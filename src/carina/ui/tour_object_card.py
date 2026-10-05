"""Cartão do objeto no tour "Objetos do mês" (v0.20 T8).

Dois gráficos pequenos e um botão:

- **altura × hora** na noite típica do mês (dia 15): a curva do objeto, a
  faixa útil acima da altura mínima, a zona do zênite (montagem alt-az),
  o céu escuro sombreado e o meridiano (montagem equatorial alemã);
- **horas úteis por noite** em cada noite do mês, com a linha das 4 h;
- **+ Sessão**: manda o alvo para a Sessão de astrofoto.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout, QWidget

from ..core.localtime import to_local
from .tour_player import register_card


class NightAltitude(QWidget):
    """Altura do objeto ao longo da noite típica."""

    def __init__(self, card: dict, parent=None) -> None:
        super().__init__(parent)
        self.card = card
        self.setMinimumHeight(120)
        self.times = [dt.datetime.fromisoformat(t) for t in card["times"]]
        self.alts = card["alts"]
        self.dark = card.get("dark") or [True] * len(self.alts)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(12, 15, 26))
        n = len(self.alts)
        if n < 2:
            p.end()
            return
        dk = [i for i, d in enumerate(self.dark) if d]
        k0, k1 = (dk[0], dk[-1]) if dk else (0, n - 1)
        k0, k1 = max(0, k0 - 6), min(n - 1, k1 + 6)            # 1 h de margem
        left, right, top, bottom = 28, 6, 6, 16
        w, h = self.width() - left - right, self.height() - top - bottom

        def x(k):
            return left + w * (k - k0) / max(1, k1 - k0)

        def y(a):
            return top + h * (1 - max(0.0, min(90.0, a)) / 90.0)

        c = self.card
        p.setFont(QFont("Segoe UI", 7))
        for k in range(k0, k1):
            if not self.dark[k]:
                p.fillRect(QRectF(x(k), top, x(k + 1) - x(k) + 0.5, h), QColor(30, 34, 48))
        p.fillRect(QRectF(left, y(90), w, y(c["min_alt"]) - y(90)), QColor(25, 45, 35, 120))
        if c.get("zenith"):
            p.fillRect(QRectF(left, y(90), w, y(c["zenith"]) - y(90)), QColor(90, 40, 40, 120))
        for a in (30, 60):
            p.setPen(QPen(QColor(60, 70, 90), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y(a)), QPointF(left + w, y(a)))
            p.setPen(QColor(130, 140, 160))
            p.drawText(QRectF(0, y(a) - 6, left - 3, 12), Qt.AlignRight | Qt.AlignVCenter,
                       f"{a}°")
        pen = QPen(QColor(120, 200, 255), 1.8)
        for k in range(k0, k1):
            ok = (self.dark[k] and self.alts[k] > c["min_alt"]
                  and (not c.get("zenith") or self.alts[k] < c["zenith"]))
            pen.setColor(QColor(110, 220, 140) if ok else QColor(120, 140, 170))
            pen.setWidthF(2.4 if ok else 1.2)
            p.setPen(pen)
            p.drawLine(QPointF(x(k), y(self.alts[k])), QPointF(x(k + 1), y(self.alts[k + 1])))
        if c.get("meridian"):
            km = max(range(k0, k1 + 1), key=lambda k: self.alts[k])
            if k0 < km < k1 and self.alts[km] > 0:
                p.setPen(QPen(QColor(255, 255, 255, 150), 1, Qt.DashLine))
                p.drawLine(QPointF(x(km), y(self.alts[km]) - 10), QPointF(x(km), top + h))
        p.setPen(QColor(140, 150, 170))
        for k in range(k0, k1 + 1):
            lt = to_local(self.times[k])
            if lt.minute == 0 and lt.hour % 2 == 0:
                p.drawText(QRectF(x(k) - 12, top + h + 2, 24, 12), Qt.AlignCenter, f"{lt:%H}h")
        p.end()


class MonthHours(QWidget):
    """Horas úteis por noite no mês, com dica ao passar o mouse."""

    def __init__(self, card: dict, parent=None) -> None:
        super().__init__(parent)
        self.card = card
        self.setMinimumHeight(70)
        self.setMouseTracking(True)
        self.dates = [dt.date.fromisoformat(d) for d in card["dates"]]
        self.hours = card["hours"]
        self._geom = None

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(14, 18, 28))
        n = len(self.hours)
        left, right, top, bottom = 28, 6, 4, 14
        w, h = self.width() - left - right, self.height() - top - bottom
        hmax = max(8.0, max(self.hours) if self.hours else 8.0)
        self._geom = (left, w)
        bw = w / max(n, 1)
        typical = self.card.get("typical")
        for k, hh in enumerate(self.hours):
            bh = h * hh / hmax
            col = (QColor(90, 170, 110) if hh >= self.card.get("min_hours", 4)
                   else QColor(200, 170, 80) if hh > 0.5 else QColor(70, 70, 80))
            if self.dates[k].isoformat() == typical:
                col = col.lighter(140)
            p.fillRect(QRectF(left + k * bw + 0.5, top + h - bh, max(1.0, bw - 1), bh), col)
        y4 = top + h - h * self.card.get("min_hours", 4) / hmax
        p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
        p.drawLine(QPointF(left, y4), QPointF(left + w, y4))
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor(140, 150, 170))
        p.drawText(QRectF(0, y4 - 6, left - 3, 12), Qt.AlignRight | Qt.AlignVCenter,
                   f"{self.card.get('min_hours', 4):.0f}h")
        for k, d in enumerate(self.dates):
            if d.day in (1, 10, 20) or k == n - 1:
                p.drawText(QRectF(left + k * bw - 8, top + h + 1, 20, 12), Qt.AlignCenter,
                           str(d.day))
        p.end()

    def bar_at(self, x: float) -> int:
        if self._geom is None:
            return -1
        left, w = self._geom
        k = int((x - left) / max(w, 1) * len(self.hours))
        return k if 0 <= k < len(self.hours) else -1

    def mouseMoveEvent(self, e) -> None:
        k = self.bar_at(e.position().x())
        if k >= 0:
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"{self.dates[k]:%d/%m}: {self.hours[k]:.1f} h úteis".replace(".", ","),
                              self)


@register_card("month_object")
def month_object_card(card: dict, player) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 4, 0, 0)
    lay.setSpacing(3)
    typical = dt.date.fromisoformat(card["typical"])
    lab = QLabel(f"<b>Altura na noite de {typical:%d/%m}</b> "
                 "<span style='color:#8a93a5'>(verde = útil)</span>")
    lay.addWidget(lab)
    lay.addWidget(NightAltitude(card))
    lay.addWidget(QLabel(f"<b>Horas úteis por noite no mês</b> "
                         f"<span style='color:#8a93a5'>(mediana "
                         f"{card['median']:.1f} h)</span>".replace(".", ",")))
    lay.addWidget(MonthHours(card))
    row = QHBoxLayout()
    btn = QPushButton("+ Sessão de astrofoto")
    btn.setToolTip("Acrescenta este alvo à Sessão de astrofoto")

    def add():
        main = player.main
        if hasattr(main, "_open_session") and hasattr(main, "_session_resolve"):
            got = main._session_resolve("dso", card["ident"])
            if got is not None:
                main._open_session(None, focus=False)
                main._session_window.add_target(*got)
                btn.setText("✓ Na sessão")
                btn.setEnabled(False)

    btn.clicked.connect(add)
    row.addStretch(1)
    row.addWidget(btn)
    lay.addLayout(row)
    return box
