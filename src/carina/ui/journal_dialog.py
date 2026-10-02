"""Diário de observação (v0.15 T8).

:class:`ObservationDialog` registra (ou edita) uma observação: quando, onde,
com que instrumento, em que condições — Bortle, seeing e transparência de
1 a 5 —, uma avaliação de 0 a 5 estrelas e uma nota livre.
:class:`JournalWindow` lista o diário inteiro, com busca, edição,
exclusão, exportação CSV e "ir para" o objeto.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

SEEING = ["—", "1 · péssimo", "2 · ruim", "3 · razoável", "4 · bom", "5 · excelente"]
TRANSPARENCY = ["—", "1 · muito nublado", "2 · véu de nuvens", "3 · razoável",
                "4 · limpo", "5 · excepcional"]
RATING = ["—", "★", "★★", "★★★", "★★★★", "★★★★★"]


class ObservationDialog(QDialog):
    """Registrar / editar uma observação."""

    def __init__(self, object_name: str, when_utc: dt.datetime, location: str = "",
                 instruments: list[str] | None = None, bortle: int | None = None,
                 data: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        from ..core.localtime import from_local_naive, to_local

        self._from_local = from_local_naive
        self.setWindowTitle(self.tr("Observado — {n}").format(n=object_name))
        data = data or {}
        local = to_local(data.get("when_utc") or when_utc)
        self.when = QDateTimeEdit(QDateTime(local.year, local.month, local.day,
                                            local.hour, local.minute, 0))
        self.when.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.when.setCalendarPopup(True)
        self.location = QLineEdit(data.get("location") or location)
        self.instrument = QComboBox()
        self.instrument.setEditable(True)
        self.instrument.addItems(instruments or [])
        self.instrument.setCurrentText(data.get("instrument") or
                                       (instruments[0] if instruments else ""))
        self.bortle = QSpinBox()
        self.bortle.setRange(0, 9)
        self.bortle.setSpecialValueText("—")
        self.bortle.setValue(int(data.get("bortle") or bortle or 0))
        self.seeing = QComboBox()
        self.seeing.addItems([self.tr(s) for s in SEEING])
        self.seeing.setCurrentIndex(int(data.get("seeing") or 0))
        self.transparency = QComboBox()
        self.transparency.addItems([self.tr(s) for s in TRANSPARENCY])
        self.transparency.setCurrentIndex(int(data.get("transparency") or 0))
        self.rating = QComboBox()
        self.rating.addItems(RATING)
        self.rating.setCurrentIndex(int(data.get("rating") or 0))
        self.note = QPlainTextEdit(data.get("note") or "")
        self.note.setPlaceholderText(self.tr(
            "O que você viu? Detalhes, cores, comparação com a carta…"))

        form = QFormLayout()
        form.addRow(self.tr("Quando"), self.when)
        form.addRow(self.tr("Local"), self.location)
        form.addRow(self.tr("Instrumento"), self.instrument)
        form.addRow(self.tr("Bortle"), self.bortle)
        form.addRow(self.tr("Seeing"), self.seeing)
        form.addRow(self.tr("Transparência"), self.transparency)
        form.addRow(self.tr("Avaliação"), self.rating)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(QLabel(self.tr("Nota")))
        lay.addWidget(self.note, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(self.tr("Salvar"))
        buttons.button(QDialogButtonBox.Cancel).setText(self.tr("Cancelar"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(440, 460)

    def values(self) -> dict:
        """Campos prontos para ``UserData.add_observation``/``update``."""
        q = self.when.dateTime()
        naive = dt.datetime(q.date().year(), q.date().month(), q.date().day(),
                            q.time().hour(), q.time().minute())
        when = self._from_local(naive).astimezone(dt.timezone.utc)
        return {
            "when_utc": when,
            "location": self.location.text().strip(),
            "instrument": self.instrument.currentText().strip(),
            "bortle": self.bortle.value() or None,
            "seeing": self.seeing.currentIndex() or None,
            "transparency": self.transparency.currentIndex() or None,
            "rating": self.rating.currentIndex() or None,
            "note": self.note.toPlainText().strip(),
        }


COLUMNS = ["Data", "Hora", "Objeto", "Local", "Instrumento", "Bortle", "Seeing",
           "Transp.", "Avaliação", "Nota"]


class JournalWindow(QMainWindow):
    """Objetos ▸ Diário de observação…"""

    gotoRequested = Signal(str, str)        # (kind, ident)

    def __init__(self, userdata, instruments: list[str] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.ud = userdata
        self.instruments = instruments or []
        self.setWindowTitle(self.tr("Diário de observação"))
        self.resize(1000, 560)
        self._rows: list[dict] = []

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Filtrar por objeto, local, nota…"))
        self.summary = QLabel()
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.summary)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([self.tr(c) for c in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.Stretch)

        btn_goto = QPushButton(self.tr("Ir para"))
        btn_edit = QPushButton(self.tr("Editar…"))
        btn_delete = QPushButton(self.tr("Excluir"))
        btn_csv = QPushButton(self.tr("Exportar CSV…"))
        bottom = QHBoxLayout()
        for b in (btn_goto, btn_edit, btn_delete):
            bottom.addWidget(b)
        bottom.addStretch(1)
        bottom.addWidget(btn_csv)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)
        self.setCentralWidget(central)

        self.search.textChanged.connect(self._fill)
        self.table.cellDoubleClicked.connect(lambda *_: self._edit())
        btn_goto.clicked.connect(self._goto)
        btn_edit.clicked.connect(self._edit)
        btn_delete.clicked.connect(self._delete)
        btn_csv.clicked.connect(self._export)
        self.reload()

    def reload(self) -> None:
        self._all = self.ud.observations()
        self._fill()

    def _fill(self) -> None:
        from ..core.localtime import to_local

        text = self.search.text().strip().lower()
        rows = [o for o in self._all if not text or text in " ".join(
            str(o.get(k) or "") for k in ("name", "location", "instrument", "note")
        ).lower()]
        self._rows = rows
        self.table.setRowCount(len(rows))
        for r, o in enumerate(rows):
            loc = to_local(o["when_utc"])
            cells = [loc.strftime("%d/%m/%Y"), loc.strftime("%H:%M"), o["name"],
                     o["location"], o["instrument"], str(o["bortle"] or ""),
                     str(o["seeing"] or ""), str(o["transparency"] or ""),
                     RATING[o["rating"] or 0] if o["rating"] else "", o["note"]]
            for c, value in enumerate(cells):
                self.table.setItem(r, c, QTableWidgetItem(value))
        objects = {(o["kind"], o["ident"]) for o in self._all}
        nights = {to_local(o["when_utc"]).date() for o in self._all}
        self.summary.setText(self.tr("{n} registros · {o} objetos · {d} noites").format(
            n=len(self._all), o=len(objects), d=len(nights)))

    def _current(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        return self._rows[rows[0].row()] if rows else None

    def _goto(self) -> None:
        o = self._current()
        if o is not None:
            self.gotoRequested.emit(o["kind"], o["ident"])

    def _edit(self) -> None:
        o = self._current()
        if o is None:
            return
        dlg = ObservationDialog(o["name"], o["when_utc"], instruments=self.instruments,
                                data=o, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.ud.update_observation(o["id"], **dlg.values())
            self.reload()

    def _delete(self) -> None:
        o = self._current()
        if o is None:
            return
        answer = QMessageBox.question(self, self.tr("Diário"), self.tr(
            "Excluir o registro de {n}?").format(n=o["name"]))
        if answer == QMessageBox.Yes:
            self.ud.delete_observation(o["id"])
            self.reload()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar diário"), "diario_carina.csv", "CSV (*.csv)")
        if path:
            Path(path).write_text(self.ud.observations_csv(), encoding="utf-8-sig")
