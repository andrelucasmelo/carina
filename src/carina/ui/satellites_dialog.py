"""Planejar ▸ Satélites e ISS (v0.19 T7).

Importa elementos orbitais (TLE) de um arquivo ou do texto colado, lista
as próximas passagens do satélite escolhido (visíveis em destaque) e
desenha a trilha da passagem no céu. Sem acesso à internet: o usuário
baixa o arquivo (ex.: ``stations.txt`` da CelesTrak) e importa aqui.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QListWidget, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import orbital as O
from ..core.localtime import to_local

UTC = dt.timezone.utc


class SatellitesDialog(QDialog):
    showPass = Signal(object, object)      # (Tle, Pass) → trilha no céu e relógio

    def __init__(self, engine, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Satélites e ISS"))
        self.engine = engine
        self.tles = O.load_saved()
        self.passes: list[O.Pass] = []

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._chosen)
        imp = QPushButton(self.tr("Importar arquivo TLE…"))
        imp.clicked.connect(self._import_file)
        paste = QPushButton(self.tr("Colar TLE…"))
        paste.clicked.connect(self._paste)
        self.lbl_age = QLabel()
        self.lbl_age.setWordWrap(True)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.list, 1)
        ll.addWidget(imp)
        ll.addWidget(paste)
        ll.addWidget(self.lbl_age)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            self.tr("Dia"), self.tr("Nasce"), self.tr("Ponto mais alto"), self.tr("Some"),
            self.tr("Altura máx."), self.tr("Visível")])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._show(r))
        show = QPushButton(self.tr("Mostrar a passagem no céu"))
        show.clicked.connect(lambda: self._show(self.table.currentRow()))
        hint = QLabel(self.tr(
            "Visível = o satélite está iluminado pelo Sol e o seu céu está escuro. "
            "Os elementos orbitais envelhecem: atualize o arquivo a cada poucos dias "
            "(CelesTrak → \"Space Stations\", arquivo stations.txt)."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a93a5")
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.table, 1)
        rl.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(show)
        rl.addLayout(row)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        self.resize(900, 520)
        self._fill_list()

    def _fill_list(self) -> None:
        self.list.clear()
        for t in self.tles:
            self.list.addItem(t.name)
        if not self.tles:
            self.lbl_age.setText(self.tr("Nenhum satélite. Importe um arquivo TLE."))
            self.table.setRowCount(0)
            return
        iss = O.iss(self.tles)
        self.list.setCurrentRow(self.tles.index(iss) if iss in self.tles else 0)

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Importar TLE"), "",
                                              self.tr("Elementos orbitais (*.txt *.tle);;Todos (*)"))
        if path:
            with open(path, encoding="utf-8", errors="replace") as fh:
                self.import_text(fh.read())

    def _paste(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, self.tr("Colar TLE"),
                                                 self.tr("Elementos orbitais (2 ou 3 linhas por satélite):"))
        if ok and text.strip():
            self.import_text(text)

    def import_text(self, text: str) -> int:
        tles = O.save(text)
        if not tles:
            QMessageBox.warning(self, self.tr("Satélites"),
                                self.tr("Nenhum elemento orbital válido no texto."))
            return 0
        self.tles = tles
        self._fill_list()
        return len(tles)

    def _chosen(self, row: int) -> None:
        if not (0 <= row < len(self.tles)):
            return
        tle = self.tles[row]
        now = self.engine.time.current_datetime()
        age = tle.age_days(now)
        warn = (self.tr(" — antigos: as previsões já podem errar por minutos")
                if abs(age) > O.MAX_AGE_DAYS else "")
        self.lbl_age.setText(self.tr("Elementos de {d:%d/%m/%Y} ({a:.0f} dias){w}.").format(
            d=to_local(tle.epoch), a=age, w=warn))
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.passes = O.passes(self.engine, tle, now - dt.timedelta(minutes=20), days=4)
        finally:
            QApplication.restoreOverrideCursor()
        self.table.setRowCount(len(self.passes))
        days = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
        for r, p in enumerate(self.passes):
            lr, lc, ls = to_local(p.rise), to_local(p.culminate), to_local(p.set)
            cells = [f"{days[lr.weekday()]} {lr:%d/%m}",
                     f"{lr:%H:%M:%S} ({O.direction_name(p.rise_az)})", f"{lc:%H:%M:%S}",
                     f"{ls:%H:%M:%S} ({O.direction_name(p.set_az)})", f"{p.max_alt:.0f}°",
                     (f"sim, {to_local(p.visible_from):%H:%M}–{to_local(p.visible_to):%H:%M}"
                      if p.visible else "não")]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if not p.visible:
                    it.setForeground(QColor(130, 130, 140))
                self.table.setItem(r, c, it)

    def _show(self, row: int) -> None:
        r = self.list.currentRow()
        if 0 <= row < len(self.passes) and 0 <= r < len(self.tles):
            self.showPass.emit(self.tles[r], self.passes[row])
