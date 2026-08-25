"""Diálogo de localização do observador.

Duas formas de escolher o local:

* **pela lista de cidades** — a base embarcada traz as 500 cidades mais
  populosas do mundo mais os top 100 de Brasil, EUA, China e Europa
  (GeoNames, CC BY 4.0). Um campo de busca filtra por nome ou país e a
  escolha preenche coordenadas, elevação e fuso horário de uma vez;
* **manualmente** — os campos continuam editáveis para qualquer sítio de
  observação fora da lista (o fuso, nesse caso, é o da última cidade ou o
  do sistema).
"""

from __future__ import annotations

import json
from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)

from ..config import ObserverLocation, package_data_dir


@lru_cache(maxsize=1)
def load_cities() -> list[dict]:
    """Carrega a base de cidades uma única vez (ordenada por população)."""
    path = package_data_dir() / "cities.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


class LocationDialog(QDialog):
    """Escolha do local: lista pesquisável de 745 cidades + campos manuais
    (ver a doc do módulo)."""

    def __init__(self, loc: ObserverLocation, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Localização do observador"))
        self.resize(560, 520)
        self._tz = loc.timezone

        layout = QVBoxLayout(self)

        # --- busca na base de cidades ----------------------------------
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            self.tr("Buscar cidade ou país (ex.: Lisboa, Chile, Tokyo)…")
        )
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.itemActivated.connect(self._apply_city)
        self.list.itemClicked.connect(self._apply_city)
        layout.addWidget(self.list, 1)

        hint = QLabel(self.tr(
            "745 cidades disponíveis (as maiores do mundo, do Brasil, dos "
            "EUA, da China e da Europa). Escolher uma preenche os campos e "
            "o fuso horário; os campos abaixo continuam editáveis."
        ))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a93a5")
        layout.addWidget(hint)

        # --- campos manuais --------------------------------------------
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
        self.tz_label = QLabel(loc.timezone or self.tr("fuso do sistema"))

        form = QFormLayout()
        form.addRow(self.tr("Nome:"), self.name_edit)
        row = QHBoxLayout()
        row.addWidget(self.lat_spin)
        row.addWidget(QLabel(self.tr("Longitude:")))
        row.addWidget(self.lon_spin)
        form.addRow(self.tr("Latitude:"), row)
        row2 = QHBoxLayout()
        row2.addWidget(self.elev_spin)
        row2.addWidget(QLabel(self.tr("Fuso:")))
        row2.addWidget(self.tz_label, 1)
        form.addRow(self.tr("Elevação:"), row2)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._filter("")

    # ------------------------------------------------------------------
    def _filter(self, text: str) -> None:
        """Preenche a lista com as cidades que casam com a busca.

        Sem busca mostra as 60 mais populosas; com busca, até 200
        resultados por substring no nome ou no país (sem acento não é
        tratado — a base tem os nomes internacionais usuais).
        """
        needle = text.strip().lower()
        self.list.clear()
        shown = 0
        limit = 200 if needle else 60
        for city in load_cities():
            if needle and (needle not in city["n"].lower()
                           and needle not in city["c"].lower()):
                continue
            item = QListWidgetItem(
                f"{city['n']} — {city['c']}   "
                f"({city['lat']:+.2f}°, {city['lon']:+.2f}°, "
                f"{city['pop'] / 1e6:.1f} M hab)"
            )
            item.setData(Qt.UserRole, city)
            self.list.addItem(item)
            shown += 1
            if shown >= limit:
                break

    def _apply_city(self, item: QListWidgetItem) -> None:
        city = item.data(Qt.UserRole)
        if not city:
            return
        self.name_edit.setText(f"{city['n']}, {city['c']}")
        self.lat_spin.setValue(city["lat"])
        self.lon_spin.setValue(city["lon"])
        self.elev_spin.setValue(float(city["el"]))
        self._tz = city["tz"]
        self.tz_label.setText(city["tz"])

    def location(self) -> ObserverLocation:
        return ObserverLocation(
            name=self.name_edit.text().strip() or self.tr("Local personalizado"),
            latitude=self.lat_spin.value(),
            longitude=self.lon_spin.value(),
            elevation=self.elev_spin.value(),
            timezone=self._tz,
        )
