"""Widget OpenGL que desenha o céu e trata a interação (pan, zoom, cursor)."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..catalogs import skygeometry
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
}


def _wrap_pi(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


class SkyWidget(QOpenGLWidget):
    statusUpdated = Signal(str)

    def __init__(self, engine: SkyEngine, stars: StarCatalog, data_dir, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.stars = stars
        self.camera = Camera()
        self.renderer = GLRenderer()
        self.layers = dict(DEFAULT_LAYERS)
        self.name_mode = "proper"  # 'proper' | 'bayer'
        self.location_name = ""

        self.const_lines = skygeometry.load_constellation_lines(data_dir)
        self.const_bounds = skygeometry.load_constellation_bounds(data_dir)
        self.milkyway = skygeometry.load_milkyway_points(data_dir)
        self.grid = skygeometry.build_grid()
        self.horizon = skygeometry.build_horizon()
        self.cardinals = skygeometry.cardinal_vectors()

        self._drag_anchor: tuple[float, float] | None = None
        self._cursor_altaz: tuple[float, float] | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self.update)
        self._clock.start()

    # ------------------------------------------------------------------
    def set_layer(self, key: str, value: bool) -> None:
        self.layers[key] = value
        self.update()

    def set_name_mode(self, mode: str) -> None:
        self.name_mode = mode
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

        # --- estrelas ---
        star_px = None
        if self.layers["stars"]:
            star_px = self._draw_stars(m, star_fade)

        # --- Sistema Solar ---
        bodies_px = []
        if self.layers["planets"]:
            bodies_px = self._draw_bodies(t)

        r.end_frame()
        painter.endNativePainting()

        # --- rótulos (QPainter em pixels lógicos) ---
        self._draw_labels(painter, dpr, star_px, bodies_px)
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
    def _draw_labels(self, painter: QPainter, dpr: float, star_px, bodies_px):
        painter.setRenderHint(QPainter.TextAntialiasing)

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
    def _emit_status(self, t) -> None:
        local = self.engine.time.current_datetime().astimezone()
        fov = math.degrees(self.camera.fov)
        parts = [
            self.location_name,
            local.strftime("%d/%m/%Y %H:%M:%S"),
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

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 0.82 if delta > 0 else 1.0 / 0.82
        self.camera.zoom(factor)
        self.update()
