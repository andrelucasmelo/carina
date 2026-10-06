"""Sistema Solar ▸ Caminho do Sol e analema (v0.22 T7).

A tabela do ano — nascer e ocaso do Sol com o azimute e a duração do dia,
semana a semana — e o atalho para a camada que desenha no céu o caminho do
Sol de hoje e o analema da hora atual.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ..core.localtime import to_local


def _dir(az: float | None) -> str:
    if az is None:
        return "—"
    from ..core.tours_generated import dir_pt

    return f"{az:.0f}° ({dir_pt(az)})"


class SunPathDialog(QDialog):
    def __init__(self, main, parent=None) -> None:
        super().__init__(parent or main)
        self.main = main
        self.setWindowTitle(self.tr("Caminho do Sol e analema"))
        self.resize(720, 620)
        lay = QVBoxLayout(self)
        intro = QLabel(self.tr(
            "O Sol nasce e se põe em pontos diferentes ao longo do ano: só perto dos "
            "equinócios (março e setembro) ele nasce no leste e se põe no oeste. A camada "
            "desenha no céu o caminho de hoje e o <b>analema</b> — o \"8\" que o Sol forma "
            "visto sempre à mesma hora do relógio."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        self.chk = QCheckBox(self.tr("Mostrar no céu"))
        act = main._layer_acts.get("sun_path")
        if act is not None:
            self.chk.setChecked(act.isChecked())
            self.chk.toggled.connect(act.setChecked)
        row.addWidget(self.chk)
        row.addStretch(1)
        row.addWidget(QLabel(self.tr("Ano:")))
        self.year = QSpinBox()
        self.year.setRange(1900, 2100)
        self.year.setValue(to_local(main.engine.time.current_datetime()).year)
        self.year.valueChanged.connect(self._fill)
        row.addWidget(self.year)
        lay.addLayout(row)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([self.tr("Data"), self.tr("Nascer"),
                                              self.tr("Azimute"), self.tr("Ocaso"),
                                              self.tr("Azimute"), self.tr("Duração do dia")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        close = QPushButton(self.tr("Fechar"))
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignRight)
        self._fill()

    def _fill(self, *_a) -> None:
        from PySide6.QtWidgets import QApplication

        from ..core.sunpath import year_table

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rows = year_table(self.main.engine, self.year.value())
        finally:
            QApplication.restoreOverrideCursor()
        self.table.setRowCount(len(rows))
        for r, d in enumerate(rows):
            length = d.day_length_h
            vals = [f"{d.date:%d/%m}",
                    f"{to_local(d.sunrise):%H:%M}" if d.sunrise else "—", _dir(d.sunrise_az),
                    f"{to_local(d.sunset):%H:%M}" if d.sunset else "—", _dir(d.sunset_az),
                    f"{int(length)} h {int(round((length % 1) * 60)):02d} min" if length else "—"]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.rows = rows
