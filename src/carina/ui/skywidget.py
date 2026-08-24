"""Widget OpenGL que desenha o céu e trata a interação (pan, zoom, cursor)."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..catalogs import skygeometry
from ..catalogs.dso import DsoCatalog
from ..catalogs.stars import StarCatalog
from ..core.engine import SkyEngine
from ..core.projection import Camera
from ..render.glrenderer import GLRenderer

# Cores (r, g, b, a)
COL_GRID_ALTAZ = (0.15, 0.45, 0.35, 0.42)
COL_GRID_EQ = (0.30, 0.40, 0.65, 0.42)
COL_CONST_LINES = (0.35, 0.55, 0.80, 0.65)
COL_CONST_BOUNDS = (0.62, 0.52, 0.26, 0.50)
COL_HORIZON = (0.80, 0.45, 0.18, 0.95)
COL_MILKYWAY = (0.58, 0.64, 0.80)

DEFAULT_LAYERS = {
    "stars": True,
    "planets": True,
    "const_lines": True,
    "const_bounds": False,
    "grid_altaz": True,
    "grid_eq": False,
    "milkyway": True,
    "horizon": True,
    "cardinals": True,
    "star_names": True,
    "planet_names": True,
    "atmosphere": True,
    "dso": True,
    "dso_names": True,
}

# Cores dos símbolos de céu profundo por classe (índices de KLASS_CODES)
DSO_COLORS = [
    (0.88, 0.58, 0.58),  # GAL
    (0.55, 0.75, 0.95),  # OC
    (0.95, 0.85, 0.55),  # GC
    (0.55, 0.88, 0.65),  # NEB
    (0.55, 0.95, 0.88),  # PN
    (0.52, 0.50, 0.60),  # DARK
    (0.72, 0.72, 0.72),  # OTHER
]


def _circle_pts(n: int) -> np.ndarray:
    a = np.linspace(0.0, 2.0 * math.pi, n + 1)
    return np.column_stack([np.cos(a), np.sin(a)])


def _polyline_segs(pts: np.ndarray, dashed: bool = False) -> np.ndarray:
    seg = np.stack([pts[:-1], pts[1:]], axis=1)  # (S,2,2)
    if dashed:
        seg = seg[::2]
    return seg


def _make_templates() -> dict[int, np.ndarray]:
    circle = _polyline_segs(_circle_pts(16))
    circle_dash = _polyline_segs(_circle_pts(20), dashed=True)
    sq = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]], float) * 0.85
    square = _polyline_segs(sq)
    square_dash = np.concatenate(
        [_polyline_segs(np.linspace(sq[i], sq[i + 1], 5), dashed=True)
         for i in range(4)]
    )
    cross = np.array(
        [[[-0.9, 0], [0.9, 0]], [[0, -0.9], [0, 0.9]]], float
    )
    ticks = np.array(
        [[[1.0, 0], [1.6, 0]], [[-1.0, 0], [-1.6, 0]],
         [[0, 1.0], [0, 1.6]], [[0, -1.0], [0, -1.6]]], float
    )
    ell = _circle_pts(16) * np.array([1.0, 0.5])
    diamond = _polyline_segs(
        np.array([[0, -1], [1, 0], [0, 1], [-1, 0], [0, -1]], float) * 0.8
    )
    return {
        0: _polyline_segs(ell),                       # GAL: elipse
        1: circle_dash,                               # OC: círculo tracejado
        2: np.concatenate([circle, cross]),           # GC: círculo + cruz
        3: square,                                    # NEB: quadrado
        4: np.concatenate([_polyline_segs(_circle_pts(12)) * 0.7, ticks * 0.7]),  # PN
        5: square_dash,                               # DARK: quadrado tracejado
        6: diamond,                                   # OTHER: losango
    }


DSO_TEMPLATES = _make_templates()


def _wrap_pi(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


class SkyWidget(QOpenGLWidget):
    statusUpdated = Signal(str)
    selectionChanged = Signal(object)  # None | ("star", idx) | ("body", nome)

    def __init__(self, engine: SkyEngine, stars: StarCatalog, dso: DsoCatalog,
                 data_dir, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.stars = stars
        self.dso = dso
        self.camera = Camera()
        self.renderer = GLRenderer()
        self.layers = dict(DEFAULT_LAYERS)
        self.name_mode = "proper"    # 'proper' | 'bayer'
        self.dso_name_mode = "number"  # 'number' | 'name' (item 10)
        self.location_name = ""

        self.const_lines = skygeometry.load_constellation_lines(data_dir)
        self.const_bounds = skygeometry.load_constellation_bounds(data_dir)
        self.milkyway = skygeometry.load_milkyway_points(data_dir)
        self.grid = skygeometry.build_grid()
        self.horizon = skygeometry.build_horizon()
        self.cardinals = skygeometry.cardinal_vectors()

        self._drag_anchor: tuple[float, float] | None = None
        self._cursor_altaz: tuple[float, float] | None = None
        self._press_pos: tuple[float, float] | None = None
        self.selection: tuple[str, object] | None = None
        self._pick_stars = None    # (idx, x, y) do último quadro
        self._pick_bodies = []     # [(BodyState, x, y, size)] do último quadro
        self._pick_dso = None      # (idx, x, y) do último quadro
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self.update)
        self._clock.start()

    def sync_clock(self) -> None:
        """Ajusta a cadência de repintura à velocidade da simulação."""
        speed = self.engine.time.speed
        interval = 1000 if speed in (0.0, 1.0) else 150
        if self._clock.interval() != interval:
            self._clock.setInterval(interval)
        self.update()

    # ------------------------------------------------------------------
    def set_layer(self, key: str, value: bool) -> None:
        self.layers[key] = value
        self.update()

    def set_name_mode(self, mode: str) -> None:
        self.name_mode = mode
        self.update()

    def set_dso_name_mode(self, mode: str) -> None:
        self.dso_name_mode = mode
        self.update()

    # ------------------------------------------------------------------
    def initializeGL(self) -> None:
        self.renderer.initialize()

    def resizeGL(self, w: int, h: int) -> None:
        pass  # o viewport é definido a cada quadro em paintGL

    # ------------------------------------------------------------------
    def _atmosphere(self, sun_alt: float):
        """Cor de fundo e fator de apagamento das estrelas pelo crepúsculo."""
        alt_deg = math.degrees(sun_alt)
        twilight = min(1.0, max(0.0, (alt_deg + 18.0) / 18.0))
        day = min(1.0, max(0.0, alt_deg / 10.0))
        night = np.array([0.012, 0.022, 0.045])
        dusk = np.array([0.10, 0.14, 0.28])
        noon = np.array([0.33, 0.55, 0.83])
        bg = night + (dusk - night) * twilight
        bg = bg + (noon - bg) * day
        fade = max(0.04, 1.0 - 0.85 * twilight - 0.15 * day)
        return bg, fade

    def _mag_limit(self) -> float:
        fov_deg = math.degrees(self.camera.fov)
        return min(13.5, 6.8 + 5.0 * math.log10(90.0 / fov_deg))

    # ------------------------------------------------------------------
    def paintGL(self) -> None:
        cam = self.camera
        dpr = self.devicePixelRatioF()
        w = max(1, int(self.width() * dpr))
        h = max(1, int(self.height() * dpr))
        cam.set_viewport(w, h)

        t = self.engine.time.current()
        m = self.engine.horizontal_matrix(t).astype(np.float32)

        if self.layers["atmosphere"]:
            sun_alt = self.engine.sun_altitude(t)
        else:
            sun_alt = -math.pi / 2
        bg, star_fade = self._atmosphere(sun_alt)

        painter = QPainter(self)
        painter.beginNativePainting()
        r = self.renderer
        r.begin_frame(w, h, bg)

        # --- Via Láctea (nuvem de splats ponderada pelas isofotas) ---
        if self.layers["milkyway"] and star_fade > 0.1:
            mw = self.milkyway
            mw_verts = mw.xyz @ m.T
            x, y, vis = cam.project(mw_verts, margin=96.0)
            idx = np.nonzero(vis)[0]
            if len(idx):
                size = float(np.clip(math.radians(1.5) * cam.pixel_scale, 8.0, 110.0))
                data = np.empty((len(idx), 7), dtype=np.float32)
                data[:, 0] = x[idx]
                data[:, 1] = y[idx]
                data[:, 2] = size
                data[:, 3:6] = COL_MILKYWAY
                alpha = mw.weight[idx].astype(np.float32) * 0.016 * star_fade
                below = mw_verts[idx, 2] < 0.0
                data[:, 6] = np.where(below, alpha * 0.15, alpha)
                r.draw_points(data)

        # --- grades ---
        if self.layers["grid_altaz"]:
            r.draw_lines(self._segments(self.grid, None, COL_GRID_ALTAZ))
        if self.layers["grid_eq"]:
            r.draw_lines(self._segments(self.grid, m, COL_GRID_EQ))

        # --- constelações ---
        if self.layers["const_bounds"]:
            r.draw_lines(self._segments(self.const_bounds, m, COL_CONST_BOUNDS))
        if self.layers["const_lines"]:
            r.draw_lines(self._segments(self.const_lines, m, COL_CONST_LINES))

        # --- horizonte ---
        if self.layers["horizon"]:
            r.draw_lines(self._segments(self.horizon, None, COL_HORIZON))

        # --- céu profundo (símbolos e contornos) ---
        dso_px = None
        if self.layers["dso"]:
            dso_px = self._draw_dso(m, star_fade)

        # --- estrelas ---
        star_px = None
        if self.layers["stars"]:
            star_px = self._draw_stars(m, star_fade)

        # --- Sistema Solar ---
        bodies_px = []
        if self.layers["planets"]:
            bodies_px = self._draw_bodies(t)

        # cache para o picking por clique
        self._pick_stars = star_px[:3] if star_px is not None else None
        self._pick_bodies = bodies_px
        self._pick_dso = dso_px[:3] if dso_px is not None else None

        # --- marcador da seleção ---
        self._draw_selection_marker(m)

        r.end_frame()
        painter.endNativePainting()

        # --- rótulos (QPainter em pixels lógicos) ---
        self._draw_labels(painter, dpr, star_px, bodies_px, dso_px)
        painter.end()

        self._emit_status(t)

    # ------------------------------------------------------------------
    def _segments(self, pset: skygeometry.PolylineSet, m: np.ndarray | None,
                  color, dim_below: bool = True) -> np.ndarray:
        verts = pset.verts if m is None else pset.verts @ m.T
        x, y, vis = self.camera.project(verts)
        seg = pset.segments
        ok = vis[seg[:, 0]] & vis[seg[:, 1]]
        s = seg[ok]
        out = np.empty((2 * len(s), 6), dtype=np.float32)
        out[0::2, 0] = x[s[:, 0]]
        out[0::2, 1] = y[s[:, 0]]
        out[1::2, 0] = x[s[:, 1]]
        out[1::2, 1] = y[s[:, 1]]
        out[:, 2:] = color
        if dim_below:
            below = np.empty(2 * len(s), dtype=bool)
            below[0::2] = verts[s[:, 0], 2] < 0.0
            below[1::2] = verts[s[:, 1], 2] < 0.0
            out[below, 5] *= 0.3
        return out

    def _draw_stars(self, m: np.ndarray, fade: float):
        cat = self.stars
        cam = self.camera
        m_lim = self._mag_limit()
        n = cat.count_brighter_than(m_lim)
        if n == 0:
            return None
        vecs = cat.xyz[:n] @ m.T
        x, y, vis = cam.project(vecs, margin=16.0)
        idx = np.nonzero(vis)[0]
        if len(idx) == 0:
            return None
        mag = cat.mag[idx]
        rel = np.maximum(0.0, m_lim - mag)
        sizes = np.minimum(16.0, 1.3 + 0.55 * rel ** 1.25).astype(np.float32)
        alpha = np.clip(0.28 + 0.17 * rel, 0.0, 1.0).astype(np.float32) * fade
        # abaixo do horizonte: bem mais fraco
        below = vecs[idx, 2] < 0.0
        alpha = np.where(below, alpha * 0.15, alpha)
        keep = alpha > 0.02
        idx = idx[keep]
        if len(idx) == 0:
            return None
        data = np.empty((len(idx), 7), dtype=np.float32)
        data[:, 0] = x[idx]
        data[:, 1] = y[idx]
        data[:, 2] = sizes[keep]
        data[:, 3:6] = cat.colors[idx]
        data[:, 6] = alpha[keep]
        self.renderer.draw_points(data)
        below_map = dict(zip(idx.tolist(), below[keep].tolist()))
        return idx, x, y, below_map

    def _dso_size_px(self) -> np.ndarray:
        """Eixo maior de cada objeto em pixels na escala atual."""
        return self.dso.maj * (math.radians(1.0 / 60.0) * self.camera.pixel_scale)

    def _draw_dso(self, m: np.ndarray, fade: float):
        dso = self.dso
        if len(dso) == 0:
            return None
        cam = self.camera
        vecs = dso.xyz @ m.T
        x, y, vis = cam.project(vecs, margin=48.0)
        maj_px = self._dso_size_px()
        dso_lim = self._mag_limit() - 0.3
        show = vis & ((dso.mag <= dso_lim) | (maj_px >= 14.0))
        idx = np.nonzero(show)[0]
        if len(idx) == 0:
            return None
        idx = idx[:400]  # arrays em ordem de magnitude: mantém os brilhantes

        pole = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        segs: list[np.ndarray] = []
        cols: list[np.ndarray] = []
        for i in idx:
            code = int(dso.klass[i])
            below = vecs[i, 2] < 0.0
            alpha = 0.85 * fade * (0.25 if below else 1.0)
            color = np.array([*DSO_COLORS[code], alpha], dtype=np.float32)
            cx, cy = x[i], y[i]
            big = maj_px[i] > 26.0
            if big:
                # contorno elíptico orientado pelo ângulo de posição (PA)
                u = dso.xyz[i].astype(np.float64)
                n_t = pole - np.dot(pole, u) * u
                norm = np.linalg.norm(n_t)
                if norm < 1e-6:
                    n_t = np.array([1.0, 0.0, 0.0])
                else:
                    n_t = n_t / norm
                e_t = np.cross(pole, u)
                e_t = e_t / max(np.linalg.norm(e_t), 1e-9)
                pts3 = np.stack([u + 1e-4 * n_t, u + 1e-4 * e_t])
                pts3 /= np.linalg.norm(pts3, axis=1, keepdims=True)
                px2, py2, _ = cam.project((pts3 @ m.T.astype(np.float64)), margin=1e9)
                n_scr = np.array([px2[0] - cx, py2[0] - cy])
                e_scr = np.array([px2[1] - cx, py2[1] - cy])
                n_scr /= max(np.linalg.norm(n_scr), 1e-9)
                e_scr /= max(np.linalg.norm(e_scr), 1e-9)
                pa = math.radians(float(dso.pa[i]))
                dir_a = math.cos(pa) * n_scr + math.sin(pa) * e_scr
                dir_b = -math.sin(pa) * n_scr + math.cos(pa) * e_scr
                a_px = maj_px[i] / 2.0
                b_px = max(
                    dso.minor[i] * math.radians(1 / 60.0) * cam.pixel_scale / 2.0,
                    a_px * 0.35,
                )
                ang = np.linspace(0.0, 2.0 * math.pi, 25)
                ring = (
                    np.array([cx, cy])
                    + np.outer(a_px * np.cos(ang), dir_a)
                    + np.outer(b_px * np.sin(ang), dir_b)
                )
                seg = np.stack([ring[:-1], ring[1:]], axis=1)
            else:
                r = float(np.clip(maj_px[i] * 0.5, 6.0, 13.0))
                seg = DSO_TEMPLATES[code] * r + np.array([cx, cy])
            segs.append(seg.astype(np.float32))
            cols.append(np.repeat(color[np.newaxis, :], 2 * len(seg), axis=0))

        if segs:
            all_seg = np.concatenate(segs).reshape(-1, 2)
            out = np.empty((len(all_seg), 6), dtype=np.float32)
            out[:, :2] = all_seg
            out[:, 2:] = np.concatenate(cols)
            self.renderer.draw_lines(out)
        return idx, x, y, maj_px

    def _draw_bodies(self, t):
        cam = self.camera
        out = []
        rows = []
        scale = cam.pixel_scale
        for b in self.engine.bodies(t):
            x, y, vis = cam.project(b.vec[np.newaxis, :])
            if not vis[0]:
                continue
            if b.angular_radius > 0.0:
                size = max(8.0, 2.0 * b.angular_radius * scale * 1.35)
            else:
                size = float(np.clip(9.0 - 1.1 * b.magnitude, 3.5, 14.0))
            dim = 0.25 if b.alt < 0 else 1.0
            rows.append([x[0], y[0], size, *b.color, dim])
            out.append((b, float(x[0]), float(y[0]), size))
        if rows:
            self.renderer.draw_points(np.array(rows, dtype=np.float32))
        return out

    # ------------------------------------------------------------------
    def _draw_labels(self, painter: QPainter, dpr: float, star_px, bodies_px,
                     dso_px=None):
        painter.setRenderHint(QPainter.TextAntialiasing)

        # rótulos de céu profundo (item 10: número de catálogo ou nome)
        if self.layers["dso_names"] and dso_px is not None:
            idx, x, y, maj_px = dso_px
            dso = self.dso
            label_lim = self._mag_limit() - 1.8
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QColor(150, 168, 190))
            shown = 0
            for i in idx:
                if not (dso.mag[i] <= label_lim or maj_px[i] > 30.0):
                    continue
                off = int(max(8.0, min(14.0, maj_px[i] * 0.5)) / dpr)
                painter.drawText(
                    int(x[i] / dpr) + off, int(y[i] / dpr) - off + 4,
                    dso.label(int(i), self.dso_name_mode),
                )
                shown += 1
                if shown >= 30:
                    break

        # pontos cardeais
        if self.layers["cardinals"]:
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.setPen(QColor(230, 140, 60))
            for name, vec in self.cardinals:
                x, y, vis = self.camera.project(vec[np.newaxis, :])
                if vis[0]:
                    painter.drawText(
                        int(x[0] / dpr) - 8, int(y[0] / dpr) - 6, name
                    )

        # nomes de estrelas
        if self.layers["star_names"] and star_px is not None:
            idx, x, y, below_map = star_px
            cat = self.stars
            name_lim = max(1.6, min(7.5, self._mag_limit() - 5.0))
            painter.setFont(QFont("Segoe UI", 8))
            pen_up = QColor(170, 185, 210)
            pen_down = QColor(70, 78, 92)
            shown = 0
            id_set = (
                cat.proper_idx if self.name_mode == "proper" else cat.bayer_idx
            )
            on_screen = set(idx.tolist())
            for si in id_set:
                if cat.mag[si] > name_lim:
                    break
                if si not in on_screen:
                    continue
                label = cat.label(int(si), self.name_mode)
                if not label:
                    continue
                painter.setPen(pen_down if below_map.get(int(si)) else pen_up)
                painter.drawText(int(x[si] / dpr) + 7, int(y[si] / dpr) - 5, label)
                shown += 1
                if shown >= 70:
                    break

        # nomes dos corpos do Sistema Solar
        if self.layers["planet_names"] and bodies_px:
            painter.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
            for b, x, y, size in bodies_px:
                painter.setPen(
                    QColor(95, 92, 82) if b.alt < 0 else QColor(235, 225, 200)
                )
                painter.drawText(
                    int(x / dpr) + int(size / dpr / 2) + 5,
                    int(y / dpr) - 5,
                    b.name,
                )

    # ------------------------------------------------------------------
    def _selection_screen_pos(self, m: np.ndarray):
        """Posição em pixels (device) da seleção atual, ou None se invisível."""
        if self.selection is None:
            return None
        kind, key = self.selection
        if kind == "star":
            vec = (self.stars.xyz[int(key)] @ m.T)[np.newaxis, :]
            x, y, vis = self.camera.project(vec)
            return (float(x[0]), float(y[0])) if vis[0] else None
        if kind == "dso":
            row = self.dso.row_of(int(key))
            if row is None:
                return None
            vec = (self.dso.xyz[row] @ m.T)[np.newaxis, :]
            x, y, vis = self.camera.project(vec)
            return (float(x[0]), float(y[0])) if vis[0] else None
        for b, x, y, _size in self._pick_bodies:
            if b.name == key:
                return (x, y)
        return None

    def _draw_selection_marker(self, m: np.ndarray) -> None:
        pos = self._selection_screen_pos(m)
        if pos is None:
            return
        cx, cy = pos
        radius = 15.0
        n = 28
        ang = np.linspace(0.0, 2.0 * math.pi, n + 1)
        px = cx + radius * np.cos(ang)
        py = cy + radius * np.sin(ang)
        out = np.empty((2 * n, 6), dtype=np.float32)
        out[0::2, 0] = px[:-1]
        out[0::2, 1] = py[:-1]
        out[1::2, 0] = px[1:]
        out[1::2, 1] = py[1:]
        out[:, 2:] = (0.95, 0.65, 0.25, 0.9)
        self.renderer.draw_lines(out)

    def clear_selection(self) -> None:
        if self.selection is not None:
            self.selection = None
            self.selectionChanged.emit(None)
            self.update()

    def _pick_at(self, px: float, py: float) -> None:
        """Seleciona o objeto mais próximo do clique (corpos têm prioridade)."""
        best = None
        for b, x, y, size in self._pick_bodies:
            r = max(14.0, size / 2.0 + 8.0)
            d2 = (x - px) ** 2 + (y - py) ** 2
            if d2 <= r * r and (best is None or d2 < best[0]):
                best = (d2, ("body", b.name))
        if best is None:
            candidates: list[tuple[float, tuple]] = []
            if self._pick_stars is not None:
                idx, x, y = self._pick_stars
                d2 = (x[idx] - px) ** 2 + (y[idx] - py) ** 2
                k = int(np.argmin(d2))
                if d2[k] <= 14.0 ** 2:
                    candidates.append((float(d2[k]), ("star", int(idx[k]))))
            if self._pick_dso is not None:
                idx, x, y = self._pick_dso
                d2 = (x[idx] - px) ** 2 + (y[idx] - py) ** 2
                k = int(np.argmin(d2))
                if d2[k] <= 16.0 ** 2:
                    candidates.append(
                        (float(d2[k]), ("dso", int(self.dso.ids[idx[k]])))
                    )
            if candidates:
                best = min(candidates, key=lambda c: c[0])
        new = best[1] if best else None
        if new != self.selection:
            self.selection = new
            self.selectionChanged.emit(new)
        self.update()

    # ------------------------------------------------------------------
    def _emit_status(self, t) -> None:
        from ..core.formats import speed_label

        local = self.engine.time.current_datetime().astimezone()
        fov = math.degrees(self.camera.fov)
        parts = [
            self.location_name,
            local.strftime("%d/%m/%Y %H:%M:%S"),
            speed_label(self.engine.time.speed),
            f"FOV {fov:.2f}°" if fov < 10 else f"FOV {fov:.0f}°",
        ]
        if self._cursor_altaz:
            az, alt = self._cursor_altaz
            parts.append(
                f"Cursor: Az {math.degrees(az):.1f}°  Alt {math.degrees(alt):.1f}°"
            )
        self.statusUpdated.emit("   ·   ".join(p for p in parts if p))

    # ------------------------------------------------------------------
    # Interação
    # ------------------------------------------------------------------
    def _device_pos(self, event) -> tuple[float, float]:
        dpr = self.devicePixelRatioF()
        p = event.position()
        return p.x() * dpr, p.y() * dpr

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            x, y = self._device_pos(event)
            self._press_pos = (x, y)
            self._drag_anchor = self.camera.screen_to_altaz(x, y)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        x, y = self._device_pos(event)
        self._cursor_altaz = self.camera.screen_to_altaz(x, y)
        if self._drag_anchor is not None and (event.buttons() & Qt.LeftButton):
            az_c, alt_c = self._cursor_altaz
            az_p, alt_p = self._drag_anchor
            daz = _wrap_pi(az_c - az_p)
            dalt = alt_c - alt_p
            cam = self.camera
            cam.set_direction(cam.az - daz, cam.alt - dalt)
            self.update()
        else:
            t = self.engine.time.current()
            self._emit_status(t)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_anchor = None
            self.setCursor(Qt.ArrowCursor)
            x, y = self._device_pos(event)
            if self._press_pos is not None:
                dx = x - self._press_pos[0]
                dy = y - self._press_pos[1]
                if dx * dx + dy * dy <= 36.0:  # clique, não arrasto
                    self._pick_at(x, y)
            self._press_pos = None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 0.82 if delta > 0 else 1.0 / 0.82
        self.camera.zoom(factor)
        self.update()
