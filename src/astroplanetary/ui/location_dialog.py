"""Diálogo de localização do observador."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLineEdit,
)

from ..config import ObserverLocation


class LocationDialog(QDialog):
    def __init__(self, loc: ObserverLocation, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Localização do observador"))

        self.name_edit = QLineEdit(loc.name)
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90.0, 90.0)
        self.lat_spin.setDecimals(4)
        self.lat_spin.setSuffix("°")
        self.lat_spin.setValue(loc.latitude)
        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180.0, 180.0)
        self.lon_spin.setDecimals(4)
        self.lon_spin.setSuffix("°")
        self.lon_spin.setValue(loc.longitude)
        self.elev_spin = QDoubleSpinBox()
        self.elev_spin.setRange(-430.0, 9000.0)
        self.elev_spin.setDecimals(0)
        self.elev_spin.setSuffix(" m")
        self.elev_spin.setValue(loc.elevation)

        form = QFormLayout(self)
        form.addRow(self.tr("Nome:"), self.name_edit)
        form.addRow(self.tr("Latitude (sul negativo):"), self.lat_spin)
        form.addRow(self.tr("Longitude (oeste negativo):"), self.lon_spin)
        form.addRow(self.tr("Elevação:"), self.elev_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def location(self) -> ObserverLocation:
        return ObserverLocation(
            name=self.name_edit.text().strip() or self.tr("Local personalizado"),
            latitude=self.lat_spin.value(),
            longitude=self.lon_spin.value(),
            elevation=self.elev_spin.value(),
        )
