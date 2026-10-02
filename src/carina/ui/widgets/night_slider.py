"""Linha do tempo da noite no rodapé (v0.16 T5).

Uma faixa do pôr ao nascer do Sol com as cores do crepúsculo, a Lua acima
do horizonte e marcas de hora; o cursor é o instante da simulação.
Clicar ou arrastar leva o relógio àquela hora — percorrer a noite vira um
gesto só.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

BANDS = [(-0.8333, QColor(60, 80, 120)), (-6.0, QColor(38, 50, 86)),
         (-12.0, QColor(24, 30, 58)), (-18.0, QColor(12, 15, 32))]


class NightSlider(QWidget):
    """Faixa da noite com cursor arrastável."""

    timeChosen = Signal(object)            # datetime UTC

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.grid = None
        self.t0: dt.datetime | None = None
        self.t1: dt.datetime | None = None
        self.now: dt.datetime | None = None
        self._dragging = False
        self.setMinimumHeight(30)
        self.setMaximumHeight(34)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setToolTip(self.tr("Clique ou arraste para percorrer a noite"))

    # -- dados ---------------------------------------------------------
    def set_night(self, grid) -> None:
        """Usa uma :class:`core.visibility.NightGrid` (pôr → nascer ± 30 min)."""
        self.grid = grid
        night = grid.night
        start = night.sunset or grid.times[0] + dt.timedelta(hours=5)
        end = night.sunrise or grid.times[-1] - dt.timedelta(hours=5)
        pad = dt.timedelta(minutes=30)
        self.t0, self.t1 = start - pad, end + pad
        self.update()

    def set_now(self, when: dt.datetime) -> None:
        self.now = when
        self.update()

    # -- conversões ----------------------------------------------------
    LEFT, RIGHT = 6.0, 6.0

    def time_to_x(self, when: dt.datetime) -> float:
        span = (self.t1 - self.t0).total_seconds()
        frac = (when - self.t0).total_seconds() / span
        return self.LEFT + frac * (self.width() - self.LEFT - self.RIGHT)

    def x_to_time(self, x: float) -> dt.datetime:
        span = (self.t1 - self.t0).total_seconds()
        frac = (x - self.LEFT) / max(1.0, self.width() - self.LEFT - self.RIGHT)
        frac = max(0.0, min(1.0, frac))
        return self.t0 + dt.timedelta(seconds=round(frac * span / 60.0) * 60.0)

    # -- desenho ---------------------------------------------------------
    def paintEvent(self, _event) -> None:
        from ...core.localtime import to_local

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(14, 16, 22))
        if self.grid is None or self.t0 is None:
            p.end()
            return
        g = self.grid
        h = self.height()
        bar = QRectF(self.LEFT, 4, self.width() - self.LEFT - self.RIGHT, h - 16)
        for k in range(g.n - 1):
            a, b = g.times[k], g.times[k + 1]
            if b < self.t0 or a > self.t1:
                continue
            col = QColor(90, 120, 170)
            for limit, c in BANDS:
                if g.sun_alt[k] < limit:
                    col = c
            x0 = self.time_to_x(max(a, self.t0))
            x1 = self.time_to_x(min(b, self.t1))
            p.fillRect(QRectF(x0, bar.top(), x1 - x0 + 0.6, bar.height()), col)
            if g.moon_alt[k] > 0:
                moon = QColor(225, 222, 200, int(70 + 150 * g.moon_illum))
                p.fillRect(QRectF(x0, bar.bottom() - 3, x1 - x0 + 0.6, 3), moon)
        small = QFont(self.font())
        small.setPointSizeF(7.0)
        p.setFont(small)
        hour = to_local(self.t0).replace(minute=0, second=0, microsecond=0)
        hour += dt.timedelta(hours=1)
        while hour.astimezone(dt.timezone.utc) < self.t1:
            x = self.time_to_x(hour.astimezone(dt.timezone.utc))
            p.setPen(QPen(QColor(90, 100, 120), 1))
            p.drawLine(QPointF(x, bar.bottom()), QPointF(x, bar.bottom() + 3))
            p.setPen(QColor(170, 180, 200))
            p.drawText(QRectF(x - 14, bar.bottom() + 1, 28, 12), Qt.AlignCenter, f"{hour:%H}h")
            hour += dt.timedelta(hours=1)
        if self.now is not None and self.t0 <= self.now <= self.t1:
            x = self.time_to_x(self.now)
            p.setPen(QPen(QColor(255, 120, 110), 2))
            p.drawLine(QPointF(x, 1), QPointF(x, bar.bottom() + 2))
            p.setBrush(QColor(255, 120, 110))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, 3), 3, 3)
        p.end()

    # -- interação -------------------------------------------------------
    def _choose(self, x: float) -> None:
        if self.t0 is None:
            return
        when = self.x_to_time(x)
        self.now = when
        self.timeChosen.emit(when)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._choose(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._choose(event.position().x())
        elif self.t0 is not None:
            from ...core.localtime import to_local

            when = to_local(self.x_to_time(event.position().x()))
            QToolTip.showText(event.globalPosition().toPoint(), f"{when:%H:%M}", self)

    def mouseReleaseEvent(self, _event) -> None:
        self._dragging = False
