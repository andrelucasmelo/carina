"""Painel "Hoje à noite" (v0.15 T11) — tecla T, menu Planejar e barra lateral.

Mostra o resumo de :func:`core.tonight.tonight_summary`: a noite
(crepúsculos e Lua), os cinco melhores alvos de céu profundo e os planetas,
com "ir para" (no mapa ou na melhor hora), ★ para a lista e "montar
roteiro dos melhores objetos".
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..core.localtime import to_local
from ..core.tonight import format_minutes
from ..core.twilight import format_night_summary
from .widgets.timeline import score_color


def _hm(when) -> str:
    return to_local(when).strftime("%H:%M") if when else "—"


class TonightPanel(QDialog):
    """Resumo da noite com atalhos de ação."""

    gotoRequested = Signal(str, str)                 # (kind, ident)
    gotoAtTimeRequested = Signal(str, str, object)
    addToListRequested = Signal(str, str)
    planRequested = Signal()

    def __init__(self, summary, location: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Hoje à noite"))
        self.resize(720, 640)
        self.summary = summary
        s = summary

        date = to_local(s.night.sunset or s.ref_utc)
        head = QLabel(f"<h2 style='margin-bottom:0'>{self.tr('Hoje à noite')} — "
                      f"{date:%d/%m/%Y}</h2><p style='color:#8a93a5'>{location}</p>"
                      f"<p><b>{s.verdict}</b></p>")
        head.setTextFormat(Qt.RichText)
        head.setWordWrap(True)

        rows = "".join(f"<tr><td style='color:#8a93a5; padding-right:12px'>{a}</td>"
                       f"<td>{b}</td></tr>" for a, b in format_night_summary(s.night))
        moon = (f"{s.moon_phase}, {s.moon_illum * 100:.0f}% iluminada · nasce "
                f"{_hm(s.moon_rise)} · se põe {_hm(s.moon_set)}")
        rows += (f"<tr><td style='color:#8a93a5'>Lua</td><td>{moon}</td></tr>"
                 f"<tr><td style='color:#8a93a5'>Céu escuro</td><td>"
                 f"{format_minutes(s.dark_minutes)} de noite astronômica, "
                 f"{format_minutes(s.moonless_minutes)} sem Lua</td></tr>")
        night = QLabel(f"<table>{rows}</table>")
        night.setTextFormat(Qt.RichText)

        self.best = self._table([it for it in s.best])
        self.planets = self._table([it for it in s.planets])

        btn_go = QPushButton(self.tr("Ir para"))
        btn_time = QPushButton(self.tr("Ir para na melhor hora"))
        btn_list = QPushButton(self.tr("★ Minha lista"))
        btn_plan = QPushButton(self.tr("Montar roteiro dos melhores objetos"))
        btn_plan.setDefault(True)
        btn_close = QPushButton(self.tr("Fechar"))
        btn_go.clicked.connect(lambda: self._act("go"))
        btn_time.clicked.connect(lambda: self._act("time"))
        btn_list.clicked.connect(lambda: self._act("list"))
        btn_plan.clicked.connect(self.planRequested.emit)
        btn_close.clicked.connect(self.close)
        bar = QHBoxLayout()
        for b in (btn_go, btn_time, btn_list):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(btn_plan)
        bar.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(night)
        lay.addWidget(QLabel(self.tr("<b>Melhores alvos de céu profundo</b> "
                                     "(nota com seu céu e seu horizonte)")))
        lay.addWidget(self.best, 3)
        lay.addWidget(QLabel(self.tr("<b>Planetas</b>")))
        lay.addWidget(self.planets, 2)
        lay.addLayout(bar)
        self._last_table = self.best
        self.best.itemSelectionChanged.connect(lambda: self._focus(self.best))
        self.planets.itemSelectionChanged.connect(lambda: self._focus(self.planets))

    def _table(self, items) -> QTableWidget:
        t = QTableWidget(len(items), 5)
        t.setHorizontalHeaderLabels([self.tr("Objeto"), self.tr("Tipo"), self.tr("Nota"),
                                     self.tr("Melhor hora"), self.tr("Janela útil")])
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for r, it in enumerate(items):
            cells = [it.name, it.type_label, str(it.score),
                     f"{_hm(it.best_utc)} · {it.best_alt:.0f}°",
                     f"{_hm(it.window_start)}–{_hm(it.window_end)}"]
            for c, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if c == 0:
                    cell.setData(Qt.UserRole, it)
                if c == 2:
                    cell.setForeground(score_color(it.score))
                    cell.setToolTip(it.explain)
                t.setItem(r, c, cell)
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.cellDoubleClicked.connect(lambda *_: self._act("go"))
        if items:
            t.selectRow(0)
        return t

    def _focus(self, table) -> None:
        self._last_table = table

    def _current(self):
        t = self._last_table
        rows = t.selectionModel().selectedRows()
        if not rows:
            return None
        return t.item(rows[0].row(), 0).data(Qt.UserRole)

    def _act(self, what: str) -> None:
        it = self._current()
        if it is None:
            return
        if what == "go":
            self.gotoRequested.emit(it.kind, it.ident)
        elif what == "time" and it.best_utc is not None:
            self.gotoAtTimeRequested.emit(it.kind, it.ident, it.best_utc)
        elif what == "list":
            self.addToListRequested.emit(it.kind, it.ident)
