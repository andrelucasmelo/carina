"""Cartas de localização para o PDF das maratonas.

Cada objeto do roteiro ganha uma pequena carta no estilo do modo de
impressão do Carina — fundo branco, estrelas pretas dimensionadas pela
magnitude, linhas de constelação discretas — com os recursos gráficos de
uma carta de busca de verdade:

* o **alvo** marcado por um círculo duplo vermelho no centro;
* as **estrelas-guia** da rota de star-hopping nomeadas;
* uma **seta tracejada** da guia principal até o alvo (o desenho conta a
  mesma história que o texto "comece por X e caminhe N° para leste");
* barra de escala em graus e a indicação de norte/leste.

A projeção é gnomônica (retas no céu viram retas no papel — ideal para
setas) centrada no ponto médio entre alvo e guia principal, com o campo
dimensionado para caber a rota inteira. A convenção é a das cartas
celestes: norte para cima, **leste à esquerda** (o céu visto de dentro).

Tudo é desenhado com QPainter puro em uma QImage — sem OpenGL — para que a
geração de dezenas de cartas no PDF seja rápida e não dispute o contexto
GL da janela principal.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF,
)

# Paletas das cartas (v0.15): papel branco, escura do Carina e vermelha
# para preservar a visão noturna no campo.
CHART_THEMES = {
    "light": {"bg": QColor(255, 255, 255), "star": QColor(20, 22, 26),
              "const": QColor(150, 158, 170), "target": QColor(196, 40, 40),
              "arrow": QColor(196, 40, 40), "guide": QColor(30, 90, 170),
              "frame": QColor(120, 126, 138), "text": QColor(60, 64, 72),
              "label_bg": QColor(255, 255, 255, 220), "grid": QColor(205, 210, 220)},
    "dark": {"bg": QColor(10, 14, 28), "star": QColor(235, 238, 248),
             "const": QColor(70, 92, 140), "target": QColor(255, 120, 110),
             "arrow": QColor(255, 120, 110), "guide": QColor(120, 185, 255),
             "frame": QColor(90, 102, 128), "text": QColor(190, 200, 222),
             "label_bg": QColor(10, 14, 28, 220), "grid": QColor(40, 52, 80)},
    "red": {"bg": QColor(0, 0, 0), "star": QColor(235, 50, 35),
            "const": QColor(110, 22, 14), "target": QColor(255, 70, 45),
            "arrow": QColor(255, 70, 45), "guide": QColor(200, 55, 35),
            "frame": QColor(120, 22, 14), "text": QColor(215, 55, 40),
            "label_bg": QColor(0, 0, 0, 220), "grid": QColor(70, 12, 8)},
}
_LIGHT = CHART_THEMES["light"]
# nomes antigos (compatibilidade com quem importava as constantes)
COL_STAR, COL_CONST, COL_TARGET = _LIGHT["star"], _LIGHT["const"], _LIGHT["target"]
COL_ARROW, COL_GUIDE, COL_FRAME, COL_TEXT = (_LIGHT["arrow"], _LIGHT["guide"],
                                             _LIGHT["frame"], _LIGHT["text"])


def _unit(ra: float, dec: float) -> np.ndarray:
    """(AR, declinação) em radianos → vetor unitário ICRS."""
    cd = math.cos(dec)
    return np.array([cd * math.cos(ra), cd * math.sin(ra), math.sin(dec)])


class _Gnomonic:
    """Projeção gnomônica centrada em ``center`` (vetor unitário ICRS).

    ``xy(v)`` devolve coordenadas de tela em pixels: y cresce para baixo
    (norte celeste para cima) e x cresce para a DIREITA com o leste à
    esquerda — a convenção de cartas celestes.
    """

    def __init__(self, center: np.ndarray, fov_deg: float, size_px: int):
        self.c = center / np.linalg.norm(center)
        pole = np.array([0.0, 0.0, 1.0])
        north = pole - float(pole @ self.c) * self.c
        n = np.linalg.norm(north)
        if n < 1e-9:                     # carta centrada no polo celeste
            north = np.array([1.0, 0.0, 0.0])
            n = 1.0
        self.north = north / n
        # leste celeste = direção de ascensão reta crescente = polo × centro
        east = np.cross(pole, self.c)
        self.east = east / np.linalg.norm(east)
        # meio campo em unidades do plano tangente -> pixels
        self.scale = (size_px / 2.0) / math.tan(math.radians(fov_deg / 2.0))
        self.half = size_px / 2.0

    def xy(self, v: np.ndarray) -> tuple[float, float] | None:
        """Vetor ICRS → pixels da carta (None se fora do hemisfério útil)."""
        t = float(v @ self.c)
        if t < 0.15:                     # atrás/na borda do plano tangente
            return None
        p = v / t - self.c
        x = self.half - self.scale * float(p @ self.east)   # leste à esquerda
        y = self.half - self.scale * float(p @ self.north)  # norte para cima
        return x, y


def _draw_label_avoiding(p: QPainter, text: str, taken: list,
                         candidates) -> None:
    """Desenha ``text`` na primeira posição (linha de base) cuja caixa não
    cruza nenhuma já ocupada e registra a caixa em ``taken``. Sem posição
    livre, usa a primeira mesmo assim — melhor sobrepor do que omitir a
    referência (revisão 2026-10, D12: rótulo do alvo em cima do da guia).
    """
    fm = p.fontMetrics()
    w, h = fm.horizontalAdvance(text), fm.height()
    chosen = None
    for x, y in candidates:
        box = QRectF(x - 2, y - fm.ascent(), w + 4, h)
        if not any(box.intersects(t) for t in taken):
            chosen = (x, y, box)
            break
    if chosen is None:
        x, y = candidates[0]
        chosen = (x, y, QRectF(x - 2, y - fm.ascent(), w + 4, h))
    x, y, box = chosen
    p.drawText(QPointF(x, y), text)
    taken.append(box)


def render_finder_chart(entry, stars, const_lines, size_px: int = 460,
                        theme: str = "light") -> QImage:
    """Desenha a carta de localização de uma entrada do roteiro.

    ``entry`` é um :class:`~carina.core.observing.PlanEntry` (usa ra/dec,
    guides e catalog_id); ``stars`` é o catálogo HYG; ``const_lines`` o
    :class:`PolylineSet` das linhas de constelação (pode ser ``None``).
    """
    pal = CHART_THEMES.get(theme, _LIGHT)
    taken: list = []   # caixas de texto já ocupadas (anticolisão)
    target = _unit(entry.ra, entry.dec)

    # Campo e centro: a carta precisa conter o alvo E as estrelas-guia,
    # senão sobrariam linhas apontando para fora do papel. O centro é a
    # média das direções envolvidas e o campo cobre a mais distante com
    # folga — limitado a 50°, além do que a projeção gnomônica distorce
    # demais nas bordas.
    if entry.guides:
        vecs = [target] + [_unit(g["ra"], g["dec"]) for g in entry.guides]
        center = np.sum(vecs, axis=0)
        norm = np.linalg.norm(center)
        center = center / norm if norm > 1e-9 else target
        spread = max(
            math.degrees(math.acos(max(-1.0, min(1.0, float(v @ center)))))
            for v in vecs
        )
        fov = min(50.0, max(10.0, spread * 2.6))
    else:
        fov = 15.0
        center = target

    proj = _Gnomonic(center, fov, size_px)
    margin = size_px * 0.04

    def inside(pt) -> bool:
        """O ponto cabe na carta com uma margem para o rótulo?"""
        return (pt is not None and margin <= pt[0] <= size_px - margin
                and margin <= pt[1] <= size_px - margin)

    img = QImage(size_px, size_px, QImage.Format_RGB32)
    img.fill(pal["bg"])
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # --- linhas de constelação (orientação de campo) -------------------
    if const_lines is not None:
        p.setPen(QPen(pal["const"], 1.0))
        verts = const_lines.verts
        near = verts @ proj.c > math.cos(math.radians(fov * 0.9))
        for a, b in const_lines.segments:
            if not (near[a] or near[b]):
                continue
            pa = proj.xy(verts[a])
            pb = proj.xy(verts[b])
            if pa and pb:
                p.drawLine(QPointF(*pa), QPointF(*pb))

    # --- estrelas até uma magnitude adequada ao campo -------------------
    # campo maior → corte mais raso, como numa carta impressa de atlas
    mag_lim = 8.6 - 0.075 * fov
    count = stars.count_brighter_than(mag_lim)
    sub = stars.xyz[:count]
    mags = stars.mag[:count]
    near = sub @ proj.c > math.cos(math.radians(fov * 0.8))
    p.setPen(Qt.NoPen)
    p.setBrush(pal["star"])
    for i in np.nonzero(near)[0]:
        pt = proj.xy(sub[i])
        if pt is None:
            continue
        r = max(0.7, 4.6 - 0.55 * float(mags[i]))
        p.drawEllipse(QPointF(*pt), r, r)

    cx, cy = proj.xy(target) or (proj.half, proj.half)

    # --- setas de cada estrela-guia até o alvo, com a distância em graus -
    # A primeira guia é a rota principal (traço forte); as demais servem
    # para TRIANGULAR o campo, e por isso também ganham linha e medida —
    # o desenho precisa contar a mesma história do texto.
    for k, g in enumerate(entry.guides):
        gp = proj.xy(_unit(g["ra"], g["dec"]))
        if not inside(gp):
            continue          # guia fora do papel: linha apontaria a lugar nenhum
        gx, gy = gp
        dx, dy = cx - gx, cy - gy
        dist = math.hypot(dx, dy)
        if dist < 26:
            continue
        ux, uy = dx / dist, dy / dist
        primary = g.get("primary", k == 0)
        color = pal["arrow"] if primary else pal["guide"]
        p.setPen(QPen(color, 2.0 if primary else 1.1, Qt.DashLine))
        x0, y0 = gx + ux * 12, gy + uy * 12
        x1, y1 = cx - ux * 16, cy - uy * 16
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        if primary:                      # ponta de seta só na rota principal
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            wing = 7.0
            p.drawPolygon(QPolygonF([
                QPointF(x1 + ux * 10, y1 + uy * 10),
                QPointF(x1 - uy * wing, y1 + ux * wing),
                QPointF(x1 + uy * wing, y1 - ux * wing),
            ]))
            p.setBrush(Qt.NoBrush)

        # medida em graus no meio do trecho, deitada sobre a linha e com
        # um fundo branco para não se perder entre as estrelas
        label = f"{g['sep']:.1f}°"
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        fm = p.fontMetrics()
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        w_lbl = fm.horizontalAdvance(label) + 6
        h_lbl = fm.height()
        box = QRectF(mx - w_lbl / 2, my - h_lbl / 2, w_lbl, h_lbl)
        p.fillRect(box, pal["label_bg"])
        p.setPen(color)
        p.drawText(box, Qt.AlignCenter, label)
        taken.append(box)

    # nomes das estrelas-guia
    p.setFont(QFont("Segoe UI", 9, QFont.Bold))
    for g in entry.guides:
        gp = proj.xy(_unit(g["ra"], g["dec"]))
        if not inside(gp):
            continue
        gx, gy = gp
        p.setPen(QPen(pal["guide"], 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(gx, gy), 9.0, 9.0)
        p.setPen(pal["guide"])
        adv = p.fontMetrics().horizontalAdvance(g["name"])
        _draw_label_avoiding(p, g["name"], taken, [
            (gx + 12, gy + 4), (gx - 12 - adv, gy + 4),
            (gx + 12, gy - 12), (gx + 12, gy + 18),
        ])

    # --- alvo: círculo duplo no estilo "finder" -------------------------
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(pal["target"], 2.0))
    p.drawEllipse(QPointF(cx, cy), 11.0, 11.0)
    p.setPen(QPen(pal["target"], 1.2))
    p.drawEllipse(QPointF(cx, cy), 16.0, 16.0)
    p.setPen(pal["target"])
    p.setFont(QFont("Segoe UI", 9, QFont.Bold))
    label = getattr(entry, "designation", entry.catalog_id)
    adv = p.fontMetrics().horizontalAdvance(label)
    _draw_label_avoiding(p, label, taken, [
        (cx + 20, cy - 12), (cx - 20 - adv, cy - 12),
        (cx + 20, cy + 26), (cx - 20 - adv, cy + 26),
    ])

    # --- moldura, escala e orientação -----------------------------------
    p.setPen(QPen(pal["frame"], 1.4))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(0.5, 0.5, size_px - 1.0, size_px - 1.0))

    p.setFont(QFont("Segoe UI", 8))
    p.setPen(pal["text"])
    # barra de escala de 5° (ou 2° em campos pequenos)
    bar_deg = 5.0 if fov >= 18 else 2.0
    bar_px = proj.scale * math.tan(math.radians(bar_deg))
    if bar_px < size_px * 0.6:
        y_bar = size_px - 16.0
        p.drawLine(QPointF(14, y_bar), QPointF(14 + bar_px, y_bar))
        p.drawLine(QPointF(14, y_bar - 4), QPointF(14, y_bar + 4))
        p.drawLine(QPointF(14 + bar_px, y_bar - 4),
                   QPointF(14 + bar_px, y_bar + 4))
        p.drawText(QPointF(14 + bar_px / 2 - 8, y_bar - 8),
                   f"{bar_deg:.0f}°")
    p.drawText(QPointF(size_px - 62, size_px - 8), f"campo {fov:.0f}°")

    _draw_compass(p, size_px, pal)
    p.end()
    return img


def _draw_compass(p: QPainter, size_px: int, pal: dict | None = None) -> None:
    """Rosa de orientação no canto superior direito.

    Uma seta cheia apontando o NORTE celeste (para cima nesta projeção) e
    o eixo leste–oeste, com o leste à ESQUERDA — a convenção das cartas
    celestes, que é o contrário dos mapas terrestres e por isso precisa
    estar explícita no desenho, não só implícita na projeção.
    """
    pal = pal or _LIGHT
    cx, cy = size_px - 40.0, 40.0
    arm = 20.0
    p.setPen(QPen(pal["frame"], 1.0))
    p.setBrush(pal["label_bg"])
    p.drawEllipse(QPointF(cx, cy), arm + 10, arm + 10)

    # eixo leste-oeste (leste à esquerda)
    p.setPen(QPen(pal["text"], 1.0))
    p.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
    p.setFont(QFont("Segoe UI", 7))
    p.drawText(QPointF(cx - arm - 9, cy + 3), "L")
    p.drawText(QPointF(cx + arm + 2, cy + 3), "O")

    # seta do norte: haste + ponta cheia
    p.setPen(QPen(pal["target"], 1.8))
    p.drawLine(QPointF(cx, cy + arm * 0.6), QPointF(cx, cy - arm * 0.55))
    p.setPen(Qt.NoPen)
    p.setBrush(pal["target"])
    p.drawPolygon(QPolygonF([
        QPointF(cx, cy - arm),
        QPointF(cx - 5.0, cy - arm * 0.5),
        QPointF(cx + 5.0, cy - arm * 0.5),
    ]))
    p.setPen(pal["target"])
    p.setFont(QFont("Segoe UI", 8, QFont.Bold))
    p.drawText(QPointF(cx - 4, cy - arm - 3), "N")
    p.setBrush(Qt.NoBrush)


# ---------------------------------------------------------------------------
# Carta geral da noite (v0.15 T13)
# ---------------------------------------------------------------------------

def render_overview_chart(plan, stars, const_lines, size_px: int = 1400,
                          theme: str = "light", when_utc=None) -> QImage:
    """Céu inteiro (projeção estereográfica do zênite) com os alvos numerados.

    Convenção de carta para segurar acima da cabeça: norte em cima, **leste
    à esquerda**. Estrelas e linhas de constelação são as do instante
    ``when_utc`` (padrão: meio da janela da noite); cada alvo aparece na
    posição do **seu horário agendado**, com o número da parada — é o mapa
    de "para onde apontar" ao longo da noite. Com horizonte do quintal, a
    silhueta é sombreada na borda.
    """
    pal = CHART_THEMES.get(theme, _LIGHT)
    engine = plan.engine
    if when_utc is None:
        when_utc = plan.night_start + (plan.night_end - plan.night_start) / 2
    m = engine.horizontal_matrix(engine.ts.from_datetime(when_utc))
    img = QImage(size_px, size_px, QImage.Format_RGB32)
    img.fill(pal["bg"])
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    cx = cy = size_px / 2.0
    radius = size_px / 2.0 - size_px * 0.06

    def xy_altaz(alt_deg: float, az_deg: float):
        z = math.radians(90.0 - alt_deg)
        rr = radius * math.tan(z / 2.0)               # horizonte: tan(45°) = 1
        a = math.radians(az_deg)
        return QPointF(cx - rr * math.sin(a), cy - rr * math.cos(a))

    def xy_vec(h):
        alt = math.degrees(math.asin(max(-1.0, min(1.0, float(h[2])))))
        az = math.degrees(math.atan2(float(h[1]), float(h[0]))) % 360.0
        return xy_altaz(alt, az), alt

    # grade: horizonte, 30° e 60°, e os cardeais
    p.setPen(QPen(pal["grid"], 1.2, Qt.DotLine))
    p.setBrush(Qt.NoBrush)
    for alt in (30.0, 60.0):
        rr = radius * math.tan(math.radians(90.0 - alt) / 2.0)
        p.drawEllipse(QPointF(cx, cy), rr, rr)
    # horizonte do quintal: anel sombreado entre 0° e o perfil
    horizon = getattr(plan, "horizon", None)
    if horizon is not None and not horizon.is_flat:
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), radius, radius)
        inner = QPolygonF([xy_altaz(float(horizon.altitude_at(az)), az)
                           for az in np.arange(0.0, 360.0, 1.0)])
        hole = QPainterPath()
        hole.addPolygon(inner)
        hole.closeSubpath()
        shade = QColor(pal["frame"])
        shade.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(shade)
        p.drawPath(path.subtracted(hole))
        p.setBrush(Qt.NoBrush)

    # linhas de constelação acima do horizonte
    if const_lines is not None:
        p.setPen(QPen(pal["const"], 1.3))
        hv = const_lines.verts.astype(np.float64) @ m.T
        for a, b in const_lines.segments:
            if hv[a, 2] < 0.0 or hv[b, 2] < 0.0:
                continue
            pa, _ = xy_vec(hv[a])
            pb, _ = xy_vec(hv[b])
            p.drawLine(pa, pb)

    # estrelas até a magnitude 5
    count = stars.count_brighter_than(5.0)
    hs = stars.xyz[:count].astype(np.float64) @ m.T
    p.setPen(Qt.NoPen)
    p.setBrush(pal["star"])
    for i in np.nonzero(hs[:, 2] > 0.0)[0]:
        pt, _ = xy_vec(hs[i])
        r = max(1.0, (5.8 - 0.95 * float(stars.mag[i])) * size_px / 1400.0)
        p.drawEllipse(pt, r, r)

    # moldura do horizonte e cardeais
    p.setPen(QPen(pal["frame"], 2.0))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), radius, radius)
    font = QFont("Segoe UI", max(9, int(size_px / 60)), QFont.Bold)
    p.setFont(font)
    p.setPen(pal["text"])
    for name, az in (("N", 0.0), ("L", 90.0), ("S", 180.0), ("O", 270.0)):
        a = math.radians(az)
        x = cx - (radius + size_px * 0.03) * math.sin(a)
        y = cy - (radius + size_px * 0.03) * math.cos(a)
        p.drawText(QRectF(x - 30, y - 20, 60, 40), Qt.AlignCenter, name)

    # alvos numerados na posição do horário de cada um
    num_font = QFont("Segoe UI", max(8, int(size_px / 75)), QFont.Bold)
    p.setFont(num_font)
    fm = p.fontMetrics()
    taken: list = []
    for k, e in enumerate(plan.entries, 1):
        if e.altitude <= 0:
            continue
        pt = xy_altaz(e.altitude, e.azimuth)
        rad = max(6.0, size_px / 140.0)
        p.setPen(QPen(pal["target"], 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(pt, rad, rad)
        text = str(k)
        w = fm.horizontalAdvance(text)
        p.setPen(pal["target"])
        _draw_label_avoiding(p, text, taken, [
            (pt.x() + rad + 2, pt.y() + 4), (pt.x() - rad - 2 - w, pt.y() + 4),
            (pt.x() - w / 2, pt.y() - rad - 3), (pt.x() - w / 2, pt.y() + rad + fm.ascent()),
        ])
    p.end()
    return img
