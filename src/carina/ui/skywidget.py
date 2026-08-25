"""Widget OpenGL que desenha o céu e trata a interação (pan, zoom, cursor)."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..catalogs import skygeometry
from ..catalogs.dso import DsoCatalog
from ..catalogs.stars import StarCatalog
from ..core.eclipses import moon_influence_radii
from ..core.engine import SkyEngine
from ..core.projection import FOV_MAX, FOV_MIN, Camera
from ..render.glrenderer import GLRenderer

# Cores (r, g, b, a)
COL_GRID_ALTAZ = (0.15, 0.45, 0.35, 0.42)
COL_GRID_EQ = (0.30, 0.40, 0.65, 0.42)
COL_CONST_LINES = (0.35, 0.55, 0.80, 0.65)
COL_CONST_BOUNDS = (0.62, 0.52, 0.26, 0.50)
COL_HORIZON = (0.80, 0.45, 0.18, 0.95)
COL_MERIDIAN = (0.55, 0.80, 0.60, 0.75)
COL_ECLIPTIC = (0.85, 0.72, 0.30, 0.80)
COL_EQUATOR = (0.45, 0.60, 0.90, 0.70)
COL_MILKYWAY = (0.58, 0.64, 0.80)

DEFAULT_LAYERS = {
    "stars": True,
    "planets": True,
    "moon_zone": False,
    "const_lines": True,
    "const_bounds": False,
    "grid_altaz": True,
    "grid_eq": False,
    "meridian": False,
    "ecliptic": False,
    "equator": False,
    "milkyway": True,
    "horizon": True,
    "ground": True,
    "cardinals": True,
    "star_names": True,
    "planet_names": True,
    "atmosphere": True,
    "refraction": True,
    "below_horizon": False,   # mostrar o céu abaixo do horizonte
    "const_names": False,
    "dso": True,
    "dso_names": True,
    "dso_images": False,
}

COL_GROUND_NIGHT = np.array([0.050, 0.078, 0.055])
COL_GROUND_DAY = np.array([0.165, 0.210, 0.150])

# Paleta do modo mapa para impressão (traços escuros sobre papel branco)
CHART_COLORS = {
    "grid_altaz": (0.62, 0.68, 0.62, 0.85),
    "grid_eq": (0.58, 0.62, 0.78, 0.85),
    "const_lines": (0.35, 0.42, 0.62, 0.95),
    "const_bounds": (0.72, 0.62, 0.42, 0.85),
    "horizon": (0.70, 0.35, 0.10, 1.0),
    "ground": (0.88, 0.90, 0.86),
    "dso": (0.15, 0.20, 0.30),
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


class _LabelPlacer:
    """Anti-colisão de rótulos: guarda retângulos ocupados (B-003).

    Rótulos de maior prioridade são colocados primeiro com force=True;
    os demais são descartados se colidirem com algo já colocado.
    """

    def __init__(self) -> None:
        self._rects: list[tuple[float, float, float, float]] = []

    def place(self, x: float, y_baseline: float, w: float, h: float,
              force: bool = False) -> bool:
        top = y_baseline - h
        pad = 2.0
        if not force:
            for ox, oy, ow, oh in self._rects:
                if (x < ox + ow + pad and ox < x + w + pad
                        and top < oy + oh + pad and oy < top + h + pad):
                    return False
        self._rects.append((x, top, w, h))
        return True


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
        self.prefer_caldwell = True    # C 14 em vez de NGC 7000
        self.location_name = ""
        self.mag_cap: float | None = None   # limite manual de magnitude
        self.bortle: int = 1                # 1 = céu perfeito … 9 = centro urbano
        self.const_label_mode = "none"      # none | pt | latin | abbr
        self.planet_paths: list = []        # trajetórias anuais (item 8)
        self.chart_mode = False             # modo mapa para impressão
        self.mouse_mode = "pan"             # 'pan' | 'measure' | 'zoom_rect'
        self._measure: dict | None = None   # medição angular ativa
        self._rubber: list | None = None    # retângulo de zoom
        self._label_hits: list = []         # (rect lógico, seleção)
        self._path_marks: list = []         # rótulos das trajetórias
        self.fov_shapes: list = []          # campos de equipamentos (item 7)
        self.fov_angle: float = 0.0         # rotação do campo (rad)
        self.fov_follow_selection = True

        # centros das constelações para os rótulos (item 5)
        self.const_info = skygeometry.load_constellation_info(data_dir)
        self.const_centers = np.array(
            [
                [
                    math.cos(math.radians(c["dec"]))
                    * math.cos(math.radians(c["ra"])),
                    math.cos(math.radians(c["dec"]))
                    * math.sin(math.radians(c["ra"])),
                    math.sin(math.radians(c["dec"])),
                ]
                for c in self.const_info
            ],
            dtype=np.float32,
        ) if self.const_info else np.zeros((0, 3), dtype=np.float32)

        self.const_lines = skygeometry.load_constellation_lines(data_dir)
        self.const_bounds = skygeometry.load_constellation_bounds(data_dir)
        self.milkyway = skygeometry.load_milkyway_points(data_dir)
        self.grid = skygeometry.build_grid()
        self.horizon = skygeometry.build_horizon()
        self.meridian = skygeometry.build_meridian()
        self.ecliptic = skygeometry.build_ecliptic()
        self.equator = skygeometry.build_equator()
        self.cardinals = skygeometry.cardinal_vectors()
        self.ground_verts, self.ground_tris = skygeometry.build_ground()
        self._goto_anim = None

        # malha da esfera celeste para a textura da Via Láctea (Stellarium-like)
        from ..render.dsoimages import DsoImageLayer

        featured: dict[str, dict] = {}
        manifest_path = data_dir / "featured_images.json"
        if manifest_path.exists():
            import json

            featured = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.dso_images = DsoImageLayer(
            {name: info["fov"] for name, info in featured.items()}
        )
        self.dso.set_featured_names(set(featured))
        self.outlines = skygeometry.load_outlines(data_dir)
        self.mw_mesh = skygeometry.build_sphere_mesh()
        self._mw_tex_rgb = None
        tex_path = data_dir / "milkyway_tex.jpg"
        if tex_path.exists():
            from PySide6.QtGui import QImage

            img = QImage(str(tex_path)).convertToFormat(QImage.Format_RGB888)
            w, h = img.width(), img.height()
            buf = np.frombuffer(img.constBits(), dtype=np.uint8)
            buf = buf.reshape(h, img.bytesPerLine())[:, : w * 3]
            self._mw_tex_rgb = buf.reshape(h, w, 3).copy()

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

    def set_prefer_caldwell(self, value: bool) -> None:
        self.prefer_caldwell = value
        self.update()

    # ------------------------------------------------------------------
    def initializeGL(self) -> None:
        self.renderer.initialize()
        if self._mw_tex_rgb is not None:
            self.renderer.set_mw_texture(self._mw_tex_rgb)

    def resizeGL(self, w: int, h: int) -> None:
        pass  # o viewport é definido a cada quadro em paintGL

    # ------------------------------------------------------------------
    def _atmosphere(self, sun_alt: float):
        """Cor de fundo, apagamento das estrelas e fator diurno."""
        alt_deg = math.degrees(sun_alt)
        twilight = min(1.0, max(0.0, (alt_deg + 18.0) / 18.0))
        day = min(1.0, max(0.0, alt_deg / 10.0))
        night = np.array([0.012, 0.022, 0.045])
        dusk = np.array([0.10, 0.14, 0.28])
        noon = np.array([0.33, 0.55, 0.83])
        bg = night + (dusk - night) * twilight
        bg = bg + (noon - bg) * day
        # brilho do céu por poluição luminosa (tom alaranjado das lâmpadas)
        glow = self.BORTLE_GLOW[self.bortle]
        if glow:
            bg = bg + glow * np.array([1.00, 0.72, 0.42])
        fade = max(0.04, 1.0 - 0.85 * twilight - 0.15 * day)
        return np.clip(bg, 0.0, 1.0), fade, day

    # ------------------------------------------------------------------
    def _refract(self, vecs: np.ndarray) -> np.ndarray:
        """Refração atmosférica (Sæmundsson) aplicada a vetores horizontais.

        Eleva a altitude aparente: R = 1,02/tan(h + 10,3/(h + 5,11)) arcmin,
        com h em graus; nula abaixo de -1°. Não é aplicada à grade horizontal
        nem ao horizonte, que são referências geométricas.
        """
        if not self.layers.get("refraction", True):
            return vecs
        z = np.clip(vecs[:, 2], -1.0, 1.0)
        alt = np.degrees(np.arcsin(z))
        alt_f = np.maximum(alt, -0.99)
        with np.errstate(divide="ignore", invalid="ignore"):
            r_arcmin = 1.02 / np.tan(np.radians(alt_f + 10.3 / (alt_f + 5.11)))
        r_arcmin = np.where(alt > -1.0, np.maximum(r_arcmin, 0.0), 0.0)
        alt_new = np.radians(alt + r_arcmin / 60.0)
        cos_old = np.maximum(np.cos(np.radians(alt)), 1e-9)
        factor = np.cos(alt_new) / cos_old
        out = np.empty_like(vecs)
        out[:, 0] = vecs[:, 0] * factor
        out[:, 1] = vecs[:, 1] * factor
        out[:, 2] = np.sin(alt_new)
        return out

    def _to_screen(self, vecs: np.ndarray, margin: float = 64.0):
        """Projeção de conteúdo celeste: refração + câmera."""
        return self.camera.project(self._refract(vecs), margin=margin)

    # Magnitude-limite a olho nu por classe de Bortle (escala clássica) e
    # brilho do fundo do céu correspondente, usado para simular a poluição.
    BORTLE_NELM = {
        1: 7.8, 2: 7.4, 3: 7.0, 4: 6.5, 5: 6.0, 6: 5.5, 7: 5.0, 8: 4.5,
        9: 4.0,
    }
    BORTLE_GLOW = {
        1: 0.000, 2: 0.006, 3: 0.014, 4: 0.026, 5: 0.042, 6: 0.062,
        7: 0.086, 8: 0.115, 9: 0.150,
    }

    def _mag_limit(self) -> float:
        fov_deg = math.degrees(self.camera.fov)
        auto = min(13.5, 6.8 + 5.0 * math.log10(90.0 / fov_deg))
        # a poluição luminosa corta as estrelas fracas: o desconto é a
        # diferença entre o céu perfeito (Bortle 1) e a classe escolhida
        auto -= self.BORTLE_NELM[1] - self.BORTLE_NELM[self.bortle]
        if self.mag_cap is not None:
            return min(auto, self.mag_cap)
        return auto

    def set_bortle(self, value: int) -> None:
        self.bortle = max(1, min(9, int(value)))
        self.update()

    def set_const_label_mode(self, mode: str) -> None:
        self.const_label_mode = mode
        self.layers["const_names"] = mode != "none"
        self.update()

    def set_mag_cap(self, value: float | None) -> None:
        self.mag_cap = value
        self.update()

    def set_chart_mode(self, on: bool) -> None:
        self.chart_mode = on
        self.update()

    def set_mouse_mode(self, mode: str) -> None:
        self.mouse_mode = mode
        self._measure = None
        self._rubber = None
        self.setCursor(
            Qt.CrossCursor if mode in ("measure", "zoom_rect") else Qt.ArrowCursor
        )
        self.update()

    # ------------------------------------------------------------------
    def paintGL(self) -> None:
        cam = self.camera
        dpr = self.devicePixelRatioF()
        w = max(1, int(self.width() * dpr))
        h = max(1, int(self.height() * dpr))
        cam.set_viewport(w, h)

        t = self.engine.time.current()
        m = self.engine.horizontal_matrix(t).astype(np.float32)

        if self.chart_mode:
            bg, star_fade, day = np.array([1.0, 1.0, 1.0]), 1.0, 0.0
        elif self.layers["atmosphere"]:
            sun_alt = self.engine.sun_altitude(t)
            bg, star_fade, day = self._atmosphere(sun_alt)
        else:
            bg, star_fade, day = self._atmosphere(-math.pi / 2)

        painter = QPainter(self)
        painter.beginNativePainting()
        r = self.renderer
        r.begin_frame(w, h, bg)

        # --- Via Láctea: textura na esfera (mecanismo do Stellarium) ---
        if (self.layers["milkyway"] and star_fade > 0.1 and not self.chart_mode
                and self._mw_tex_rgb is not None):
            # A textura é difusa (estrelas do levantamento removidas no
            # build), então permanece visível em qualquer zoom.
            verts, uv, tris = self.mw_mesh
            vh = self._refract(verts @ m.T)
            fwd = cam.forward_component(vh)
            keep = (fwd[tris] > -0.05).any(axis=1)
            tri = tris[keep]
            if len(tri):
                px, py = cam.project_clamped(vh)
                idx = tri.ravel()
                pos = np.column_stack([px, py])[idx]
                # em campos pequenos a textura vira um véu uniforme (tem
                # ~5′/pixel): reduz o peso sem apagá-la
                fov_deg = math.degrees(cam.fov)
                depth = 0.42 + 0.58 * min(1.0, max(0.0, (fov_deg - 3.0) / 27.0))
                self.renderer.draw_textured_triangles(
                    pos, uv[idx], 0.72 * star_fade * depth
                )
        elif self.layers["milkyway"] and star_fade > 0.1 and not self.chart_mode:
            mw = self.milkyway
            mw_verts = self._refract(mw.xyz @ m.T)
            wanted = max(8.0, math.radians(1.6) * cam.pixel_scale)
            # sprites muito grandes são descartados por alguns drivers:
            # limitamos o tamanho e compensamos a área perdida com alpha
            # (B-010); em zoom extremo a Via Láctea se dissolve suavemente
            size = float(min(wanted, 60.0, r.max_point_size))
            boost = min((wanted / size) ** 2, 6.0)
            fov_deg = math.degrees(cam.fov)
            zoom_fade = min(1.0, max(0.0, (fov_deg - 3.0) / 5.0))
            x, y, vis = cam.project(mw_verts, margin=max(96.0, size))
            idx = np.nonzero(vis)[0]
            if len(idx) and zoom_fade > 0.0:
                w = mw.weight[idx].astype(np.float32)
                data = np.empty((len(idx), 7), dtype=np.float32)
                data[:, 0] = x[idx]
                data[:, 1] = y[idx]
                # isofotas internas com splats um pouco menores: núcleo da
                # banda mais definido, borda mais difusa
                data[:, 2] = size * (1.15 - 0.06 * w)
                data[:, 3:6] = COL_MILKYWAY
                alpha = np.minimum(w * 0.016 * boost, 0.30) * star_fade * zoom_fade
                below = mw_verts[idx, 2] < 0.0
                data[:, 6] = np.where(below, alpha * 0.15, alpha)
                r.draw_points(data)

        # --- grades ---
        chart = self.chart_mode
        if self.layers["grid_altaz"]:
            col = CHART_COLORS["grid_altaz"] if chart else COL_GRID_ALTAZ
            r.draw_lines(self._segments(self.grid, None, col))
        if self.layers["grid_eq"]:
            col = CHART_COLORS["grid_eq"] if chart else COL_GRID_EQ
            r.draw_lines(self._segments(self.grid, m, col))

        # --- círculos de referência ---
        if self.layers["equator"]:
            r.draw_lines(self._segments(self.equator, m, COL_EQUATOR))
        if self.layers["ecliptic"]:
            r.draw_lines(self._segments(self.ecliptic, m, COL_ECLIPTIC))
        if self.layers["meridian"]:
            r.draw_lines(self._segments(self.meridian, None, COL_MERIDIAN))

        # --- constelações ---
        if self.layers["const_bounds"]:
            col = CHART_COLORS["const_bounds"] if chart else COL_CONST_BOUNDS
            r.draw_lines(self._segments(self.const_bounds, m, col))
        if self.layers["const_lines"]:
            col = CHART_COLORS["const_lines"] if chart else COL_CONST_LINES
            r.draw_lines(self._segments(self.const_lines, m, col))

        # --- imagens do levantamento nos objetos (antes dos símbolos) ---
        if (self.layers["dso_images"] and self.layers["dso"]
                and not self.chart_mode and star_fade > 0.15):
            self._draw_dso_images(m, star_fade)

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
            bodies_px = self._draw_bodies(t, m)

        # --- trajetórias anuais dos planetas (item 8) ---
        if self.planet_paths:
            self._draw_planet_paths(m)

        # --- zona de influência da Lua para astrofotografia (item 5) ---
        if self.layers["moon_zone"]:
            self._draw_moon_zone(t)

        # cache para o picking por clique
        self._pick_stars = star_px[:3] if star_px is not None else None
        self._pick_bodies = bodies_px
        self._pick_dso = dso_px[:3] if dso_px is not None else None

        # --- solo opaco (cobre o que está abaixo do horizonte) ---
        # o modo "ver abaixo do horizonte" suprime o solo e marca a divisão
        ground_on = self.layers["ground"] and not self.layers["below_horizon"]
        if ground_on:
            # descarta triângulos totalmente atrás da câmera: com o clamp da
            # projeção eles se espalhariam cobrindo a tela inteira
            fwd = cam.forward_component(self.ground_verts)
            keep = (fwd[self.ground_tris] > -0.15).any(axis=1)
            tris = self.ground_tris[keep]
            if len(tris):
                gx, gy = cam.project_clamped(self.ground_verts)
                pts = np.column_stack([gx, gy])[tris.ravel()]
                if self.chart_mode:
                    col = np.asarray(CHART_COLORS["ground"])
                else:
                    col = (
                        COL_GROUND_NIGHT
                        + (COL_GROUND_DAY - COL_GROUND_NIGHT) * day
                    )
                r.fill_triangles(pts, (col[0], col[1], col[2], 1.0))

        # --- horizonte por cima do solo ---
        if self.layers["horizon"]:
            col = CHART_COLORS["horizon"] if self.chart_mode else COL_HORIZON
            r.draw_lines(self._segments(self.horizon, None, col))

        # --- campos de visão dos equipamentos (item 7) ---
        if self.fov_shapes:
            self._draw_fov_shapes(m)

        # --- marcador da seleção ---
        self._draw_selection_marker(m)

        r.end_frame()
        painter.endNativePainting()

        # --- rótulos (QPainter em pixels lógicos) ---
        self._draw_labels(painter, dpr, star_px, bodies_px, dso_px, ground_on)
        self._draw_fov_labels(painter, dpr)
        self._draw_tools_overlay(painter, dpr)
        painter.end()

        self._emit_status(t)

    # ------------------------------------------------------------------
    def _segments(self, pset: skygeometry.PolylineSet, m: np.ndarray | None,
                  color, dim_below: bool = True) -> np.ndarray:
        """Projeta polilinhas em segmentos de tela, com clipping correto.

        Segmentos que cruzam o plano da câmera são cortados por interpolação
        esférica (slerp) até um pouco à frente dela; sem isso, um vértice
        atrás do observador é projetado a um raio enorme e a linha atravessa
        a tela — era a origem das deformações em zoom (B-015).
        """
        cam = self.camera
        # Conteúdo equatorial (m fornecida) sofre refração; referências
        # horizontais (grade alt-az, horizonte) não.
        verts = pset.verts if m is None else self._refract(pset.verts @ m.T)
        verts = np.asarray(verts, dtype=np.float64)
        fwd = cam.forward_component(verts)          # cos do ângulo ao centro
        seg = pset.segments
        f0, f1 = fwd[seg[:, 0]], fwd[seg[:, 1]]

        eps = 0.02          # ~88,9° do centro da vista
        keep = (f0 > eps) | (f1 > eps)
        s = seg[keep]
        if len(s) == 0:
            return np.zeros((0, 6), dtype=np.float32)
        a = verts[s[:, 0]].copy()
        b = verts[s[:, 1]].copy()
        fa, fb = fwd[s[:, 0]].copy(), fwd[s[:, 1]].copy()

        # corta a extremidade que está atrás do plano da câmera
        for src, dst, f_src, f_dst in ((a, b, fa, fb), (b, a, fb, fa)):
            bad = f_src <= eps
            if bad.any():
                t = (eps - f_src[bad]) / (f_dst[bad] - f_src[bad])
                t = np.clip(t, 0.0, 1.0)[:, None]
                mixed = src[bad] * (1.0 - t) + dst[bad] * t
                norm = np.linalg.norm(mixed, axis=1, keepdims=True)
                src[bad] = mixed / np.maximum(norm, 1e-12)

        pts = np.concatenate([a, b])
        x, y, _ = cam.project(pts, margin=1e9)
        n = len(a)
        out = np.empty((2 * n, 6), dtype=np.float32)
        out[0::2, 0] = x[:n]
        out[0::2, 1] = y[:n]
        out[1::2, 0] = x[n:]
        out[1::2, 1] = y[n:]
        out[:, 2:] = color

        # descarta segmentos que continuam absurdamente longos (numérico)
        span = np.hypot(out[1::2, 0] - out[0::2, 0], out[1::2, 1] - out[0::2, 1])
        limit = 6.0 * max(cam.width, cam.height)
        good = np.repeat(span < limit, 2)
        out = out[good]
        if dim_below:
            below = np.empty(2 * n, dtype=bool)
            below[0::2] = a[:, 2] < 0.0
            below[1::2] = b[:, 2] < 0.0
            factor = 0.6 if self.layers.get("below_horizon", False) else 0.3
            out[below[good], 5] *= factor
        return out

    def _draw_stars(self, m: np.ndarray, fade: float):
        cat = self.stars
        cam = self.camera
        m_lim = self._mag_limit()
        n = cat.count_brighter_than(m_lim)
        if n == 0:
            return None
        vecs = self._refract(cat.xyz[:n] @ m.T)
        x, y, vis = cam.project(vecs, margin=16.0)
        idx = np.nonzero(vis)[0]
        if len(idx) == 0:
            return None
        mag = cat.mag[idx]
        rel = np.maximum(0.0, m_lim - mag)
        # Curva de tamanho bem íngreme: as estrelas mais brilhantes dominam
        # visivelmente o campo (compensação de brilho por tamanho).
        sizes = np.minimum(26.0, 1.1 + 0.68 * rel ** 1.58).astype(np.float32)
        alpha = np.clip(0.26 + 0.17 * rel, 0.0, 1.0).astype(np.float32) * fade
        # abaixo do horizonte: bem mais fraco
        below = vecs[idx, 2] < 0.0
        dim_below = 0.45 if self.layers.get("below_horizon", False) else 0.15
        alpha = np.where(below, alpha * dim_below, alpha)
        keep = alpha > 0.02
        idx = idx[keep]
        if len(idx) == 0:
            return None
        data = np.empty((len(idx), 7), dtype=np.float32)
        data[:, 0] = x[idx]
        data[:, 1] = y[idx]
        data[:, 2] = sizes[keep]
        if self.chart_mode:
            data[:, 3:6] = 0.05  # pontos escuros sobre fundo branco
            data[:, 6] = np.clip(alpha[keep] * 1.6, 0.0, 1.0)
        else:
            data[:, 3:6] = cat.colors[idx]
            data[:, 6] = alpha[keep]
        self.renderer.draw_points(data)
        below_map = dict(zip(idx.tolist(), below[keep].tolist()))

        # --- catálogo profundo (Tycho-2): só quando o zoom pede mag > 8,5 ---
        if cat.deep_xyz is not None and m_lim > 8.6:
            nd = cat.deep_count_brighter_than(m_lim)
            if nd:
                dv = self._refract(cat.deep_xyz[:nd] @ m.T)
                dx, dy, dvis = cam.project(dv, margin=16.0)
                didx = np.nonzero(dvis)[0]
                if len(didx):
                    if len(didx) > 60000:      # teto de segurança por quadro
                        didx = didx[:60000]
                    drel = np.maximum(0.0, m_lim - cat.deep_mag[didx])
                    dsize = np.minimum(
                        26.0, 1.1 + 0.68 * drel ** 1.58
                    ).astype(np.float32)
                    dalpha = (
                        np.clip(0.26 + 0.17 * drel, 0.0, 1.0).astype(np.float32)
                        * fade
                    )
                    dbelow = dv[didx, 2] < 0.0
                    if self.layers.get("below_horizon", False):
                        dalpha = np.where(dbelow, dalpha * 0.45, dalpha)
                    else:
                        dalpha = np.where(dbelow, dalpha * 0.15, dalpha)
                    ddata = np.empty((len(didx), 7), dtype=np.float32)
                    ddata[:, 0] = dx[didx]
                    ddata[:, 1] = dy[didx]
                    ddata[:, 2] = dsize
                    if self.chart_mode:
                        ddata[:, 3:6] = 0.05
                        ddata[:, 6] = np.clip(dalpha * 1.6, 0.0, 1.0)
                    else:
                        ddata[:, 3:6] = cat.deep_colors[didx]
                        ddata[:, 6] = dalpha
                    self.renderer.draw_points(ddata)
        return idx, x, y, below_map

    def _draw_dso_images(self, m: np.ndarray, fade: float) -> None:
        """Imagens DSS dos objetos visíveis (Messier/Caldwell embarcados)."""
        dso = self.dso
        if len(dso) == 0:
            return
        cam = self.camera
        vecs = self._refract(dso.xyz @ m.T)
        _, _, vis = cam.project(vecs, margin=160.0)
        maj_px = self._dso_size_px()
        # objetos com imagem no pacote (M/C + destaques) e visíveis na tela
        has_img = dso.is_mc | dso.is_featured
        candidates = np.nonzero(vis & has_img & (maj_px > 12.0))[0]
        if len(candidates) == 0:
            return
        candidates = candidates[:16]

        def project(pts, margin):
            # as imagens já estão no frame ICRS do catálogo: aplica a matriz
            return cam.project(self._refract(pts @ m.T), margin=margin)

        self.dso_images.draw(
            self.renderer, cam, project, dso, candidates, 0.62 * fade
        )

    def _dso_size_px(self) -> np.ndarray:
        """Eixo maior de cada objeto em pixels na escala atual."""
        return self.dso.maj * (math.radians(1.0 / 60.0) * self.camera.pixel_scale)

    def _draw_dso(self, m: np.ndarray, fade: float):
        dso = self.dso
        if len(dso) == 0:
            return None
        cam = self.camera
        vecs = self._refract(dso.xyz @ m.T)
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
            rgb = CHART_COLORS["dso"] if self.chart_mode else DSO_COLORS[code]
            color = np.array([*rgb, alpha], dtype=np.float32)
            cx, cy = x[i], y[i]
            big = maj_px[i] > 26.0

            # contorno real da nebulosa, quando existir e couber na tela
            shapes = self.outlines.get(dso.names[i]) if big else None
            if shapes:
                for poly in shapes:
                    pts = self._refract(poly @ m.T)
                    px, py, vis_o = cam.project(pts, margin=96.0)
                    ok = vis_o[:-1] & vis_o[1:]
                    sel = np.nonzero(ok)[0]
                    if len(sel) == 0:
                        continue
                    seg = np.empty((2 * len(sel), 2), dtype=np.float32)
                    seg[0::2, 0] = px[sel]
                    seg[0::2, 1] = py[sel]
                    seg[1::2, 0] = px[sel + 1]
                    seg[1::2, 1] = py[sel + 1]
                    segs.append(seg.reshape(-1, 2, 2))
                    cols.append(
                        np.repeat(color[np.newaxis, :], 2 * len(sel), axis=0)
                    )
                continue

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
                px2, py2, _ = self._to_screen(
                    pts3 @ m.T.astype(np.float64), margin=1e9
                )
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
        return idx, x, y, maj_px, vecs[:, 2] < 0.0

    def set_fov_shapes(self, shapes: list, angle_deg: float = 0.0,
                       follow_selection: bool = True) -> None:
        self.fov_shapes = list(shapes)
        self.fov_angle = math.radians(angle_deg)
        self.fov_follow_selection = follow_selection
        self.update()

    def _fov_center_vec(self, m: np.ndarray):
        """Centro dos campos: o objeto selecionado ou o centro da vista."""
        if self.fov_follow_selection and self.selection is not None:
            t = self.engine.time.current()
            vec = self._selection_vec(self.selection, m, t)
            if vec is not None:
                return self._refract(np.asarray(vec)[np.newaxis, :])[0]
        from ..core.projection import altaz_to_vec

        return altaz_to_vec(self.camera.az, self.camera.alt)

    def _draw_fov_shapes(self, m: np.ndarray) -> None:
        """Desenha os campos de visão (retângulos/círculos) sobre o céu."""
        u = np.asarray(self._fov_center_vec(m), dtype=np.float64)
        norm = np.linalg.norm(u)
        if norm < 1e-9:
            return
        u = u / norm
        zen = np.array([0.0, 0.0, 1.0])
        up_t = zen - np.dot(zen, u) * u
        if np.linalg.norm(up_t) < 1e-6:
            up_t = np.array([1.0, 0.0, 0.0])
        up_t /= np.linalg.norm(up_t)
        right_t = np.cross(up_t, u)
        right_t /= max(np.linalg.norm(right_t), 1e-9)

        ca, sa = math.cos(self.fov_angle), math.sin(self.fov_angle)
        e1 = ca * right_t + sa * up_t
        e2 = -sa * right_t + ca * up_t

        palette = [
            (0.35, 0.95, 0.65, 0.95), (0.95, 0.75, 0.35, 0.95),
            (0.75, 0.55, 0.95, 0.95),
        ]
        for i, shape in enumerate(self.fov_shapes):
            color = palette[i % len(palette)]
            if shape.kind == "circle":
                ang = np.linspace(0.0, 2.0 * math.pi, 145)
                a = shape.width / 2.0
                pts = (
                    math.cos(a) * u[np.newaxis, :]
                    + math.sin(a) * (np.outer(np.cos(ang), e1)
                                     + np.outer(np.sin(ang), e2))
                )
            else:
                hw, hh = shape.width / 2.0, shape.height / 2.0
                edge = []
                n = 40
                for t0, t1 in (((-hw, -hh), (hw, -hh)), ((hw, -hh), (hw, hh)),
                               ((hw, hh), (-hw, hh)), ((-hw, hh), (-hw, -hh))):
                    for k in range(n):
                        f = k / n
                        edge.append(
                            (t0[0] + (t1[0] - t0[0]) * f,
                             t0[1] + (t1[1] - t0[1]) * f)
                        )
                edge.append(edge[0])
                arr = np.asarray(edge)
                # gnomônica local: tan dos ângulos no plano tangente
                pts = (
                    u[np.newaxis, :]
                    + np.outer(np.tan(arr[:, 0]), e1)
                    + np.outer(np.tan(arr[:, 1]), e2)
                )
                pts /= np.linalg.norm(pts, axis=1, keepdims=True)

            x, y, vis = self.camera.project(pts, margin=64.0)
            ok = vis[:-1] & vis[1:]
            idx = np.nonzero(ok)[0]
            if len(idx) == 0:
                continue
            out = np.empty((2 * len(idx), 6), dtype=np.float32)
            out[0::2, 0] = x[idx]
            out[0::2, 1] = y[idx]
            out[1::2, 0] = x[idx + 1]
            out[1::2, 1] = y[idx + 1]
            out[:, 2:] = color
            self.renderer.draw_lines(out)

            # marcas do centro (cruz pequena)
            xc, yc, visc = self.camera.project(u[np.newaxis, :], margin=64.0)
            if visc[0]:
                cx, cy = float(xc[0]), float(yc[0])
                cross = np.array([
                    [cx - 7, cy, cx + 7, cy], [cx, cy - 7, cx, cy + 7],
                ], dtype=np.float32).reshape(-1, 2)
                seg = np.empty((4, 6), dtype=np.float32)
                seg[:, :2] = cross
                seg[:, 2:] = color
                self.renderer.draw_lines(seg)

    def set_planet_paths(self, paths: list) -> None:
        self.planet_paths = list(paths)
        self.update()

    def _draw_planet_paths(self, m: np.ndarray) -> None:
        """Desenha o caminho anual dos planetas entre as constelações."""
        cam = self.camera
        palette = [
            (0.95, 0.65, 0.35), (0.60, 0.85, 0.95), (0.95, 0.55, 0.55),
            (0.75, 0.95, 0.60), (0.90, 0.80, 0.45), (0.70, 0.70, 0.95),
        ]
        self._path_marks = []
        for k, path in enumerate(self.planet_paths):
            color = palette[k % len(palette)]
            pts = np.array([p.vec for p in path.points], dtype=np.float64)
            if len(pts) < 2:
                continue
            scr = self._refract(pts @ m.T.astype(np.float64))
            x, y, vis = cam.project(scr, margin=64.0)
            ok = vis[:-1] & vis[1:]
            idx = np.nonzero(ok)[0]
            if len(idx):
                out = np.empty((2 * len(idx), 6), dtype=np.float32)
                out[0::2, 0] = x[idx]
                out[0::2, 1] = y[idx]
                out[1::2, 0] = x[idx + 1]
                out[1::2, 1] = y[idx + 1]
                out[:, 2:5] = color
                # trechos retrógrados ficam mais tênues
                retro = np.array(
                    [path.points[i].retrograde for i in idx], dtype=bool
                )
                alpha = np.where(retro, 0.45, 0.9).astype(np.float32)
                out[0::2, 5] = alpha
                out[1::2, 5] = alpha
                self.renderer.draw_lines(out)

            # marcadores de data e eventos (guardados para os rótulos)
            marks = [i for i in path.marks if vis[i]]
            for i in marks:
                cxm, cym = float(x[i]), float(y[i])
                ring = np.empty((8, 6), dtype=np.float32)
                pts4 = [(-3, 0, 3, 0), (0, -3, 0, 3)]
                seg = []
                for dx0, dy0, dx1, dy1 in pts4:
                    seg += [[cxm + dx0, cym + dy0], [cxm + dx1, cym + dy1]]
                ring = np.empty((len(seg), 6), dtype=np.float32)
                ring[:, :2] = np.asarray(seg, dtype=np.float32)
                ring[:, 2:5] = color
                ring[:, 5] = 0.95
                self.renderer.draw_lines(ring)
            self._path_marks.append((path, x, y, vis, color, marks))

    def _draw_moon_zone(self, t) -> None:
        """Anéis da zona de influência da Lua (regra prática por iluminação).

        Círculo interno: zona crítica (evitar alvos de astrofoto); externo:
        zona de cautela. Raios crescem com a fração iluminada.
        """
        moon = next(
            (b for b in self.engine.bodies(t) if b.name == "Lua"), None
        )
        if moon is None or moon.alt < math.radians(-5.0):
            return
        if float(self.camera.forward_component(moon.vec[np.newaxis, :])[0]) < -0.4:
            return
        illum = self.engine.moon_illumination(t)
        r1, r2 = moon_influence_radii(illum)

        u = moon.vec / np.linalg.norm(moon.vec)
        ref = (
            np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.95
            else np.array([1.0, 0.0, 0.0])
        )
        e1 = np.cross(u, ref)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(u, e1)
        ang = np.linspace(0.0, 2.0 * math.pi, 121)
        for radius, alpha in ((r1, 0.55), (r2, 0.30)):
            ring = (
                math.cos(radius) * u[np.newaxis, :]
                + math.sin(radius) * (
                    np.outer(np.cos(ang), e1) + np.outer(np.sin(ang), e2)
                )
            )
            x, y, vis = self._to_screen(ring, margin=32.0)
            ok = vis[:-1] & vis[1:]
            idx = np.nonzero(ok)[0]
            idx = idx[idx % 2 == 0]  # tracejado: segmentos alternados
            if len(idx) == 0:
                continue
            out = np.empty((2 * len(idx), 6), dtype=np.float32)
            out[0::2, 0] = x[idx]
            out[0::2, 1] = y[idx]
            out[1::2, 0] = x[idx + 1]
            out[1::2, 1] = y[idx + 1]
            out[:, 2:] = (0.90, 0.72, 0.35, alpha)
            self.renderer.draw_lines(out)

    def _draw_bodies(self, t, m: np.ndarray):
        cam = self.camera
        out = []
        rows = []
        specials = []  # (BodyState, cx, cy) de Sol e Lua, desenhados como discos
        scale = cam.pixel_scale
        for b in self.engine.bodies(t):
            x, y, vis = self._to_screen(b.vec[np.newaxis, :])
            if not vis[0]:
                continue
            if b.name in ("Sol", "Lua"):
                radius = max(5.0, b.angular_radius * scale)
                specials.append((b, float(x[0]), float(y[0])))
                out.append((b, float(x[0]), float(y[0]), 2.0 * radius))
                continue
            size = float(np.clip(9.0 - 1.1 * b.magnitude, 3.5, 14.0))
            dim = 0.25 if b.alt < 0 else 1.0
            rows.append([x[0], y[0], size, *b.color, dim])
            out.append((b, float(x[0]), float(y[0]), size))
        if rows:
            self.renderer.draw_points(np.array(rows, dtype=np.float32))
        for b, cx, cy in specials:
            if b.name == "Sol":
                self._draw_sun(b, cx, cy)
            else:
                self._draw_moon(b, cx, cy, m, t)
        return out

    def _screen_north_east(self, u_icrs: np.ndarray, m: np.ndarray,
                           cx: float, cy: float):
        """Direções norte e leste celestes na tela, na posição dada (ICRS)."""
        pole = np.array([0.0, 0.0, 1.0])
        n_t = pole - np.dot(pole, u_icrs) * u_icrs
        norm = np.linalg.norm(n_t)
        n_t = n_t / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])
        e_t = np.cross(pole, u_icrs)
        e_t /= max(np.linalg.norm(e_t), 1e-9)
        pts = np.stack([u_icrs + 1e-4 * n_t, u_icrs + 1e-4 * e_t])
        pts /= np.linalg.norm(pts, axis=1, keepdims=True)
        px, py, _ = self._to_screen(pts @ m.astype(np.float64).T, margin=1e9)
        n_scr = np.array([px[0] - cx, py[0] - cy])
        e_scr = np.array([px[1] - cx, py[1] - cy])
        n_scr /= max(np.linalg.norm(n_scr), 1e-9)
        e_scr /= max(np.linalg.norm(e_scr), 1e-9)
        return n_scr, e_scr

    def _draw_sun(self, b, cx: float, cy: float) -> None:
        radius = max(5.0, b.angular_radius * self.camera.pixel_scale)
        # halo suave + disco
        halo = np.array(
            [[cx, cy, radius * 7.0, 1.0, 0.93, 0.72, 0.30]], dtype=np.float32
        )
        self.renderer.draw_points(halo)
        ang = np.linspace(0.0, 2.0 * math.pi, 49)
        disc = np.column_stack(
            [cx + radius * np.cos(ang), cy + radius * np.sin(ang)]
        )
        self.renderer.fill_polygons([disc], (1.0, 0.97, 0.86, 1.0))

    def _draw_moon(self, b, cx: float, cy: float, m: np.ndarray, t) -> None:
        """Disco lunar com a fase atual: lado escuro tênue + região iluminada.

        O terminadouro é a meia-elipse de semieixo R·cos(i) (i = ângulo de
        fase); o limbo brilhante aponta para o Sol (ângulo de posição χ
        calculado com as coordenadas equatoriais de Sol e Lua).
        """
        cam = self.camera
        radius = max(5.0, b.angular_radius * cam.pixel_scale)

        sun = next(s for s in self.engine.bodies(t) if s.name == "Sol")
        m64 = m.astype(np.float64)
        u_moon = m64.T @ b.vec
        u_sun = m64.T @ sun.vec
        d_m = math.asin(max(-1.0, min(1.0, u_moon[2])))
        a_m = math.atan2(u_moon[1], u_moon[0])
        d_s = math.asin(max(-1.0, min(1.0, u_sun[2])))
        a_s = math.atan2(u_sun[1], u_sun[0])
        da = a_s - a_m
        # Ângulo de posição do limbo brilhante (do norte, para leste)
        chi = math.atan2(
            math.cos(d_s) * math.sin(da),
            math.sin(d_s) * math.cos(d_m)
            - math.cos(d_s) * math.sin(d_m) * math.cos(da),
        )
        n_scr, e_scr = self._screen_north_east(u_moon, m, cx, cy)
        u2 = math.cos(chi) * n_scr + math.sin(chi) * e_scr  # p/ limbo brilhante
        v2 = np.array([-u2[1], u2[0]])

        c = np.array([cx, cy])
        ang = np.linspace(-math.pi / 2, math.pi / 2, 25)
        limb = c + radius * (
            np.outer(np.cos(ang), u2) + np.outer(np.sin(ang), v2)
        )
        i = b.phase_angle
        ang2 = np.linspace(math.pi / 2, -math.pi / 2, 25)
        term = (
            c
            + np.outer(-radius * math.cos(i) * np.cos(ang2), u2)
            + np.outer(radius * np.sin(ang2), v2)
        )
        lit = np.vstack([limb, term])

        ang3 = np.linspace(0.0, 2.0 * math.pi, 49)
        disc = np.column_stack(
            [cx + radius * np.cos(ang3), cy + radius * np.sin(ang3)]
        )
        self.renderer.fill_polygons([disc], (0.16, 0.17, 0.19, 0.75))
        self.renderer.fill_polygons([lit], (0.94, 0.93, 0.87, 1.0))

    # ------------------------------------------------------------------
    def _draw_labels(self, painter: QPainter, dpr: float, star_px, bodies_px,
                     dso_px=None, ground_on: bool = False):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QFontMetrics

        painter.setRenderHint(QPainter.TextAntialiasing)
        placer = _LabelPlacer()
        self._label_hits = []

        # pontos cardeais (prioridade máxima)
        if self.layers["cardinals"]:
            font = QFont("Segoe UI", 11, QFont.Bold)
            painter.setFont(font)
            painter.setPen(
                QColor(170, 80, 20) if self.chart_mode else QColor(230, 140, 60)
            )
            fm = QFontMetrics(font)
            for name, vec in self.cardinals:
                x, y, vis = self.camera.project(vec[np.newaxis, :])
                if vis[0]:
                    tx, ty = int(x[0] / dpr) - 8, int(y[0] / dpr) - 6
                    placer.place(tx, ty, fm.horizontalAdvance(name),
                                 fm.height(), force=True)
                    painter.drawText(tx, ty, name)

        # datas e eventos das trajetórias planetárias (item 8)
        if self._path_marks:
            from ..core.planetpath import EVENT_LABEL

            font_small = QFont("Segoe UI", 7)
            painter.setFont(font_small)
            fm_s = QFontMetrics(font_small)
            for path, px, py, vis, color, marks in self._path_marks:
                pen = QColor(
                    int(color[0] * 255), int(color[1] * 255),
                    int(color[2] * 255),
                )
                painter.setPen(pen)
                for i in marks:
                    when = path.points[i].when_utc.astimezone()
                    text = when.strftime("%d/%m")
                    w_t, h_t = fm_s.horizontalAdvance(text), fm_s.height()
                    tx, ty = int(px[i] / dpr) + 5, int(py[i] / dpr) - 4
                    if placer.place(tx, ty, w_t, h_t):
                        painter.drawText(tx, ty, text)
                # eventos: rótulo destacado
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                for ev in path.events:
                    xe, ye, ve = self.camera.project(
                        self._refract(ev.vec[np.newaxis, :]), margin=40.0
                    )
                    if not ve[0]:
                        continue
                    label = (
                        f"{path.name}: {EVENT_LABEL.get(ev.kind, ev.kind)} "
                        f"{ev.when_utc.astimezone():%d/%m}"
                    )
                    if ev.kind.startswith("elong"):
                        label += f" ({ev.value:.0f}°)"
                    tx, ty = int(xe[0] / dpr) + 8, int(ye[0] / dpr) + 14
                    painter.setPen(QColor(20, 22, 28))
                    painter.drawText(tx + 1, ty + 1, label)
                    painter.setPen(pen)
                    painter.drawText(tx, ty, label)
                painter.setFont(font_small)

        # nomes das constelações (item 5: português, latim ou abreviado)
        if (self.layers.get("const_names") and self.const_label_mode != "none"
                and len(self.const_centers)):
            from ..catalogs.constnames import label_for

            m_const = self.engine.horizontal_matrix(
                self.engine.time.current()
            ).astype(np.float32)
            cv = self.const_centers @ m_const.T
            cx_, cy_, cvis = self.camera.project(cv, margin=40.0)
            font = QFont("Segoe UI", 10, QFont.DemiBold)
            painter.setFont(font)
            fm = QFontMetrics(font)
            pen = (QColor(70, 90, 120) if self.chart_mode
                   else QColor(120, 150, 190))
            painter.setPen(pen)
            for i, info in enumerate(self.const_info):
                if not cvis[i]:
                    continue
                if ground_on and cv[i, 2] < 0:
                    continue
                text = label_for(
                    info.get("id", ""), self.const_label_mode,
                    info.get("name", ""),
                )
                w_text, h_text = fm.horizontalAdvance(text), fm.height()
                tx = int(cx_[i] / dpr) - w_text // 2
                ty = int(cy_[i] / dpr)
                if placer.place(tx, ty, w_text, h_text):
                    painter.drawText(tx, ty, text)

        # nomes dos corpos do Sistema Solar
        if self.layers["planet_names"] and bodies_px:
            font = QFont("Segoe UI", 9, QFont.DemiBold)
            painter.setFont(font)
            fm = QFontMetrics(font)
            for b, x, y, size in bodies_px:
                if ground_on and b.alt < 0:
                    continue
                if self.chart_mode:
                    pen = QColor(20, 20, 20)
                else:
                    pen = QColor(95, 92, 82) if b.alt < 0 else QColor(235, 225, 200)
                painter.setPen(pen)
                tx = int(x / dpr) + int(size / dpr / 2) + 5
                ty = int(y / dpr) - 5
                w_text, h_text = fm.horizontalAdvance(b.name), fm.height()
                placer.place(tx, ty, w_text, h_text, force=True)
                painter.drawText(tx, ty, b.name)
                self._label_hits.append(
                    (QRect(tx, ty - h_text, w_text, h_text), ("body", b.name))
                )

        # nomes de estrelas
        if self.layers["star_names"] and star_px is not None:
            idx, x, y, below_map = star_px
            cat = self.stars
            name_lim = max(1.6, min(7.5, self._mag_limit() - 5.0))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            fm = QFontMetrics(font)
            if self.chart_mode:
                pen_up, pen_down = QColor(30, 30, 30), QColor(160, 160, 160)
            else:
                pen_up, pen_down = QColor(170, 185, 210), QColor(70, 78, 92)
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
                below = bool(below_map.get(int(si)))
                if ground_on and below:
                    continue
                label = cat.label(int(si), self.name_mode)
                if not label:
                    continue
                tx = int(x[si] / dpr) + 7
                ty = int(y[si] / dpr) - 5
                w_text, h_text = fm.horizontalAdvance(label), fm.height()
                if not placer.place(tx, ty, w_text, h_text):
                    continue
                painter.setPen(pen_down if below else pen_up)
                painter.drawText(tx, ty, label)
                self._label_hits.append(
                    (QRect(tx, ty - h_text, w_text, h_text), ("star", int(si)))
                )
                shown += 1
                if shown >= 70:
                    break

        # rótulos de céu profundo (item 10: número de catálogo ou nome).
        # Messier e Caldwell aparecem SEMPRE e em negrito (pedido do usuário).
        if self.layers["dso_names"] and dso_px is not None:
            from PySide6.QtCore import QRect

            idx, x, y, maj_px, below_arr = dso_px
            dso = self.dso
            label_lim = self._mag_limit() - 1.8
            font = QFont("Segoe UI", 8)
            font_mc = QFont("Segoe UI", 9, QFont.Bold)
            fm = QFontMetrics(font)
            fm_mc = QFontMetrics(font_mc)
            if self.chart_mode:
                pen_up, pen_mc, pen_down = (
                    QColor(40, 40, 40), QColor(0, 0, 0), QColor(150, 150, 150)
                )
            else:
                pen_up, pen_mc, pen_down = (
                    QColor(150, 168, 190), QColor(235, 226, 190),
                    QColor(64, 70, 82),
                )
            shown = 0
            # duas passadas: M/C primeiro (prioridade), depois os demais
            order = sorted(idx, key=lambda i: not bool(dso.is_mc[i]))
            for i in order:
                is_mc = bool(dso.is_mc[i])
                if not is_mc and shown >= 30:
                    continue
                if not (is_mc or dso.mag[i] <= label_lim or maj_px[i] > 30.0):
                    continue
                below = bool(below_arr[i])
                if ground_on and below:
                    continue
                text = dso.label(
                    int(i), self.dso_name_mode, self.prefer_caldwell
                )
                metrics = fm_mc if is_mc else fm
                w_text, h_text = metrics.horizontalAdvance(text), metrics.height()
                off = int(max(8.0, min(14.0, maj_px[i] * 0.5)) / dpr)
                tx = int(x[i] / dpr) + off
                ty = int(y[i] / dpr) - off + 4
                if not placer.place(tx, ty, w_text, h_text, force=is_mc):
                    continue
                painter.setFont(font_mc if is_mc else font)
                painter.setPen(
                    pen_down if below else (pen_mc if is_mc else pen_up)
                )
                painter.drawText(tx, ty, text)
                # rótulo clicável seleciona o objeto (pedido do usuário)
                self._label_hits.append(
                    (QRect(tx, ty - h_text, w_text, h_text),
                     ("dso", int(dso.ids[i])))
                )
                if not is_mc:
                    shown += 1

    # ------------------------------------------------------------------
    def _selection_screen_pos(self, m: np.ndarray):
        """Posição em pixels (device) da seleção atual, ou None se invisível."""
        if self.selection is None:
            return None
        kind, key = self.selection
        if kind == "star":
            vec = (self.stars.xyz[int(key)] @ m.T)[np.newaxis, :]
            x, y, vis = self._to_screen(vec)
            return (float(x[0]), float(y[0])) if vis[0] else None
        if kind == "dso":
            row = self.dso.row_of(int(key))
            if row is None:
                return None
            vec = (self.dso.xyz[row] @ m.T)[np.newaxis, :]
            x, y, vis = self._to_screen(vec)
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

    def _selection_vec(self, selection, m: np.ndarray, t):
        """Vetor horizontal (sem refração) do objeto da seleção, ou None."""
        kind, key = selection
        if kind == "star":
            return self.stars.xyz[int(key)] @ m.T
        if kind == "dso":
            row = self.dso.row_of(int(key))
            if row is not None:
                return self.dso.xyz[row] @ m.T
            data = self.dso.get(int(key))  # objeto desabilitado ainda é válido
            if data is None:
                return None
            cd = math.cos(data["dec"])
            icrs = np.array(
                [cd * math.cos(data["ra"]), cd * math.sin(data["ra"]),
                 math.sin(data["dec"])]
            )
            return icrs @ m.T
        state = next(
            (s for s in self.engine.bodies(t) if s.name == key), None
        )
        return state.vec if state is not None else None

    def goto_object(self, selection, animate: bool = True) -> None:
        """Seleciona e centraliza a câmera no objeto (busca / 'ir para')."""
        t = self.engine.time.current()
        m = self.engine.horizontal_matrix(t).astype(np.float32)
        vec = self._selection_vec(selection, m, t)
        if vec is None:
            return
        if selection != self.selection:
            self.selection = selection
            self.selectionChanged.emit(selection)
        alt1 = math.asin(max(-1.0, min(1.0, float(vec[2]))))
        az1 = math.atan2(float(vec[1]), float(vec[0]))
        cam = self.camera
        if self._goto_anim is not None:
            self._goto_anim.stop()
        if not animate:
            cam.set_direction(az1, alt1)
            self.update()
            return
        az0, alt0 = cam.az, cam.alt
        daz = _wrap_pi(az1 - az0)
        dalt = alt1 - alt0
        anim = QVariantAnimation(self)
        anim.setDuration(650)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def step(v: float) -> None:
            cam.set_direction(az0 + daz * v, alt0 + dalt * v)
            self.update()

        anim.valueChanged.connect(step)
        anim.start()
        self._goto_anim = anim

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
    def _draw_fov_labels(self, painter: QPainter, dpr: float) -> None:
        """Legenda dos campos de visão ativos (canto inferior esquerdo)."""
        if not self.fov_shapes:
            return
        painter.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        colors = [
            QColor(90, 240, 165), QColor(240, 190, 90), QColor(190, 140, 240),
        ]
        y = int(self.height() - 10 - 14 * len(self.fov_shapes))
        for i, shape in enumerate(self.fov_shapes):
            w = math.degrees(shape.width)
            h = math.degrees(shape.height)
            size = (
                f"{w:.2f}°" if shape.kind == "circle"
                else f"{w:.2f}° × {h:.2f}°"
            )
            text = f"{shape.label} — {size}"
            painter.setPen(QColor(10, 12, 16) if not self.chart_mode
                           else QColor(255, 255, 255))
            painter.drawText(13, y + 14 * i + 1, text)
            painter.setPen(colors[i % len(colors)])
            painter.drawText(12, y + 14 * i, text)

    def _draw_tools_overlay(self, painter: QPainter, dpr: float) -> None:
        """Régua angular e retângulo de zoom (coordenadas lógicas)."""
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtGui import QPen

        if self._measure and self._measure.get("b") is not None:
            a, b = self._measure["a"], self._measure["b"]
            sep = math.degrees(
                math.acos(max(-1.0, min(1.0, float(np.dot(a["vec"], b["vec"])))))
            )
            pa_x, pa_y = a["x"] / dpr, a["y"] / dpr
            pb_x, pb_y = b["x"] / dpr, b["y"] / dpr
            pen = QPen(QColor(255, 200, 90), 1.4)
            painter.setPen(pen)
            painter.drawLine(int(pa_x), int(pa_y), int(pb_x), int(pb_y))
            for px, py in ((pa_x, pa_y), (pb_x, pb_y)):
                painter.drawEllipse(QPoint(int(px), int(py)), 4, 4)
            if sep < 1.0:
                text = f"{sep * 60:.1f}′"
            elif sep < 10.0:
                text = f"{sep:.2f}°"
            else:
                text = f"{sep:.1f}°"
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            mx, my = int((pa_x + pb_x) / 2) + 8, int((pa_y + pb_y) / 2) - 8
            painter.setPen(QColor(20, 20, 20))
            painter.drawText(mx + 1, my + 1, text)
            painter.setPen(QColor(255, 210, 110))
            painter.drawText(mx, my, text)

        if self._rubber is not None:
            x0, y0, x1, y1 = self._rubber
            rect = QRect(
                QPoint(int(min(x0, x1) / dpr), int(min(y0, y1) / dpr)),
                QPoint(int(max(x0, x1) / dpr), int(max(y0, y1) / dpr)),
            )
            painter.setPen(QPen(QColor(120, 200, 255), 1.2, Qt.DashLine))
            painter.setBrush(QColor(120, 200, 255, 28))
            painter.drawRect(rect)
            painter.setBrush(Qt.NoBrush)

    def _zoom_to_rect(self, x0, y0, x1, y1) -> None:
        """Ajusta a câmera ao retângulo selecionado (zoom por área)."""
        cam = self.camera
        if abs(x1 - x0) < 12 or abs(y1 - y0) < 12:
            return
        v_center = cam.unproject((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        alt = math.asin(max(-1.0, min(1.0, float(v_center[2]))))
        az = math.atan2(float(v_center[1]), float(v_center[0]))
        # ângulo vertical coberto pelo retângulo -> novo FOV
        v_top = cam.unproject((x0 + x1) / 2.0, min(y0, y1))
        v_bot = cam.unproject((x0 + x1) / 2.0, max(y0, y1))
        ang = math.acos(max(-1.0, min(1.0, float(np.dot(v_top, v_bot)))))
        cam.set_direction(az, alt)
        cam.fov = max(FOV_MIN, min(FOV_MAX, ang if ang > 1e-4 else cam.fov))
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
        if event.button() != Qt.LeftButton:
            return
        if self._goto_anim is not None:
            self._goto_anim.stop()
        x, y = self._device_pos(event)
        self._press_pos = (x, y)

        if self.mouse_mode == "measure":
            point = {"x": x, "y": y, "vec": self.camera.unproject(x, y)}
            if self._measure is None or self._measure.get("b") is not None:
                self._measure = {"a": point, "b": None}
            else:
                self._measure["b"] = point
            self.update()
            return
        if self.mouse_mode == "zoom_rect":
            self._rubber = [x, y, x, y]
            self.update()
            return

        self._drag_anchor = self.camera.screen_to_altaz(x, y)
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        x, y = self._device_pos(event)
        self._cursor_altaz = self.camera.screen_to_altaz(x, y)

        if self.mouse_mode == "zoom_rect" and self._rubber is not None:
            self._rubber[2], self._rubber[3] = x, y
            self.update()
            return
        if (self.mouse_mode == "measure" and self._measure is not None
                and self._measure.get("b") is None):
            # pré-visualiza a medição enquanto o segundo ponto não é fixado
            self._measure["b"] = {
                "x": x, "y": y, "vec": self.camera.unproject(x, y),
            }
            self.update()
            self._measure["b"] = None
            return

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
        if event.button() != Qt.LeftButton:
            return
        x, y = self._device_pos(event)

        if self.mouse_mode == "zoom_rect" and self._rubber is not None:
            x0, y0, _, _ = self._rubber
            self._rubber = None
            self._zoom_to_rect(x0, y0, x, y)
            self._press_pos = None
            return
        if self.mouse_mode == "measure":
            self._press_pos = None
            return

        self._drag_anchor = None
        self.setCursor(Qt.ArrowCursor)
        if self._press_pos is not None:
            dx = x - self._press_pos[0]
            dy = y - self._press_pos[1]
            if dx * dx + dy * dy <= 36.0:  # clique, não arrasto
                dpr = self.devicePixelRatioF()
                hit = self._label_at(x / dpr, y / dpr)
                if hit is not None:
                    if hit != self.selection:
                        self.selection = hit
                        self.selectionChanged.emit(hit)
                    self.update()
                else:
                    self._pick_at(x, y)
        self._press_pos = None

    def _label_at(self, lx: float, ly: float):
        """Seleção associada a um rótulo sob o cursor (coords. lógicas)."""
        for rect, selection in self._label_hits:
            if rect.adjusted(-2, -2, 2, 2).contains(int(lx), int(ly)):
                return selection
        return None

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
