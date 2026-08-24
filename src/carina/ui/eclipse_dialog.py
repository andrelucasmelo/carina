"""Diálogo de previsão de eclipses (item 4): lista + "ir para o máximo"."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..core.eclipses import find_eclipses


class EclipseDialog(QDialog):
    goto_requested = Signal(object, str)  # (datetime UTC, corpo: 'Lua'|'Sol')

    def __init__(self, engine, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle(self.tr("Eclipses lunares e solares"))
        self.resize(760, 460)

        self.years_spin = QSpinBox()
        self.years_spin.setRange(1, 20)
        self.years_spin.setValue(5)
        self.years_spin.setSuffix(self.tr(" anos"))
        self.kind_combo = QComboBox()
        self.kind_combo.addItem(self.tr("Todos"), "")
        self.kind_combo.addItem(self.tr("Lunares"), "lunar")
        self.kind_combo.addItem(self.tr("Solares"), "solar")
        self.kind_combo.currentIndexChanged.connect(self._fill)
        btn_calc = QPushButton(self.tr("Calcular"))
        btn_calc.clicked.connect(self._calc)

        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("A partir da data da simulação, por")))
        top.addWidget(self.years_spin)
        top.addWidget(self.kind_combo)
        top.addWidget(btn_calc)
        top.addStretch(1)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Data e hora (local)"), self.tr("Eclipse"),
             self.tr("Tipo"), self.tr("Detalhe"), self.tr("Alt. no máx."),
             self.tr("Visível daqui?")]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemDoubleClicked.connect(lambda _i: self._goto())

        btn_goto = QPushButton(self.tr("Ir para o máximo"))
        btn_goto.clicked.connect(self._goto)
        btn_close = QPushButton(self.tr("Fechar"))
        btn_close.clicked.connect(self.reject)
        hint = QLabel(self.tr(
            "Duplo clique leva ao instante do máximo (a simulação é pausada). "
            "Circunstâncias locais para a localização atual do observador."
        ))
        hint.setStyleSheet("color: #8a93a5; font-size: 8pt")

        bottom = QHBoxLayout()
        bottom.addWidget(hint, 1)
        bottom.addWidget(btn_goto)
        bottom.addWidget(btn_close)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addLayout(bottom)

        self._events = []
        self._calc()

    # ------------------------------------------------------------------
    def _calc(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            start = self.engine.time.current_datetime()
            self._events = find_eclipses(
                self.engine, start, float(self.years_spin.value())
            )
        finally:
            QApplication.restoreOverrideCursor()
        self._fill()

    def _fill(self) -> None:
        kind = self.kind_combo.currentData()
        events = [e for e in self._events if not kind or e.kind == kind]
        self.table.setRowCount(len(events))
        for r, ev in enumerate(events):
            local = ev.when_utc.astimezone()
            cells = [
                local.strftime("%d/%m/%Y %H:%M"),
                self.tr("Lunar") if ev.kind == "lunar" else self.tr("Solar"),
                ev.type_label,
                ev.detail,
                f"{ev.alt_deg:.0f}°",
                self.tr("sim") if ev.visible else self.tr("não"),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.UserRole, ev)
                if not ev.visible:
                    item.setForeground(QColor(120, 126, 138))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()

    def _goto(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        ev = self.table.item(row, 0).data(Qt.UserRole)
        body = "Lua" if ev.kind == "lunar" else "Sol"
        self.goto_requested.emit(ev.when_utc, body)
        self.accept()
