"""Mini-gráfico da altitude de um objeto durante a noite (ficha, v0.15).

Eixo x: do pôr ao nascer do Sol (com meia hora de folga); eixo y: altitude
de 0° a 90°. O fundo mostra as faixas do crepúsculo, a linha tracejada é a
altitude mínima útil, a área marrom é o horizonte do quintal na direção em
que o objeto está, e as marcas indicam agora (linha) e a melhor hora (ponto).
Passar o mouse mostra hora e altitude.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

BAND_COLORS = [(-0.8333, QColor(46, 62, 96)), (-6.0, QColor(30, 40, 70)),
               (-12.0, QColor(20, 26, 50)), (-18.0, QColor(12, 15, 32))]


class AltitudeMini(QWidget):
    """Altitude × hora para uma :class:`core.visibility.Visibility`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.vis = None
        self.horizon = None
        self.now_utc: dt.datetime | None = None
        self._i0 = self._i1 = 0
        self.setMinimumSize(240, 110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(120)
        self.setMouseTracking(True)

    def set_visibility(self, vis, horizon=None, now_utc=None) -> None:
        self.vis, self.horizon, self.now_utc = vis, horizon, now_utc
        if vis is not None:
            night = np.nonzero(vis.grid.sun_alt < -0.8333)[0]
            if len(night):
                self._i0 = max(0, int(night[0]) - 3)
                self._i1 = min(vis.grid.n - 1, int(night[-1]) + 3)
            else:
                self._i0, self._i1 = 0, vis.grid.n - 1
        self.update()

    def set_now(self, now_utc) -> None:
        self.now_utc = now_utc
        self.update()

    # -- geometria -----------------------------------------------------
    def _plot(self) -> QRectF:
        return QRectF(30, 6, self.width() - 36, self.height() - 24)

    def _x_of_index(self, k: float) -> float:
        r = self._plot()
        span = max(1, self._i1 - self._i0)
        return r.left() + (k - self._i0) / span * r.width()

    def _x_of_time(self, when: dt.datetime) -> float:
        g = self.vis.grid
        k = (when - g.start).total_seconds() / 60.0 / g.step_minutes
        return self._x_of_index(k)

    def _y(self, alt: float) -> float:
        r = self._plot()
        return r.bottom() - max(0.0, min(90.0, alt)) / 90.0 * r.height()

    # -- desenho ---------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(16, 18, 26))
        r = self._plot()
        if self.vis is None:
            p.end()
            return
        g = self.vis.grid
        i0, i1 = self._i0, self._i1
        # faixas do crepúsculo
        for k in range(i0, i1):
            sun = g.sun_alt[k]
            col = QColor(70, 90, 130)
            for limit, c in BAND_COLORS:
                if sun < limit:
                    col = c
            p.fillRect(QRectF(self._x_of_index(k), r.top(),
                              self._x_of_index(k + 1) - self._x_of_index(k) + 0.5,
                              r.height()), col)
        # grade e rótulos de altitude
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        p.setFont(small)
        for alt in (30, 60):
            p.setPen(QPen(QColor(70, 80, 100), 1, Qt.DotLine))
            p.drawLine(QPointF(r.left(), self._y(alt)), QPointF(r.right(), self._y(alt)))
            p.setPen(QColor(140, 150, 170))
            p.drawText(QRectF(0, self._y(alt) - 7, 26, 14),
                       Qt.AlignRight | Qt.AlignVCenter, f"{alt}°")
        # horas inteiras no eixo x
        from ...core.localtime import to_local

        for k in range(i0, i1 + 1):
            local = to_local(g.times[k])
            if local.minute == 0 and local.hour % 2 == 0:
                x = self._x_of_index(k)
                p.setPen(QColor(140, 150, 170))
                p.drawText(QRectF(x - 14, r.bottom() + 2, 28, 14), Qt.AlignCenter,
                           f"{local.hour:02d}h")
        # horizonte do quintal na direção do objeto
        if self.horizon is not None and not self.horizon.is_flat:
            path = QPainterPath(QPointF(self._x_of_index(i0), r.bottom()))
            for k in range(i0, i1 + 1):
                path.lineTo(self._x_of_index(k),
                            self._y(float(self.horizon.altitude_at(self.vis.azs[k]))))
            path.lineTo(self._x_of_index(i1), r.bottom())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(90, 64, 40, 190))
            p.drawPath(path)
        # altitude mínima útil
        p.setPen(QPen(QColor(200, 160, 90), 1, Qt.DashLine))
        p.drawLine(QPointF(r.left(), self._y(self.vis.min_alt)),
                   QPointF(r.right(), self._y(self.vis.min_alt)))
        # janela útil destacada sob a curva
        for a, b in self.vis.segments:
            p.fillRect(QRectF(self._x_of_time(a), r.bottom() - 3,
                              self._x_of_time(b) - self._x_of_time(a), 3),
                       QColor(110, 220, 140))
        # curva
        p.setPen(QPen(QColor(120, 200, 255), 1.8))
        prev = None
        for k in range(i0, i1 + 1):
            alt = float(self.vis.alts[k])
            pt = QPointF(self._x_of_index(k), self._y(alt))
            if prev is not None and (alt > 0 or prev[1] > 0):
                p.drawLine(prev[0], pt)
            prev = (pt, alt)
        # melhor hora e agora
        if self.vis.best_utc is not None and self.vis.observable:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 220, 120))
            p.drawEllipse(QPointF(self._x_of_time(self.vis.best_utc),
                                  self._y(self.vis.best_alt)), 3.5, 3.5)
        if self.now_utc is not None:
            x = self._x_of_time(self.now_utc)
            if r.left() <= x <= r.right():
                p.setPen(QPen(QColor(255, 120, 120), 1.2))
                p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        p.end()

    def mouseMoveEvent(self, event) -> None:
        if self.vis is None:
            return
        r = self._plot()
        x = event.position().x()
        if not r.left() <= x <= r.right():
            return
        from ...core.localtime import to_local

        k = self._i0 + (x - r.left()) / r.width() * max(1, self._i1 - self._i0)
        k = int(round(max(self._i0, min(self._i1, k))))
        when = to_local(self.vis.grid.times[k])
        QToolTip.showText(event.globalPosition().toPoint(),
                          f"{when:%H:%M} · {self.vis.alts[k]:.0f}°", self)
