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

# Paleta do modo carta (mesma linguagem do print_window)
COL_STAR = QColor(20, 22, 26)
COL_CONST = QColor(150, 158, 170)
COL_TARGET = QColor(196, 40, 40)
COL_ARROW = QColor(196, 40, 40)
COL_GUIDE = QColor(30, 90, 170)
COL_FRAME = QColor(120, 126, 138)
COL_TEXT = QColor(60, 64, 72)


def _unit(ra: float, dec: float) -> np.ndarray:
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
        t = float(v @ self.c)
        if t < 0.15:                     # atrás/na borda do plano tangente
            return None
        p = v / t - self.c
        x = self.half - self.scale * float(p @ self.east)   # leste à esquerda
        y = self.half - self.scale * float(p @ self.north)  # norte para cima
        return x, y


def render_finder_chart(entry, stars, const_lines, size_px: int = 460) -> QImage:
    """Desenha a carta de localização de uma entrada do roteiro.

    ``entry`` é um :class:`~carina.core.observing.PlanEntry` (usa ra/dec,
    guides e catalog_id); ``stars`` é o catálogo HYG; ``const_lines`` o
    :class:`PolylineSet` das linhas de constelação (pode ser ``None``).
    """
    target = _unit(entry.ra, entry.dec)

    # campo: cabe a guia principal com folga; sem guia, um campo de 15°
    if entry.guides:
        sep = max(g["sep"] for g in entry.guides[:1])
        fov = min(45.0, max(12.0, sep * 2.4))
        gvec = _unit(entry.guides[0]["ra"], entry.guides[0]["dec"])
        center = target + gvec
        center /= np.linalg.norm(center)
    else:
        fov = 15.0
        center = target

    proj = _Gnomonic(center, fov, size_px)

    img = QImage(size_px, size_px, QImage.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # --- linhas de constelação (orientação de campo) -------------------
    if const_lines is not None:
        p.setPen(QPen(COL_CONST, 1.0))
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
    p.setBrush(COL_STAR)
    for i in np.nonzero(near)[0]:
        pt = proj.xy(sub[i])
        if pt is None:
            continue
        r = max(0.7, 4.6 - 0.55 * float(mags[i]))
        p.drawEllipse(QPointF(*pt), r, r)

    cx, cy = proj.xy(target) or (proj.half, proj.half)

    # --- seta tracejada da guia principal até o alvo --------------------
    if entry.guides:
        g0 = entry.guides[0]
        gp = proj.xy(_unit(g0["ra"], g0["dec"]))
        if gp:
            gx, gy = gp
            dx, dy = cx - gx, cy - gy
            dist = math.hypot(dx, dy)
            if dist > 30:
                ux, uy = dx / dist, dy / dist
                pen = QPen(COL_ARROW, 2.0, Qt.DashLine)
                p.setPen(pen)
                # a linha parte da borda da estrela e para antes do alvo
                x0, y0 = gx + ux * 12, gy + uy * 12
                x1, y1 = cx - ux * 16, cy - uy * 16
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
                # ponta da seta
                p.setPen(Qt.NoPen)
                p.setBrush(COL_ARROW)
                wing = 7.0
                head = QPolygonF([
                    QPointF(x1 + ux * 10, y1 + uy * 10),
                    QPointF(x1 - uy * wing, y1 + ux * wing),
                    QPointF(x1 + uy * wing, y1 - ux * wing),
                ])
                p.drawPolygon(head)

        # nomes das estrelas-guia
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        for g in entry.guides:
            gp = proj.xy(_unit(g["ra"], g["dec"]))
            if gp is None:
                continue
            gx, gy = gp
            p.setPen(QPen(COL_GUIDE, 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(gx, gy), 9.0, 9.0)
            p.setPen(COL_GUIDE)
            p.drawText(QPointF(gx + 12, gy + 4), g["name"])

    # --- alvo: círculo duplo no estilo "finder" -------------------------
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(COL_TARGET, 2.0))
    p.drawEllipse(QPointF(cx, cy), 11.0, 11.0)
    p.setPen(QPen(COL_TARGET, 1.2))
    p.drawEllipse(QPointF(cx, cy), 16.0, 16.0)
    p.setPen(COL_TARGET)
    p.setFont(QFont("Segoe UI", 9, QFont.Bold))
    p.drawText(QPointF(cx + 20, cy - 12), entry.catalog_id)

    # --- moldura, escala e orientação -----------------------------------
    p.setPen(QPen(COL_FRAME, 1.4))
    p.drawRect(QRectF(0.5, 0.5, size_px - 1.0, size_px - 1.0))

    p.setFont(QFont("Segoe UI", 8))
    p.setPen(COL_TEXT)
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
    # rosa: N para cima, L à esquerda (convenção celeste)
    p.drawText(QPointF(size_px / 2 - 5, 14), "N")
    p.drawText(QPointF(8, size_px / 2 + 4), "L")
    p.drawText(QPointF(size_px - 16, size_px / 2 + 4), "O")
    p.drawText(QPointF(size_px - 60, size_px - 8), f"campo {fov:.0f}°")

    p.end()
    return img
