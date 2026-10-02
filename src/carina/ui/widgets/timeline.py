"""Linha do tempo da noite para o roteiro (v0.15 T10), estilo Gantt.

Faixa superior: crepúsculos (cores do céu pela altitude do Sol) e a Lua
acima do horizonte. Abaixo, uma linha por parada do roteiro: a barra fina
é a **janela útil** do objeto, o bloco é o **horário agendado** (cor pela
pontuação; contorno vermelho quando cai fora da janela). Clicar seleciona;
**arrastar o bloco** muda o horário (o roteiro é reagendado pelo dono).
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

ROW_H = 16
HEAD_H = 34
LEFT = 150
SUN_BANDS = [(-0.8333, QColor(52, 70, 108)), (-6.0, QColor(34, 46, 80)),
             (-12.0, QColor(22, 28, 54)), (-18.0, QColor(12, 15, 32))]


def score_color(score: int) -> QColor:
    if score >= 75:
        return QColor(60, 170, 100)
    if score >= 55:
        return QColor(120, 170, 60)
    if score >= 35:
        return QColor(200, 160, 50)
    if score > 0:
        return QColor(200, 110, 50)
    return QColor(120, 120, 130)


class NightTimeline(QWidget):
    """Gantt da noite: crepúsculos, Lua e uma barra por parada."""

    entryClicked = Signal(int)
    slotMoved = Signal(int, object)          # (índice, novo horário UTC)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.plan = None
        self.grid = None
        self.t0: dt.datetime | None = None
        self.t1: dt.datetime | None = None
        self.selected = -1
        self.now_utc: dt.datetime | None = None
        self._drag: tuple[int, float, dt.datetime] | None = None
        self._drag_x = 0.0
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(HEAD_H + 3 * ROW_H)

    # -- dados ---------------------------------------------------------
    def set_plan(self, plan, grid=None) -> None:
        self.plan, self.grid = plan, grid
        if plan is not None and plan.night_start and plan.night_end:
            pad = dt.timedelta(minutes=30)
            self.t0, self.t1 = plan.night_start - pad, plan.night_end + pad
        else:
            self.t0 = self.t1 = None
        n = len(plan.entries) if plan else 0
        self.setMinimumHeight(HEAD_H + max(3, n) * ROW_H + 18)
        self.updateGeometry()
        self.update()

    def set_selected(self, index: int) -> None:
        self.selected = index
        self.update()

    def set_now(self, when) -> None:
        self.now_utc = when
        self.update()

    # -- conversões ----------------------------------------------------
    def time_to_x(self, when: dt.datetime) -> float:
        span = (self.t1 - self.t0).total_seconds()
        frac = (when - self.t0).total_seconds() / span
        return LEFT + frac * (self.width() - LEFT - 8)

    def x_to_time(self, x: float) -> dt.datetime:
        span = (self.t1 - self.t0).total_seconds()
        frac = (x - LEFT) / max(1.0, self.width() - LEFT - 8)
        frac = max(0.0, min(1.0, frac))
        return self.t0 + dt.timedelta(seconds=frac * span)

    def row_at(self, y: float) -> int:
        if self.plan is None or y < HEAD_H:
            return -1
        r = int((y - HEAD_H) // ROW_H)
        return r if 0 <= r < len(self.plan.entries) else -1

    def _slot(self, e) -> tuple[dt.datetime, dt.datetime]:
        return e.when_utc, e.when_utc + dt.timedelta(minutes=self.plan.minutes_per_object)

    # -- desenho ---------------------------------------------------------
    def paintEvent(self, _event) -> None:
        from ...core.localtime import to_local

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(16, 18, 26))
        if self.plan is None or self.t0 is None:
            p.end()
            return
        w = self.width()
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        p.setFont(small)

        # faixa do céu: cor pela altitude do Sol (grade da visibilidade)
        g = self.grid
        if g is not None:
            for k in range(g.n - 1):
                a, b = g.times[k], g.times[k + 1]
                if b < self.t0 or a > self.t1:
                    continue
                col = QColor(80, 100, 140)
                for limit, c in SUN_BANDS:
                    if g.sun_alt[k] < limit:
                        col = c
                x0, x1 = self.time_to_x(max(a, self.t0)), self.time_to_x(min(b, self.t1))
                p.fillRect(QRectF(x0, 0, x1 - x0 + 0.6, HEAD_H - 14), col)
                if g.moon_alt[k] > 0:
                    p.fillRect(QRectF(x0, HEAD_H - 14, x1 - x0 + 0.6, 5),
                               QColor(220, 220, 200, int(80 + 150 * g.moon_illum)))
        p.setPen(QColor(150, 160, 180))
        p.drawText(QRectF(4, 0, LEFT - 8, HEAD_H - 14), Qt.AlignVCenter, "Céu")
        p.drawText(QRectF(4, HEAD_H - 16, LEFT - 8, 10), Qt.AlignVCenter,
                   f"Lua {self.plan.moon_illumination * 100:.0f}%")
        # horas cheias
        hour = to_local(self.t0).replace(minute=0, second=0, microsecond=0)
        hour += dt.timedelta(hours=1)
        while hour.astimezone(dt.timezone.utc) < self.t1:
            x = self.time_to_x(hour.astimezone(dt.timezone.utc))
            p.setPen(QPen(QColor(60, 70, 90), 1, Qt.DotLine))
            p.drawLine(QPointF(x, HEAD_H), QPointF(x, self.height()))
            p.setPen(QColor(200, 210, 225))
            p.drawText(QRectF(x - 18, 2, 36, 12), Qt.AlignCenter, f"{hour:%H}h")
            hour += dt.timedelta(hours=1)

        # linhas do roteiro
        for r, e in enumerate(self.plan.entries):
            y = HEAD_H + r * ROW_H
            if r == self.selected:
                p.fillRect(QRectF(0, y, w, ROW_H), QColor(45, 60, 95))
            elif r % 2:
                p.fillRect(QRectF(0, y, w, ROW_H), QColor(22, 25, 34))
            p.setPen(QColor(210, 215, 228))
            p.drawText(QRectF(4, y, LEFT - 8, ROW_H), Qt.AlignVCenter,
                       f"{r + 1}. {e.designation}")
            if e.window_start and e.window_end:
                x0 = self.time_to_x(max(e.window_start, self.t0))
                x1 = self.time_to_x(min(e.window_end, self.t1))
                p.fillRect(QRectF(x0, y + ROW_H / 2 - 1.5, max(1.0, x1 - x0), 3),
                           QColor(110, 150, 200, 150))
            s0, s1 = self._slot(e)
            x0 = self.time_to_x(s0)
            if self._drag is not None and self._drag[0] == r:
                x0 += self._drag_x - self._drag[1]
            x1 = x0 + (self.time_to_x(s1) - self.time_to_x(s0))
            rect = QRectF(x0, y + 2, max(4.0, x1 - x0), ROW_H - 4)
            p.setPen(QPen(QColor(235, 80, 80), 1.6) if e.late else Qt.NoPen)
            p.setBrush(score_color(e.score))
            p.drawRoundedRect(rect, 2, 2)
        if self.now_utc is not None and self.t0 <= self.now_utc <= self.t1:
            x = self.time_to_x(self.now_utc)
            p.setPen(QPen(QColor(255, 110, 110), 1.4))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        p.end()

    # -- interação -------------------------------------------------------
    def _hit_slot(self, x: float, y: float) -> int:
        r = self.row_at(y)
        if r < 0:
            return -1
        s0, s1 = self._slot(self.plan.entries[r])
        return r if self.time_to_x(s0) - 3 <= x <= self.time_to_x(s1) + 3 else -1

    def mousePressEvent(self, event) -> None:
        if self.plan is None or self.t0 is None:
            return
        x, y = event.position().x(), event.position().y()
        r = self.row_at(y)
        if r >= 0:
            self.entryClicked.emit(r)
        hit = self._hit_slot(x, y)
        if hit >= 0 and event.button() == Qt.LeftButton:
            self._drag = (hit, x, self.plan.entries[hit].when_utc)
            self._drag_x = x

    def mouseMoveEvent(self, event) -> None:
        if self.plan is None or self.t0 is None:
            return
        x, y = event.position().x(), event.position().y()
        if self._drag is not None:
            self._drag_x = x
            self.update()
            return
        hit = self._hit_slot(x, y)
        self.setCursor(Qt.SizeHorCursor if hit >= 0 else Qt.ArrowCursor)
        r = self.row_at(y)
        if r >= 0:
            from ...core.localtime import to_local

            e = self.plan.entries[r]
            text = f"{e.label}\n{to_local(e.when_utc):%H:%M} · alt {e.altitude:.0f}°"
            if e.window_start and e.window_end:
                text += (f"\njanela {to_local(e.window_start):%H:%M}–"
                         f"{to_local(e.window_end):%H:%M}")
            if e.late:
                text += "\nfora da janela útil"
            QToolTip.showText(event.globalPosition().toPoint(), text, self)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag is None:
            return
        index, x_start, when0 = self._drag
        self._drag = None
        dx = event.position().x() - x_start
        if abs(dx) >= 3:
            new = self.x_to_time(self.time_to_x(when0) + dx)
            # arredonda para o minuto
            new = new.replace(second=0, microsecond=0)
            self.slotMoved.emit(index, new)
        self.update()
