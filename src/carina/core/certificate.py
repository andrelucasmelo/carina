"""Certificado de conclusão de um programa de observação (v0.22 T1).

PDF A4 paisagem desenhado com o ``QPdfWriter`` do próprio Qt (sem
dependências): moldura dupla, um campo de estrelas discreto (semente fixa,
o mesmo desenho sempre), o título do programa, o nome de quem observou, o
número de objetos, a data de conclusão e o local.
"""

from __future__ import annotations

import datetime as dt
import random
from pathlib import Path


def make_certificate(path: Path | str, program_title: str, count: int, name: str,
                     date: dt.date, place: str = "", source: str = "") -> Path:
    from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

    path = Path(path)
    w = QPdfWriter(str(path))
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageOrientation(QPageLayout.Landscape)
    w.setPageMargins(QMarginsF(0, 0, 0, 0))
    w.setResolution(150)
    w.setTitle(f"Certificado — {program_title}")
    w.setCreator("Carina")
    p = QPainter(w)
    W, H = w.width(), w.height()
    p.fillRect(0, 0, W, H, QColor(11, 16, 32))
    rnd = random.Random(42)
    for _ in range(420):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        r = rnd.choice((1.0, 1.0, 1.5, 2.0, 3.0))
        a = rnd.randint(60, 200)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(220, 228, 255, a))
        p.drawEllipse(QPointF(x, y), r, r)
    m = W * 0.035
    gold = QColor(222, 190, 120)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(gold, 6))
    p.drawRect(QRectF(m, m, W - 2 * m, H - 2 * m))
    p.setPen(QPen(gold, 2))
    p.drawRect(QRectF(m * 1.5, m * 1.5, W - 3 * m, H - 3 * m))

    def text(y_frac, size, s, color=QColor(235, 238, 248), bold=False, italic=False):
        f = QFont("Georgia", size)
        f.setBold(bold)
        f.setItalic(italic)
        p.setFont(f)
        p.setPen(color)
        p.drawText(QRectF(m * 2, H * y_frac, W - 4 * m, H * 0.12),
                   Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, s)

    text(0.11, 20, "CARINA", gold, bold=True)
    text(0.20, 38, "Certificado de observação", bold=True)
    text(0.34, 18, "Certificamos que", QColor(190, 198, 220), italic=True)
    text(0.41, 34, name or "—", gold, bold=True)
    text(0.53, 18, f"concluiu o programa de observação", QColor(190, 198, 220), italic=True)
    text(0.60, 30, program_title, bold=True)
    obj = "objeto" if count == 1 else "objetos"
    line = f"{count} {obj} observados · concluído em {date:%d/%m/%Y}"
    if place:
        line += f" · {place}"
    text(0.72, 16, line, QColor(205, 212, 232))
    if source:
        text(0.80, 11, source, QColor(150, 160, 185), italic=True)
    text(0.86, 11, "Registrado no diário de observação do Carina", QColor(150, 160, 185))
    p.end()
    return path
