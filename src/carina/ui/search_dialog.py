"""Busca de objetos (Ctrl+F): estrelas, Sistema Solar e céu profundo.

Aceita nome próprio ("Antares"), nome comum ("Lagoon"), corpo ("Lua") e
designações diretas ("m42", "ngc 7000", "sh2-155", "b33", "mel 25", "c14",
"hip 32349"). Enter ou duplo clique centraliza a câmera no objeto.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)

from ..catalogs.dso import DsoCatalog, type_label
from ..catalogs.stars import StarCatalog
from ..core.engine import _BODIES

_CATALOG_PREFIX = {
    "m": "M", "ngc": "NGC", "ic": "IC", "sh2": "SH2", "sh": "SH2",
    "b": "B", "mel": "Mel", "c": "C",
}


class SearchDialog(QDialog):
    """Busca unificada (estrelas, céu profundo e corpos do Sistema Solar)
    com resultados ao digitar; Enter ou duplo clique centraliza no céu."""

    goto_requested = Signal(object)  # ("star"|"dso"|"body", chave)

    def __init__(self, stars: StarCatalog, dso: DsoCatalog, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Buscar objeto"))
        self.resize(430, 420)
        self.stars = stars
        self.dso = dso

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(
            self.tr("Nome, designação (M 42, NGC 7000, Sh2-155…) ou corpo")
        )
        self.edit.textChanged.connect(self._update)
        self.edit.returnPressed.connect(self._go_first)
        self.list = QListWidget()
        self.list.itemActivated.connect(self._go_item)
        self.hint = QLabel(
            self.tr("Enter centraliza no primeiro resultado · Esc fecha")
        )
        self.hint.setStyleSheet("color: #8a93a5; font-size: 8pt")

        layout = QVBoxLayout(self)
        layout.addWidget(self.edit)
        layout.addWidget(self.list)
        layout.addWidget(self.hint)

    # ------------------------------------------------------------------
    def _add(self, results, seen, selection, label, sort_key) -> None:
        if selection in seen:
            return
        seen.add(selection)
        results.append((sort_key, label, selection))

    def _update(self, text: str) -> None:
        self.list.clear()
        text = text.strip()
        if len(text) < 2:
            return
        tl = text.lower()
        results: list[tuple] = []
        seen: set = set()

        # corpos do Sistema Solar
        for name, _key, _color in _BODIES:
            if tl in name.lower():
                self._add(results, seen, ("body", name),
                          f"{name} — Sistema Solar", (0, 0.0))

        # designação direta (M 42, NGC 7000, B 33, HIP 32349…)
        mm = re.match(r"^([a-z]+)[\s\-]*([0-9].*)$", tl)
        if mm:
            prefix, ident = mm.group(1), mm.group(2).strip()
            if prefix == "hip":
                try:
                    import numpy as np

                    hits = np.nonzero(self.stars.hip == int(ident))[0]
                    if len(hits):
                        idx = int(hits[0])
                        self._add(
                            results, seen, ("star", idx),
                            f"HIP {int(ident)} — "
                            f"{self.stars.full_designation(idx)}",
                            (1, float(self.stars.mag[idx])),
                        )
                except ValueError:
                    pass
            cat = _CATALOG_PREFIX.get(prefix)
            if cat:
                rows = self.dso.cx.execute(
                    "SELECT o.id, o.name, o.type, o.mag, o.common"
                    " FROM designations d JOIN objects o ON o.id = d.object_id"
                    " WHERE d.catalog = ? AND d.ident LIKE ?"
                    " ORDER BY LENGTH(d.ident), d.ident LIMIT 12",
                    (cat, ident + "%"),
                ).fetchall()
                for r in rows:
                    label = f"{r['name']} — {type_label(r['type'])}"
                    if r["common"]:
                        label += f" · {r['common'].split(',')[0]}"
                    self._add(results, seen, ("dso", int(r["id"])), label,
                              (2, r["mag"] if r["mag"] is not None else 99.0))

        # estrelas por nome próprio
        for idx, nm in self.stars.proper.items():
            if tl in nm.lower():
                mag = float(self.stars.mag[idx])
                self._add(results, seen, ("star", int(idx)),
                          f"{nm} — estrela, mag {mag:.1f}", (1, mag))

        # céu profundo por nome/nome comum
        for r in self.dso.search(text=text, limit=25):
            label = f"{r['name']} — {type_label(r['type'])}"
            if r["common"]:
                label += f" · {r['common'].split(',')[0]}"
            self._add(results, seen, ("dso", int(r["id"])), label,
                      (3, r["mag"] if r["mag"] is not None else 99.0))

        results.sort(key=lambda item: item[0])
        for _key, label, selection in results[:40]:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, selection)
            self.list.addItem(item)

    # ------------------------------------------------------------------
    def _go_item(self, item: QListWidgetItem) -> None:
        self.goto_requested.emit(item.data(Qt.UserRole))
        self.accept()

    def _go_first(self) -> None:
        if self.list.count():
            self._go_item(self.list.item(0))
