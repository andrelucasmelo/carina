"""Tela de filtros do céu profundo (revisão 2026-10, §9).

Substitui a antiga "Catálogos exibidos": além dos catálogos, filtra por
tipo, faixa de magnitude e de tamanho angular, só nomeados / só Messier-
Caldwell, e define como tratar as regiões gigantes (Sh2, Barnard, LDN).
Não modal: cada mudança vai para o mapa na hora, com a contagem de quantos
objetos passam. Presets prontos e presets do usuário (salvos nas
preferências).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
    QVBoxLayout,
)

from ..catalogs.dso import ALL_CATALOGS, CATALOG_LABELS, KLASS_CODES
from ..config import Settings
from ..core.dsofilter import (
    BIG_MODES, CLASS_LABELS, PRESETS, DsoFilter, arcmin_label,
)

CUSTOM = "Personalizado"


class _LimitSpin(QDoubleSpinBox):
    """QDoubleSpinBox que mostra um texto especial também no MÁXIMO
    (o Qt só oferece isso para o mínimo): o limite superior vira
    "sem limite"."""

    def __init__(self, special_max: str = "", parent=None) -> None:
        super().__init__(parent)
        self._special_max = special_max

    def textFromValue(self, value: float) -> str:  # noqa: N802 (Qt)
        if self._special_max and value >= self.maximum():
            return self._special_max
        return super().textFromValue(value)

    def valueFromText(self, text: str) -> float:  # noqa: N802 (Qt)
        if self._special_max and text.strip() == self._special_max:
            return self.maximum()
        return super().valueFromText(text)
USER_PRESETS_KEY = "dso/user_presets"


class DsoFilterDialog(QDialog):
    """Filtros de exibição do céu profundo; emite ``changed(DsoFilter)``."""

    changed = Signal(object)

    def __init__(self, dso, current: DsoFilter, parent=None) -> None:
        super().__init__(parent)
        self.dso = dso
        self.settings = Settings()
        self._loading = False
        self.setWindowTitle(self.tr("Céu profundo — filtros de exibição"))
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)

        # --- presets -------------------------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Preset:")))
        self.cb_preset = QComboBox()
        self._fill_presets()
        self.cb_preset.currentIndexChanged.connect(self._apply_preset)
        row.addWidget(self.cb_preset, 1)
        btn_save = QPushButton(self.tr("Salvar como…"))
        btn_save.clicked.connect(self._save_preset)
        btn_del = QPushButton(self.tr("Excluir"))
        btn_del.clicked.connect(self._delete_preset)
        row.addWidget(btn_save)
        row.addWidget(btn_del)
        root.addLayout(row)

        # --- catálogos -----------------------------------------------------
        box = QGroupBox(self.tr("Catálogos"))
        grid = QGridLayout(box)
        counts = dso.cat_matrix.sum(axis=0) if len(dso.mag) else [0] * len(ALL_CATALOGS)
        self.chk_cat: dict[str, QCheckBox] = {}
        for i, cat in enumerate(ALL_CATALOGS):
            chk = QCheckBox(f"{CATALOG_LABELS.get(cat, cat)} ({int(counts[i]):,})".replace(",", "."))
            chk.toggled.connect(self._emit)
            grid.addWidget(chk, i // 3, i % 3)
            self.chk_cat[cat] = chk
        brow = QHBoxLayout()
        for label, value in ((self.tr("Marcar todos"), True), (self.tr("Desmarcar todos"), False)):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, v=value: self._set_all(self.chk_cat, v))
            brow.addWidget(b)
        brow.addStretch(1)
        grid.addLayout(brow, (len(ALL_CATALOGS) + 2) // 3, 0, 1, 3)
        root.addWidget(box)

        # --- tipos -----------------------------------------------------------
        box = QGroupBox(self.tr("Tipos de objeto"))
        grid = QGridLayout(box)
        self.chk_cls: dict[str, QCheckBox] = {}
        for i, (code, label) in enumerate(CLASS_LABELS.items()):
            chk = QCheckBox(label)
            chk.toggled.connect(self._emit)
            grid.addWidget(chk, i // 3, i % 3)
            self.chk_cls[code] = chk
        root.addWidget(box)

        # --- magnitude e tamanho ---------------------------------------------
        box = QGroupBox(self.tr("Brilho e tamanho"))
        form = QFormLayout(box)
        self.sp_mag_min = self._spin(-30.0, 25.0, 1, self.tr("sem limite"), -30.0)
        self.sp_mag_max = self._spin(-5.0, 30.0, 1, self.tr("sem limite"), 30.0, special_at_max=True)
        self.chk_unknown_mag = QCheckBox(self.tr("incluir objetos sem magnitude (nebulosas escuras, p. ex.)"))
        self.chk_unknown_mag.toggled.connect(self._emit)
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel(self.tr("de"))); mrow.addWidget(self.sp_mag_min)
        mrow.addWidget(QLabel(self.tr("até"))); mrow.addWidget(self.sp_mag_max)
        mrow.addStretch(1)
        form.addRow(self.tr("Magnitude:"), mrow)
        form.addRow("", self.chk_unknown_mag)
        self.sp_size_min = self._spin(0.0, 3000.0, 0, self.tr("sem limite"), 0.0, suffix=" ′")
        self.sp_size_max = self._spin(1.0, 100000.0, 0, self.tr("sem limite"), 100000.0, suffix=" ′", special_at_max=True)
        self.chk_unknown_size = QCheckBox(self.tr("incluir objetos sem tamanho"))
        self.chk_unknown_size.toggled.connect(self._emit)
        srow = QHBoxLayout()
        srow.addWidget(QLabel(self.tr("de"))); srow.addWidget(self.sp_size_min)
        srow.addWidget(QLabel(self.tr("até"))); srow.addWidget(self.sp_size_max)
        srow.addStretch(1)
        form.addRow(self.tr("Tamanho angular:"), srow)
        form.addRow("", self.chk_unknown_size)
        self.chk_named = QCheckBox(self.tr("só objetos com nome comum"))
        self.chk_mc = QCheckBox(self.tr("só Messier e Caldwell"))
        for chk in (self.chk_named, self.chk_mc):
            chk.toggled.connect(self._emit)
        form.addRow("", self.chk_named)
        form.addRow("", self.chk_mc)
        root.addWidget(box)

        # --- regiões grandes -------------------------------------------------
        box = QGroupBox(self.tr("Regiões gigantes (Sharpless, Barnard, LDN…)"))
        form = QFormLayout(box)
        self.cb_big = QComboBox()
        for code, label in BIG_MODES.items():
            self.cb_big.addItem(label, code)
        self.cb_big.currentIndexChanged.connect(self._emit)
        form.addRow(self.tr("Tratamento:"), self.cb_big)
        self.sp_big = self._spin(30.0, 1200.0, 0, "", 120.0, suffix=" ′")
        self.sp_big.setSingleStep(30.0)
        self.lbl_big = QLabel()
        hrow = QHBoxLayout()
        hrow.addWidget(self.sp_big)
        hrow.addWidget(self.lbl_big)
        hrow.addStretch(1)
        form.addRow(self.tr("Conta como gigante a partir de:"), hrow)
        self.sp_fov = self._spin(5.0, 100.0, 0, "", 40.0, suffix=" °")
        form.addRow(self.tr("Ocultar quando o campo passar de:"), self.sp_fov)
        root.addWidget(box)

        # --- rodapé ----------------------------------------------------------
        self.lbl_count = QLabel()
        root.addWidget(self.lbl_count)
        brow = QHBoxLayout()
        btn_default = QPushButton(self.tr("Padrão"))
        btn_default.clicked.connect(lambda: self.set_filter(DsoFilter()))
        btn_close = QPushButton(self.tr("Fechar"))
        btn_close.clicked.connect(self.accept)
        brow.addWidget(btn_default)
        brow.addStretch(1)
        brow.addWidget(btn_close)
        root.addLayout(brow)

        self.set_filter(current)

    # ------------------------------------------------------------------
    def _spin(self, lo, hi, decimals, special, value, suffix="",
              special_at_max=False) -> QDoubleSpinBox:
        sp = _LimitSpin(special if special_at_max else "")
        sp.setRange(lo, hi)
        sp.setDecimals(decimals)
        if suffix:
            sp.setSuffix(suffix)
        if special and not special_at_max:
            sp.setSpecialValueText(special)
        sp.setValue(value)
        sp.valueChanged.connect(self._emit)
        return sp

    @staticmethod
    def _set_all(checks: dict, value: bool) -> None:
        for chk in checks.values():
            chk.setChecked(value)

    def _fill_presets(self) -> None:
        self.cb_preset.blockSignals(True)
        self.cb_preset.clear()
        self.cb_preset.addItem(CUSTOM, None)
        for name in PRESETS:
            self.cb_preset.addItem(name, PRESETS[name].to_json())
        for name, text in self._user_presets().items():
            self.cb_preset.addItem(f"{name} (meu)", text)
        self.cb_preset.blockSignals(False)

    def _user_presets(self) -> dict[str, str]:
        import json

        raw = self.settings.value(USER_PRESETS_KEY, "{}", str)
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = {}
        return {k: v for k, v in data.items() if isinstance(v, str)}

    def _store_user_presets(self, presets: dict[str, str]) -> None:
        import json

        self.settings.set_value(
            USER_PRESETS_KEY, json.dumps(presets, ensure_ascii=False)
        )

    # ------------------------------------------------------------------
    def set_filter(self, f: DsoFilter) -> None:
        """Preenche os controles a partir de um filtro e emite uma vez."""
        self._loading = True
        try:
            for cat, chk in self.chk_cat.items():
                chk.setChecked(cat in f.catalogs)
            for code, chk in self.chk_cls.items():
                chk.setChecked(code in f.classes)
            self.sp_mag_min.setValue(f.mag_min)
            self.sp_mag_max.setValue(f.mag_max)
            self.chk_unknown_mag.setChecked(f.include_unknown_mag)
            self.sp_size_min.setValue(f.size_min)
            self.sp_size_max.setValue(min(f.size_max, self.sp_size_max.maximum()))
            self.chk_unknown_size.setChecked(f.include_unknown_size)
            self.chk_named.setChecked(f.only_named)
            self.chk_mc.setChecked(f.only_mc)
            self.cb_big.setCurrentIndex(max(0, self.cb_big.findData(f.big_mode)))
            self.sp_big.setValue(f.big_threshold_arcmin)
            self.sp_fov.setValue(f.big_hide_fov_deg)
        finally:
            self._loading = False
        self._emit()

    def current_filter(self) -> DsoFilter:
        """Lê os controles e devolve o filtro correspondente."""
        f = DsoFilter()
        f.catalogs = {c for c, chk in self.chk_cat.items() if chk.isChecked()}
        f.classes = {c for c, chk in self.chk_cls.items() if chk.isChecked()}
        f.mag_min = self.sp_mag_min.value()
        f.mag_max = self.sp_mag_max.value()
        f.include_unknown_mag = self.chk_unknown_mag.isChecked()
        f.size_min = self.sp_size_min.value()
        f.size_max = self.sp_size_max.value()
        f.include_unknown_size = self.chk_unknown_size.isChecked()
        f.only_named = self.chk_named.isChecked()
        f.only_mc = self.chk_mc.isChecked()
        f.big_mode = self.cb_big.currentData() or "outline"
        f.big_threshold_arcmin = self.sp_big.value()
        f.big_hide_fov_deg = self.sp_fov.value()
        return f

    def _emit(self, *_args) -> None:
        if self._loading:
            return
        f = self.current_filter()
        self.sp_fov.setEnabled(f.big_mode == "hide")
        self.lbl_big.setText(arcmin_label(f.big_threshold_arcmin))
        total = len(self.dso.mag)
        passing = int(f.mask(self.dso).sum()) if total else 0
        self.lbl_count.setText(self.tr(
            "<b>{p}</b> de {t} objetos passam no filtro"
        ).format(p=f"{passing:,}".replace(",", "."),
                 t=f"{total:,}".replace(",", ".")))
        # o preset selecionado deixa de valer quando algo muda
        self.cb_preset.blockSignals(True)
        idx = self.cb_preset.findData(f.to_json())
        self.cb_preset.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_preset.blockSignals(False)
        self.changed.emit(f)

    def _apply_preset(self, index: int) -> None:
        text = self.cb_preset.itemData(index)
        if text:
            self.set_filter(DsoFilter.from_json(text))

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self, self.tr("Salvar preset"), self.tr("Nome do preset:")
        )
        name = name.strip()
        if not ok or not name:
            return
        presets = self._user_presets()
        presets[name] = self.current_filter().to_json()
        self._store_user_presets(presets)
        self._fill_presets()
        self.cb_preset.setCurrentIndex(self.cb_preset.findData(presets[name]))

    def _delete_preset(self) -> None:
        label = self.cb_preset.currentText()
        if not label.endswith(" (meu)"):
            QMessageBox.information(self, "Carina", self.tr(
                "Só os presets que você salvou podem ser excluídos."
            ))
            return
        presets = self._user_presets()
        presets.pop(label[:-len(" (meu)")], None)
        self._store_user_presets(presets)
        self._fill_presets()
