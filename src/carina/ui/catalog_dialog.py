"""Tela de configuração da exibição dos catálogos de céu profundo."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from ..catalogs.dso import ALL_CATALOGS, CATALOG_LABELS, EXTRA_CATALOGS


class CatalogDialog(QDialog):
    changed = Signal()

    def __init__(self, dso, parent=None) -> None:
        super().__init__(parent)
        self.dso = dso
        self.setWindowTitle(self.tr("Catálogos exibidos"))
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr(
            "Escolha quais catálogos aparecem no mapa. A contagem é do banco "
            "local — objetos desabilitados individualmente não são somados."
        )))

        self.checks: dict[str, QCheckBox] = {}
        for title, cats in (
            (self.tr("Catálogos clássicos"),
             [c for c in ALL_CATALOGS if c not in EXTRA_CATALOGS]),
            (self.tr("Catálogos adicionais"), EXTRA_CATALOGS),
        ):
            box = QGroupBox(title)
            vbox = QVBoxLayout(box)
            for cat in cats:
                n = self.dso.cx.execute(
                    "SELECT COUNT(DISTINCT object_id) c FROM designations"
                    " WHERE catalog = ?", (cat,),
                ).fetchone()["c"]
                chk = QCheckBox(
                    f"{CATALOG_LABELS.get(cat, cat)} — {n} objetos"
                )
                chk.setChecked(cat in self.dso.visible_catalogs)
                chk.toggled.connect(
                    lambda on, c=cat: self._toggle(c, on)
                )
                vbox.addWidget(chk)
                self.checks[cat] = chk
            layout.addWidget(box)

        row = QHBoxLayout()
        btn_all = QPushButton(self.tr("Marcar todos"))
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton(self.tr("Desmarcar todos"))
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_default = QPushButton(self.tr("Padrão"))
        btn_default.setToolTip(
            self.tr("Clássicos ligados, adicionais desligados")
        )
        btn_default.clicked.connect(self._defaults)
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        row.addWidget(btn_default)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _toggle(self, catalog: str, visible: bool) -> None:
        self.dso.set_catalog_visible(catalog, visible)
        self.changed.emit()

    def _set_all(self, value: bool) -> None:
        for cat, chk in self.checks.items():
            chk.setChecked(value)

    def _defaults(self) -> None:
        for cat, chk in self.checks.items():
            chk.setChecked(cat not in EXTRA_CATALOGS)
