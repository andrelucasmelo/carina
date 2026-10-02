"""Carta celeste para impressão: especificação e moldura (v0.16 T3).

:class:`ChartSpec` descreve uma carta — enquadramento, papel, tema,
conteúdo e moldura — e se converte em :class:`RenderOptions` para o render
fora da tela (ADR-044). :func:`compose_page` monta a página: título e
subtítulo, o mapa (com rotação opcional), bússola com o norte e o leste
celestes, escala angular, legenda de símbolos e rodapé.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

PAPERS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "Carta": (279.4, 215.9)}
FRAMINGS = {"view": "Vista atual", "object": "Objeto selecionado",
            "constellation": "Constelação inteira", "field": "Campo do equipamento"}

# (chave da camada no SkyWidget, rótulo no diálogo, padrão)
CONTENT_LAYERS = [
    ("stars", "Estrelas", True),
    ("const_lines", "Linhas das constelações", True),
    ("const_bounds", "Fronteiras das constelações", False),
    ("const_names", "Nomes das constelações", True),
    ("grid_eq", "Grade equatorial", False),
    ("grid_altaz", "Grade horizontal", False),
    ("ecliptic", "Eclíptica", False),
    ("equator", "Equador celeste", False),
    ("meridian", "Meridiano", False),
    ("ground", "Solo e horizonte", False),
    ("milkyway", "Via Láctea", True),
    ("dso", "Céu profundo", True),
    ("dso_images", "Imagens do levantamento", False),
    ("planets", "Planetas, Sol e Lua", True),
    ("cardinals", "Pontos cardeais", False),
]


@dataclass
class ChartSpec:
    """Tudo o que define uma carta impressa (serializável em JSON)."""

    title: str = "Carta celeste"
    subtitle: str = ""                 # vazio = local · data · campo
    framing: str = "view"              # view | object | constellation | field
    target: str = ""                   # identidade (objeto) ou sigla (constelação)
    fov_deg: float = 40.0
    rotation_deg: float = 0.0
    paper: str = "A4"
    landscape: bool = True
    margin_mm: float = 10.0
    theme: str = "light"               # light | dark | red
    star_mag: float = 6.5
    name_mag: float = 2.5
    layers: dict = field(default_factory=lambda: {k: v for k, _l, v in CONTENT_LAYERS})
    dso_preset: str = "Padrão"
    dso_name_mode: str = "number"      # number | name
    const_label_mode: str = "pt"       # pt | latin | abbr
    show_fov: bool = False
    show_marker: bool = False
    show_title: bool = True
    show_compass: bool = True
    show_scale: bool = True
    show_legend: bool = True
    show_footer: bool = True
    dpi: int = 200

    # -- papel ---------------------------------------------------------
    def page_mm(self) -> tuple[float, float]:
        w, h = PAPERS.get(self.paper, PAPERS["A4"])
        return (w, h) if self.landscape else (h, w)

    def page_px(self, dpi: int | None = None) -> tuple[int, int]:
        d = dpi or self.dpi
        w, h = self.page_mm()
        return int(round(w / 25.4 * d)), int(round(h / 25.4 * d))

    # -- serialização --------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text) -> "ChartSpec":
        data = json.loads(text) if isinstance(text, str) else dict(text or {})
        spec = cls()
        for key, value in data.items():
            if hasattr(spec, key):
                if key == "layers":
                    merged = dict(spec.layers)
                    merged.update({k: bool(v) for k, v in (value or {}).items()})
                    value = merged
                setattr(spec, key, value)
        return spec

    # -- render --------------------------------------------------------
    def render_options(self, base):
        """:class:`RenderOptions` da carta a partir das opções atuais.

        Camadas fora da lista de conteúdo (atmosfera, zona da Lua, caminhos
        dos planetas…) ficam desligadas; o céu é sempre o de Bortle 1 e as
        estrelas vão até ``star_mag`` exatamente, sem o ajuste pelo zoom.
        """
        import dataclasses

        from ..core.dsofilter import PRESETS, DsoFilter

        layers = {k: False for k in base.layers}
        for key, value in self.layers.items():
            layers[key] = bool(value)
        if layers.get("ground"):
            layers["horizon"] = True
        # rótulos acompanham as camadas; refração como o céu de verdade
        layers["star_names"] = layers.get("stars", False) and self.name_mag > -1.5
        layers["dso_names"] = layers.get("dso", False)
        layers["planet_names"] = layers.get("planets", False)
        layers["refraction"] = True
        layers["below_horizon"] = not layers.get("ground", False)
        flt = PRESETS.get(self.dso_preset)
        flt_json = flt.to_json() if isinstance(flt, DsoFilter) else base.dso_filter
        const_mode = self.const_label_mode if self.layers.get("const_names") else "none"
        return dataclasses.replace(
            base, layers=layers, chart_mode=self.theme == "light", bortle=1,
            mag_cap=None, mag_fixed=float(self.star_mag),
            label_mag_cap=float(self.name_mag), dso_name_mode=self.dso_name_mode,
            const_label_mode=const_mode, dso_filter=flt_json, theme=self.theme,
        )


@dataclass
class ChartInfo:
    """Dados do quadro renderizado que a moldura precisa."""

    location: str = ""
    when_text: str = ""
    fov_deg: float = 40.0
    north_deg: float = 0.0       # ângulo do norte celeste a partir do "para cima", horário
    east_deg: float = -90.0      # idem para o leste celeste
    px_per_deg: float = 10.0     # pixels do mapa renderizado por grau, no centro
    map_px: tuple[int, int] = (1, 1)


# ---------------------------------------------------------------------------
# Moldura
# ---------------------------------------------------------------------------

FRAME_COLORS = {
    "light": {"bg": (255, 255, 255), "ink": (20, 22, 28), "muted": (100, 106, 118),
              "accent": (190, 40, 40), "line": (120, 126, 138)},
    "dark": {"bg": (8, 12, 24), "ink": (225, 230, 242), "muted": (140, 152, 176),
             "accent": (255, 120, 110), "line": (90, 102, 128)},
    "red": {"bg": (0, 0, 0), "ink": (215, 22, 14), "muted": (140, 14, 9),
            "accent": (255, 24, 16), "line": (110, 14, 9)},
}


def layout(spec: ChartSpec, page_w: int, page_h: int) -> dict:
    """Retângulos (x, y, w, h) da página em pixels: título, mapa, legenda e
    rodapé. O mapa ocupa o que sobra."""
    unit = page_w / 297.0 if spec.landscape else page_h / 297.0   # px por mm (aprox.)
    m = spec.margin_mm * page_w / spec.page_mm()[0]
    title_h = (14.0 * unit) if spec.show_title else 0.0
    foot_h = (6.0 * unit) if spec.show_footer else 0.0
    legend_w = (46.0 * unit) if spec.show_legend else 0.0
    gap = 3.0 * unit
    map_x = m
    map_y = m + title_h + (gap if title_h else 0)
    map_w = page_w - 2 * m - (legend_w + gap if legend_w else 0)
    map_h = page_h - map_y - m - (foot_h + gap if foot_h else 0)
    return {
        "unit": unit, "margin": m,
        "title": (m, m, page_w - 2 * m, title_h),
        "map": (map_x, map_y, max(10.0, map_w), max(10.0, map_h)),
        "legend": (page_w - m - legend_w, map_y, legend_w, map_h),
        "footer": (m, page_h - m - foot_h, page_w - 2 * m, foot_h),
    }


def map_render_size(spec: ChartSpec, page_w: int, page_h: int,
                    scale: float = 1.0) -> tuple[int, int]:
    """Tamanho lógico do quadro a renderizar para preencher o mapa.

    Com rotação, renderiza o quadrado que contém o retângulo girado, para
    os cantos não ficarem vazios.
    """
    _x, _y, w, h = layout(spec, page_w, page_h)["map"]
    if spec.rotation_deg % 360:
        side = math.hypot(w, h)
        w = h = side
    return max(1, int(w / scale)), max(1, int(h / scale))


def nice_degrees(px_per_deg: float, target_px: float) -> float:
    """Comprimento redondo da barra de escala (em graus) perto do alvo."""
    for deg in (0.25, 0.5, 1, 2, 5, 10, 15, 20, 30, 45, 60):
        if deg * px_per_deg >= target_px:
            return deg
    return 90.0


def compose_page(map_img, spec: ChartSpec, info: ChartInfo, page_size=None):
    """Monta a página inteira (``QImage``) com o mapa e a moldura."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

    W, H = page_size or spec.page_px()
    col = {k: QColor(*v) for k, v in FRAME_COLORS.get(spec.theme,
                                                        FRAME_COLORS["light"]).items()}
    page = QImage(W, H, QImage.Format_RGB32)
    page.fill(col["bg"])
    lay = layout(spec, W, H)
    u = lay["unit"]
    p = QPainter(page)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)

    def font(mm: float, bold: bool = False) -> QFont:
        f = QFont("Segoe UI")
        f.setPixelSize(max(6, int(mm * u)))
        f.setBold(bold)
        return f

    # --- mapa (com rotação opcional) -------------------------------------
    mx, my, mw, mh = lay["map"]
    rect = QRectF(mx, my, mw, mh)
    p.save()
    p.setClipRect(rect)
    p.translate(rect.center())
    p.rotate(spec.rotation_deg)
    iw, ih = map_img.width(), map_img.height()
    k = max(mw / iw, mh / ih) if spec.rotation_deg % 360 else min(mw / iw, mh / ih)
    p.drawImage(QRectF(-iw * k / 2, -ih * k / 2, iw * k, ih * k), map_img)
    p.restore()
    p.setPen(QPen(col["line"], max(1.0, 0.3 * u)))
    p.setBrush(Qt.NoBrush)
    p.drawRect(rect)
    px_per_deg_page = info.px_per_deg * k

    # --- título ------------------------------------------------------------
    if spec.show_title:
        tx, ty, tw, th = lay["title"]
        p.setPen(col["ink"])
        p.setFont(font(7.0, True))
        p.drawText(QRectF(tx, ty, tw, th * 0.62), Qt.AlignLeft | Qt.AlignVCenter,
                   spec.title or "Carta celeste")
        sub = spec.subtitle or " · ".join(x for x in (
            info.location, info.when_text, f"campo {info.fov_deg:.0f}°") if x)
        p.setPen(col["muted"])
        p.setFont(font(3.4))
        p.drawText(QRectF(tx, ty + th * 0.6, tw, th * 0.4), Qt.AlignLeft | Qt.AlignVCenter,
                   sub)

    # --- bússola (norte e leste celestes) ---------------------------------
    if spec.show_compass:
        arm = 9.0 * u
        cx, cy = rect.right() - arm * 1.7, rect.top() + arm * 1.7
        p.setPen(QPen(col["line"], max(1.0, 0.25 * u)))
        bgc = QColor(col["bg"])
        bgc.setAlpha(215)
        p.setBrush(bgc)
        p.drawEllipse(QPointF(cx, cy), arm * 1.45, arm * 1.45)
        for ang, label, colr in ((info.north_deg + spec.rotation_deg, "N", col["accent"]),
                                 (info.east_deg + spec.rotation_deg, "L", col["ink"])):
            a = math.radians(ang)
            ex, ey = cx + arm * math.sin(a), cy - arm * math.cos(a)
            p.setPen(QPen(colr, max(1.5, 0.45 * u)))
            p.drawLine(QPointF(cx, cy), QPointF(ex, ey))
            p.setFont(font(3.2, True))
            p.setPen(colr)
            lx, ly = cx + arm * 1.22 * math.sin(a), cy - arm * 1.22 * math.cos(a)
            p.drawText(QRectF(lx - 3 * u, ly - 2.5 * u, 6 * u, 5 * u), Qt.AlignCenter, label)

    # --- escala angular ------------------------------------------------------
    if spec.show_scale and px_per_deg_page > 0:
        deg = nice_degrees(px_per_deg_page, mw * 0.14)
        length = deg * px_per_deg_page
        x0, y0 = rect.left() + 5 * u, rect.bottom() - 6 * u
        bgc = QColor(col["bg"])
        bgc.setAlpha(200)
        p.fillRect(QRectF(x0 - 2 * u, y0 - 6 * u, length + 4 * u, 9 * u), bgc)
        p.setPen(QPen(col["ink"], max(1.5, 0.4 * u)))
        p.drawLine(QPointF(x0, y0), QPointF(x0 + length, y0))
        for x in (x0, x0 + length):
            p.drawLine(QPointF(x, y0 - 1.5 * u), QPointF(x, y0 + 1.5 * u))
        p.setFont(font(3.0))
        label = f"{deg:g}°".replace(".", ",")
        p.drawText(QRectF(x0, y0 - 6 * u, length, 4 * u), Qt.AlignCenter, label)

    # --- legenda -------------------------------------------------------------
    if spec.show_legend:
        _draw_legend(p, lay["legend"], u, col, spec, font)

    # --- rodapé --------------------------------------------------------------
    if spec.show_footer:
        fx, fy, fw, fh = lay["footer"]
        p.setPen(col["muted"])
        p.setFont(font(2.6))
        p.drawText(QRectF(fx, fy, fw, fh), Qt.AlignLeft | Qt.AlignVCenter,
                   "Carina — planetário de código aberto · norte e leste celestes "
                   "indicados na bússola")
        p.drawText(QRectF(fx, fy, fw, fh), Qt.AlignRight | Qt.AlignVCenter,
                   f"estrelas até mag {spec.star_mag:.1f}".replace(".", ","))
    p.end()
    return page


def _draw_legend(p, rect, u, col, spec, font) -> None:
    """Coluna de legenda: magnitudes das estrelas e símbolos de céu profundo."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QPen

    x, y, w, h = rect
    p.setPen(col["ink"])
    p.setFont(font(3.6, True))
    p.drawText(QRectF(x, y, w, 6 * u), Qt.AlignLeft | Qt.AlignVCenter, "Legenda")
    y += 8 * u
    if spec.layers.get("stars", True):
        p.setFont(font(3.0, True))
        p.drawText(QRectF(x, y, w, 5 * u), Qt.AlignLeft | Qt.AlignVCenter, "Estrelas")
        y += 6 * u
        p.setFont(font(2.8))
        top = int(math.floor(min(spec.star_mag, 7.0)))
        for i, mag in enumerate(range(0, top + 1)):
            cy = y + 2.5 * u
            r = max(0.35 * u, (2.4 - 0.33 * mag) * u)
            p.setPen(col["ink"])
            p.setBrush(col["ink"])
            p.drawEllipse(QPointF(x + 4 * u, cy), r, r)
            p.setBrush(Qt.NoBrush)
            p.drawText(QRectF(x + 9 * u, y, w - 9 * u, 5 * u), Qt.AlignLeft | Qt.AlignVCenter,
                       f"mag {mag}")
            y += 5.2 * u
        y += 3 * u
    if spec.layers.get("dso", True):
        p.setPen(col["ink"])
        p.setFont(font(3.0, True))
        p.drawText(QRectF(x, y, w, 5 * u), Qt.AlignLeft | Qt.AlignVCenter, "Céu profundo")
        y += 6 * u
        p.setFont(font(2.8))
        pen = QPen(col["ink"], max(1.0, 0.3 * u))
        symbols = [("gal", "Galáxia"), ("oc", "Aglomerado aberto"),
                   ("gc", "Aglomerado globular"), ("pn", "Nebulosa planetária"),
                   ("neb", "Nebulosa"), ("dark", "Nebulosa escura")]
        for kind, label in symbols:
            cx, cy, s = x + 4 * u, y + 2.5 * u, 2.2 * u
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            if kind == "gal":
                p.drawEllipse(QPointF(cx, cy), s * 1.3, s * 0.6)
            elif kind == "oc":
                dashed = QPen(pen)
                dashed.setStyle(Qt.DashLine)
                p.setPen(dashed)
                p.drawEllipse(QPointF(cx, cy), s, s)
            elif kind == "gc":
                p.drawEllipse(QPointF(cx, cy), s, s)
                p.drawLine(QPointF(cx - s, cy), QPointF(cx + s, cy))
                p.drawLine(QPointF(cx, cy - s), QPointF(cx, cy + s))
            elif kind == "pn":
                p.drawEllipse(QPointF(cx, cy), s * 0.6, s * 0.6)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    p.drawLine(QPointF(cx + dx * s * 0.6, cy + dy * s * 0.6),
                               QPointF(cx + dx * s * 1.1, cy + dy * s * 1.1))
            elif kind == "neb":
                p.drawRect(QRectF(cx - s, cy - s, 2 * s, 2 * s))
            else:
                dotted = QPen(pen)
                dotted.setStyle(Qt.DotLine)
                p.setPen(dotted)
                p.drawRect(QRectF(cx - s, cy - s, 2 * s, 2 * s))
            p.setPen(col["ink"])
            p.drawText(QRectF(x + 9 * u, y, w - 9 * u, 5 * u), Qt.AlignLeft | Qt.AlignVCenter,
                       label)
            y += 5.6 * u
        y += 2 * u
        p.setFont(font(2.6))
        p.setPen(col["muted"])
        p.drawText(QRectF(x, y, w, 12 * u), Qt.TextWordWrap,
                   "Messier e Caldwell em negrito; tamanho dos símbolos proporcional "
                   "ao do objeto.")
