"""Gerenciador de objetos de céu profundo (item 6): CRUD + categorias.

Todas as alterações acontecem na cópia do usuário do banco (dso.sqlite no
diretório de dados); "Restaurar padrão" volta ao banco embarcado.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ..catalogs.dso import DsoCatalog, type_label

CATALOG_FILTERS = [
    ("Todos os catálogos", ""),
    ("Messier (M)", "M"),
    ("Caldwell (C)", "C"),
    ("NGC", "NGC"),
    ("IC", "IC"),
    ("Sharpless (SH2)", "SH2"),
    ("Barnard (B)", "B"),
    ("Melotte (Mel)", "Mel"),
    ("Adicionados pelo usuário", "user"),
]

EDIT_TYPES = [
    ("G", "Galáxia", "GAL"),
    ("OCl", "Aglomerado aberto", "OC"),
    ("GCl", "Aglomerado globular", "GC"),
    ("PN", "Nebulosa planetária", "PN"),
    ("HII", "Região HII", "NEB"),
    ("EmN", "Nebulosa de emissão", "NEB"),
    ("RfN", "Nebulosa de reflexão", "NEB"),
    ("SNR", "Remanescente de supernova", "NEB"),
    ("DrkN", "Nebulosa escura", "DARK"),
    ("OCl+N", "Aglomerado com nebulosa", "NEB"),
    ("**", "Estrela dupla", "OTHER"),
    ("*Ass", "Associação estelar", "OTHER"),
    ("Other", "Outro", "OTHER"),
]


def _parse_angle(text: str, hours: bool) -> float | None:
    """Aceita decimal ('18.27') ou sexagesimal ('18:16:48' / '-24:07:30')."""
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        if ":" in text:
            parts = text.split(":")
            sign = -1.0 if parts[0].strip().startswith("-") else 1.0
            vals = [abs(float(p)) for p in parts] + [0.0, 0.0]
            value = sign * (vals[0] + vals[1] / 60.0 + vals[2] / 3600.0)
        else:
            value = float(text)
    except ValueError:
        return None
    return value * (math.pi / 12.0 if hours else math.pi / 180.0)


def _fmt_angle(rad: float, hours: bool) -> str:
    value = rad * (12.0 / math.pi if hours else 180.0 / math.pi)
    return f"{value:.5f}"


class DsoEditDialog(QDialog):
    """Formulário de inclusão/edição de um objeto."""

    def __init__(self, catalog: DsoCatalog, data: dict | None, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle(
            self.tr("Editar objeto") if data else self.tr("Novo objeto")
        )
        data = data or {}

        self.name_edit = QLineEdit(data.get("name", ""))
        self.type_combo = QComboBox()
        for code, label, _k in EDIT_TYPES:
            self.type_combo.addItem(f"{label} ({code})", code)
        if data.get("type"):
            i = next(
                (k for k, (c, _l, _x) in enumerate(EDIT_TYPES)
                 if c == data["type"]), len(EDIT_TYPES) - 1,
            )
            self.type_combo.setCurrentIndex(i)

        self.ra_edit = QLineEdit(
            _fmt_angle(data["ra"], True) if "ra" in data else ""
        )
        self.ra_edit.setPlaceholderText("horas: 18.28 ou 18:16:48")
        self.dec_edit = QLineEdit(
            _fmt_angle(data["dec"], False) if "dec" in data else ""
        )
        self.dec_edit.setPlaceholderText("graus: -24.12 ou -24:07:30")

        def spin(lo, hi, dec, value, suffix=""):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(dec)
            s.setSpecialValueText(self.tr("(vazio)"))
            s.setValue(value if value is not None else lo)
            if suffix:
                s.setSuffix(suffix)
            return s

        self.mag_spin = spin(-2.0, 30.0, 1, data.get("mag"))
        self.maj_spin = spin(0.0, 1200.0, 1, data.get("maj"), " ′")
        self.min_spin = spin(0.0, 1200.0, 1, data.get("min"), " ′")
        self.pa_spin = spin(0.0, 359.0, 0, data.get("pa"), "°")
        self.common_edit = QLineEdit(data.get("common") or "")
        self.notes_edit = QLineEdit(data.get("notes") or "")
        self.enabled_check = QCheckBox(self.tr("Habilitado (visível no mapa)"))
        self.enabled_check.setChecked(bool(data.get("enabled", 1)))

        self.cat_list = QListWidget()
        self.cat_list.setMaximumHeight(90)
        selected = set(data.get("categories", []))
        for name in catalog.categories():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if name in selected else Qt.Unchecked
            )
            self.cat_list.addItem(item)

        form = QFormLayout(self)
        form.addRow(self.tr("Designação:"), self.name_edit)
        form.addRow(self.tr("Tipo:"), self.type_combo)
        form.addRow(self.tr("AR (J2000):"), self.ra_edit)
        form.addRow(self.tr("Dec (J2000):"), self.dec_edit)
        form.addRow(self.tr("Magnitude:"), self.mag_spin)
        form.addRow(self.tr("Eixo maior:"), self.maj_spin)
        form.addRow(self.tr("Eixo menor:"), self.min_spin)
        form.addRow(self.tr("Ângulo de posição:"), self.pa_spin)
        form.addRow(self.tr("Nomes comuns:"), self.common_edit)
        form.addRow(self.tr("Notas:"), self.notes_edit)
        form.addRow(self.tr("Categorias:"), self.cat_list)
        form.addRow("", self.enabled_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _validate(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Carina", self.tr("Informe a designação."))
            return
        if _parse_angle(self.ra_edit.text(), True) is None or \
                _parse_angle(self.dec_edit.text(), False) is None:
            QMessageBox.warning(
                self, "Carina", self.tr("AR/Dec inválidas."),
            )
            return
        self.accept()

    def payload(self) -> dict:
        code = self.type_combo.currentData()
        klass = next(k for c, _l, k in EDIT_TYPES if c == code)

        def val(sp):
            return None if sp.value() == sp.minimum() else sp.value()

        cats = [
            self.cat_list.item(i).text()
            for i in range(self.cat_list.count())
            if self.cat_list.item(i).checkState() == Qt.Checked
        ]
        return {
            "name": self.name_edit.text().strip(),
            "type": code,
            "klass": klass,
            "ra": _parse_angle(self.ra_edit.text(), True),
            "dec": _parse_angle(self.dec_edit.text(), False),
            "mag": val(self.mag_spin),
            "maj": val(self.maj_spin),
            "min": val(self.min_spin),
            "pa": val(self.pa_spin),
            "con": None,
            "common": self.common_edit.text().strip() or None,
            "notes": self.notes_edit.text().strip() or None,
            "enabled": 1 if self.enabled_check.isChecked() else 0,
            "categories": cats,
        }


class DsoManagerDialog(QDialog):
    def __init__(self, catalog: DsoCatalog, parent=None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle(self.tr("Céu profundo — objetos e catálogos"))
        self.resize(880, 560)
        self._loading = False

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("Buscar por nome…"))
        self.search_edit.textChanged.connect(self.refresh)
        self.catalog_combo = QComboBox()
        for label, key in CATALOG_FILTERS:
            self.catalog_combo.addItem(label, key)
        self.catalog_combo.currentIndexChanged.connect(self.refresh)
        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(self.refresh)
        self.enabled_check = QCheckBox(self.tr("Somente habilitados"))
        self.enabled_check.toggled.connect(self.refresh)

        top = QHBoxLayout()
        top.addWidget(self.search_edit, 2)
        top.addWidget(self.catalog_combo, 1)
        top.addWidget(self.category_combo, 1)
        top.addWidget(self.enabled_check)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Visível"), self.tr("Nome"), self.tr("Tipo"),
             self.tr("Mag"), self.tr("Tam (′)"), self.tr("Const"),
             self.tr("Nome comum")]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(lambda _i: self._edit())

        self.count_label = QLabel()

        btn_new = QPushButton(self.tr("Novo…"))
        btn_new.clicked.connect(self._new)
        btn_edit = QPushButton(self.tr("Editar…"))
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton(self.tr("Remover"))
        btn_del.clicked.connect(self._delete)
        btn_cats = QPushButton(self.tr("Categorias…"))
        btn_cats.clicked.connect(self._categories)
        btn_reset = QPushButton(self.tr("Restaurar padrão…"))
        btn_reset.clicked.connect(self._restore)
        btn_close = QPushButton(self.tr("Fechar"))
        btn_close.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        for b in (btn_new, btn_edit, btn_del, btn_cats, btn_reset):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(btn_close)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(self.count_label)
        layout.addLayout(buttons)

        self._reload_categories()
        self.refresh()

    # ------------------------------------------------------------------
    def _reload_categories(self) -> None:
        self.category_combo.blockSignals(True)
        current = self.category_combo.currentData()
        self.category_combo.clear()
        self.category_combo.addItem(self.tr("Todas as categorias"), "")
        for name in self.catalog.categories():
            self.category_combo.addItem(name, name)
        if current:
            i = self.category_combo.findData(current)
            if i >= 0:
                self.category_combo.setCurrentIndex(i)
        self.category_combo.blockSignals(False)

    def refresh(self) -> None:
        self._loading = True
        rows = self.catalog.search(
            text=self.search_edit.text().strip(),
            catalog=self.catalog_combo.currentData() or "",
            category=self.category_combo.currentData() or "",
            only_enabled=self.enabled_check.isChecked(),
            limit=500,
        )
        self.table.setRowCount(len(rows))
        for r, obj in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
            )
            chk.setCheckState(Qt.Checked if obj["enabled"] else Qt.Unchecked)
            chk.setData(Qt.UserRole, obj["id"])
            self.table.setItem(r, 0, chk)
            name = obj["name"] + (" *" if obj["user_added"] else "")
            self.table.setItem(r, 1, QTableWidgetItem(name))
            self.table.setItem(r, 2, QTableWidgetItem(type_label(obj["type"])))
            self.table.setItem(
                r, 3,
                QTableWidgetItem("" if obj["mag"] is None else f"{obj['mag']:.1f}"),
            )
            self.table.setItem(
                r, 4,
                QTableWidgetItem("" if not obj["maj"] else f"{obj['maj']:.0f}"),
            )
            self.table.setItem(r, 5, QTableWidgetItem(obj["con"] or ""))
            self.table.setItem(r, 6, QTableWidgetItem(obj["common"] or ""))
        total = self.catalog.count(
            text=self.search_edit.text().strip(),
            catalog=self.catalog_combo.currentData() or "",
            category=self.category_combo.currentData() or "",
            only_enabled=self.enabled_check.isChecked(),
        )
        shown = len(rows)
        msg = self.tr("{n} objetos").format(n=total)
        if total > shown:
            msg += self.tr(" (mostrando os {s} mais brilhantes — refine o filtro)").format(s=shown)
        msg += self.tr(" · * = adicionado pelo usuário")
        self.count_label.setText(msg)
        self._loading = False

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 0:
            return
        oid = item.data(Qt.UserRole)
        self.catalog.set_enabled(oid, item.checkState() == Qt.Checked)

    def _new(self) -> None:
        dlg = DsoEditDialog(self.catalog, None, self)
        if dlg.exec():
            self.catalog.upsert(dlg.payload())
            self._reload_categories()
            self.refresh()

    def _edit(self) -> None:
        oid = self._selected_id()
        if oid is None:
            return
        data = self.catalog.get(oid)
        dlg = DsoEditDialog(self.catalog, data, self)
        if dlg.exec():
            self.catalog.upsert(dlg.payload(), object_id=oid)
            self._reload_categories()
            self.refresh()

    def _delete(self) -> None:
        oid = self._selected_id()
        if oid is None:
            return
        data = self.catalog.get(oid)
        if QMessageBox.question(
            self, "Carina",
            self.tr("Remover \"{name}\" do banco local?\n"
                    "(\"Restaurar padrão\" desfaz remoções de objetos de fábrica.)"
                    ).format(name=data["name"]),
        ) == QMessageBox.Yes:
            self.catalog.delete(oid)
            self.refresh()

    def _categories(self) -> None:
        while True:
            names = self.catalog.categories()
            name, ok = QInputDialog.getItem(
                self, self.tr("Categorias"),
                self.tr("Selecione para REMOVER, ou digite um novo nome para "
                        "CRIAR e confirme:"),
                names, 0, True,
            )
            if not ok:
                break
            name = name.strip()
            if not name:
                continue
            if name in names:
                if QMessageBox.question(
                    self, "Carina",
                    self.tr("Remover a categoria \"{n}\"?").format(n=name),
                ) == QMessageBox.Yes:
                    self.catalog.remove_category(name)
            else:
                self.catalog.add_category(name)
        self._reload_categories()
        self.refresh()

    def _restore(self) -> None:
        if QMessageBox.question(
            self, "Carina",
            self.tr("Descartar TODAS as alterações locais e restaurar o banco "
                    "padrão do aplicativo?"),
        ) == QMessageBox.Yes:
            self.catalog.restore_default()
            self._reload_categories()
            self.refresh()
