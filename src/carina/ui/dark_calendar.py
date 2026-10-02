"""Calendário de noites escuras (v0.15 T12).

Grade mensal: cada dia mostra a fase da Lua desenhada, as horas de noite
astronômica sem Lua (número e barra) e destaca as três melhores noites do
mês. Clicar num dia leva a simulação ao anoitecer daquela data.
"""

from __future__ import annotations

import calendar
import datetime as dt
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core.dark_nights import BEST_MIN_HOURS, best_nights, darkest_night, month_nights

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
WEEKDAYS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"]


def draw_moon(p: QPainter, center: QPointF, r: float, phase_deg: float,
              south: bool = False) -> None:
    """Lua com a fase (0 nova, 180 cheia).

    No hemisfério norte o crescente tem o lado direito iluminado; no sul,
    o esquerdo (``south=True``) — é como a Lua aparece a quem observa.
    """
    p.save()
    p.setPen(QPen(QColor(120, 125, 140), 0.8))
    p.setBrush(QColor(40, 42, 52))
    p.drawEllipse(center, r, r)
    phase = phase_deg % 360.0
    frac = (1.0 - math.cos(math.radians(phase))) / 2.0      # fração iluminada
    if frac > 0.005:
        waxing = phase < 180.0
        right = waxing != south
        rect = QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r)
        half = QPainterPath()
        half.moveTo(center.x(), center.y() - r)
        half.arcTo(rect, 90, -180 if right else 180)
        half.closeSubpath()
        tw = abs(math.cos(math.radians(phase))) * r
        ell = QPainterPath()
        ell.addEllipse(QRectF(center.x() - tw, center.y() - r, 2 * tw, 2 * r))
        lit = half.subtracted(ell) if frac < 0.5 else half.united(ell)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 232, 210))
        p.drawPath(lit)
    p.restore()


class MonthGrid(QWidget):
    """Grade 7 × 6 do mês com as noites escuras."""

    dayClicked = Signal(object)          # dt.date

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.nights = []
        self.best = set()
        self.year = self.month = 0
        self.south = False
        self.setMinimumSize(640, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_month(self, year: int, month: int, nights) -> None:
        self.year, self.month, self.nights = year, month, nights
        self.best = {n.date for n in best_nights(nights)}
        self.update()

    def _cells(self):
        first_wd = (dt.date(self.year, self.month, 1).weekday() + 1) % 7   # domingo = 0
        w = self.width() / 7.0
        h = (self.height() - 22) / 6.0
        for i, night in enumerate(self.nights):
            slot = first_wd + i
            yield night, QRectF((slot % 7) * w, 22 + (slot // 7) * h, w, h)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(16, 18, 26))
        w = self.width() / 7.0
        small = QFont(self.font())
        small.setPointSizeF(8)
        p.setFont(small)
        p.setPen(QColor(150, 160, 180))
        for i, name in enumerate(WEEKDAYS):
            p.drawText(QRectF(i * w, 0, w, 20), Qt.AlignCenter, name)
        max_dark = max((n.astro_minutes for n in self.nights), default=1.0) or 1.0
        for night, r in self._cells():
            cell = r.adjusted(2, 2, -2, -2)
            best = night.date in self.best
            p.setPen(QPen(QColor(110, 200, 140), 1.6) if best else QPen(QColor(45, 50, 64)))
            p.setBrush(QColor(26, 30, 42))
            p.drawRoundedRect(cell, 4, 4)
            p.setPen(QColor(220, 225, 235))
            p.drawText(cell.adjusted(6, 4, 0, 0), Qt.AlignLeft | Qt.AlignTop,
                       str(night.date.day))
            draw_moon(p, QPointF(cell.right() - 14, cell.top() + 14), 9.0,
                      night.phase_deg, self.south)
            hours = night.moonless_hours
            frac = night.moonless_minutes / max_dark
            bar = QRectF(cell.left() + 6, cell.bottom() - 10, (cell.width() - 12) * frac, 5)
            p.fillRect(QRectF(cell.left() + 6, cell.bottom() - 10, cell.width() - 12, 5),
                       QColor(45, 50, 64))
            p.fillRect(bar, QColor(110, 200, 140) if hours >= 3 else QColor(200, 160, 60)
                       if hours >= 1 else QColor(150, 90, 70))
            p.setPen(QColor(200, 210, 225))
            p.drawText(QRectF(cell.left() + 6, cell.bottom() - 30, cell.width() - 12, 16),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{hours:.1f} h".replace(".", ","))
        p.end()

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        for night, r in self._cells():
            if r.contains(pos):
                self.dayClicked.emit(night.date)
                return

    def tooltip_for(self, night) -> str:
        return (f"{night.date:%d/%m}: {night.phase_name}, {night.moon_illum * 100:.0f}% · "
                f"{night.astro_minutes / 60:.1f} h de noite astronômica, "
                f"{night.moonless_hours:.1f} h sem Lua")

    def event(self, ev) -> bool:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QToolTip

        if ev.type() == QEvent.ToolTip:
            for night, r in self._cells():
                if r.contains(QPointF(ev.pos())):
                    QToolTip.showText(ev.globalPos(), self.tooltip_for(night), self)
                    return True
            QToolTip.hideText()
            return True
        return super().event(ev)


class DarkCalendarDialog(QDialog):
    """Tempo ▸ Calendário de noites escuras…"""

    dateChosen = Signal(object)          # dt.date (a noite que começa nesta data)

    def __init__(self, engine, start: dt.date, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle(self.tr("Calendário de noites escuras"))
        self.resize(760, 560)
        self.year, self.month = start.year, start.month
        self.title = QLabel()
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size:14pt; font-weight:600;")
        prev_btn = QPushButton("◀")
        next_btn = QPushButton("▶")
        today_btn = QPushButton(self.tr("Mês atual"))
        prev_btn.clicked.connect(lambda: self._shift(-1))
        next_btn.clicked.connect(lambda: self._shift(+1))
        today_btn.clicked.connect(self._today)
        top = QHBoxLayout()
        top.addWidget(prev_btn)
        top.addWidget(self.title, 1)
        top.addWidget(next_btn)
        top.addWidget(today_btn)
        self.grid = MonthGrid()
        topo = getattr(engine, "topos", None)
        self.grid.south = bool(topo is not None and topo.latitude.degrees < 0)
        self.grid.dayClicked.connect(self._chosen)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        hint = QLabel(self.tr(
            "Número e barra: horas de noite astronômica sem a Lua no céu. Contorno "
            "verde: as melhores noites — mais de 8 h sem Lua. Clique num dia para ir "
            "ao anoitecer daquela data."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a93a5; font-size:8pt")
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.grid, 1)
        lay.addWidget(self.summary)
        lay.addWidget(hint)
        self._today_date = start
        self._load()

    def _load(self) -> None:
        nights = month_nights(self.engine, self.year, self.month)
        self.grid.set_month(self.year, self.month, nights)
        self.title.setText(f"{MONTHS[self.month - 1].capitalize()} de {self.year}")
        best = best_nights(nights)
        if best:
            parts = [f"{n.date:%d/%m} ({n.moonless_hours:.1f} h)".replace(".", ",")
                     for n in best]
            self.summary.setText(self.tr("Melhores noites (mais de {h:.0f} h sem Lua): {l}")
                                 .format(h=BEST_MIN_HOURS, l=", ".join(parts)))
        else:
            top = darkest_night(nights)
            extra = (f" — a mais escura: {top.date:%d/%m}, {top.moonless_hours:.1f} h"
                     .replace(".", ",", 1) if top else "")
            self.summary.setText(self.tr(
                "Nenhuma noite com mais de {h:.0f} h sem Lua neste mês{e}.").format(
                    h=BEST_MIN_HOURS, e=extra))

    def _shift(self, delta: int) -> None:
        m = self.month - 1 + delta
        self.year += m // 12
        self.month = m % 12 + 1
        self._load()

    def _today(self) -> None:
        self.year, self.month = self._today_date.year, self._today_date.month
        self._load()

    def _chosen(self, date: dt.date) -> None:
        self.dateChosen.emit(date)
