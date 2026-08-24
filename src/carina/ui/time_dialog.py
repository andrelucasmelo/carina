"""Diálogo "Ir para data/hora" da simulação."""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
)


class TimeDialog(QDialog):
    def __init__(self, current_local: dt.datetime, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Ir para data e hora"))

        self.edit = QDateTimeEdit(
            QDateTime.fromSecsSinceEpoch(int(current_local.timestamp()))
        )
        self.edit.setDisplayFormat("dd/MM/yyyy HH:mm:ss")
        self.edit.setCalendarPopup(True)

        form = QFormLayout(self)
        form.addRow(self.tr("Data e hora (local):"), self.edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def datetime_utc(self) -> dt.datetime:
        """Instante escolhido, convertido para UTC."""
        local = self.edit.dateTime().toPython()
        return local.astimezone().astimezone(dt.timezone.utc)
