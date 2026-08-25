"""Diálogo "Ir para data/hora" da simulação."""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate, QDateTime, QTime
from PySide6.QtWidgets import (
    QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
)


class TimeDialog(QDialog):
    def __init__(self, current_local: dt.datetime, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Ir para data e hora"))

        # monta o QDateTime pelos COMPONENTES da hora local do observador
        # (fromSecsSinceEpoch exibiria no fuso do computador, que pode ser
        # outro quando o usuário escolheu uma cidade distante)
        c = current_local
        self.edit = QDateTimeEdit(QDateTime(
            QDate(c.year, c.month, c.day), QTime(c.hour, c.minute, c.second)
        ))
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
        """Instante escolhido, convertido para UTC.

        A hora digitada é interpretada no fuso do OBSERVADOR (a cidade
        escolhida), não no do computador — "22:00" numa viagem planejada
        para o Atacama significa 22:00 de lá.
        """
        from ..core.localtime import from_local_naive

        local = self.edit.dateTime().toPython()
        return from_local_naive(local).astimezone(dt.timezone.utc)
