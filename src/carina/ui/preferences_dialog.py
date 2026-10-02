"""Preferências (v0.16 T5) — Arquivo ▸ Preferências…

Escala da fonte da interface (útil em telas grandes ou longe dos olhos,
no campo), tamanho dos rótulos do céu e o instrumento que a pontuação de
observabilidade considera.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox,
)

INSTRUMENTS = [("olho", "A olho nu"), ("binoculo", "Binóculo"),
               ("pequeno", "Pequeno telescópio"), ("medio", "Telescópio médio")]
_BASE_POINT_SIZE: float | None = None


def apply_font_scale(scale_pct: int, app: QApplication | None = None) -> None:
    """Fonte da aplicação inteira em ``scale_pct``% do tamanho do sistema."""
    global _BASE_POINT_SIZE
    app = app or QApplication.instance()
    if app is None:
        return
    font = app.font()
    if _BASE_POINT_SIZE is None:
        _BASE_POINT_SIZE = font.pointSizeF() if font.pointSizeF() > 0 else 9.0
    font.setPointSizeF(max(6.0, _BASE_POINT_SIZE * scale_pct / 100.0))
    app.setFont(font)


class PreferencesDialog(QDialog):
    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(self.tr("Preferências"))
        self.font_scale = QSpinBox()
        self.font_scale.setRange(80, 175)
        self.font_scale.setSingleStep(5)
        self.font_scale.setSuffix(" %")
        self.font_scale.setValue(settings.value("ui/font_scale", 100, int))
        self.label_scale = QSpinBox()
        self.label_scale.setRange(70, 200)
        self.label_scale.setSingleStep(10)
        self.label_scale.setSuffix(" %")
        self.label_scale.setValue(settings.value("sky/label_scale", 100, int))
        self.instrument = QComboBox()
        for key, label in INSTRUMENTS:
            self.instrument.addItem(self.tr(label), key)
        current = settings.value("card/instrument", "pequeno", str)
        self.instrument.setCurrentIndex(max(0, self.instrument.findData(current)))
        from ..i18n import DEFAULT_LANGUAGE, LANGUAGES, SETTING_KEY, language_label

        self.language = QComboBox()
        for code in LANGUAGES:
            self.language.addItem(language_label(code), code)
        self.language.setCurrentIndex(max(0, self.language.findData(
            settings.value(SETTING_KEY, DEFAULT_LANGUAGE, str))))
        form = QFormLayout(self)
        form.addRow(self.tr("Idioma"), self.language)
        form.addRow(self.tr("Fonte da interface"), self.font_scale)
        form.addRow(self.tr("Rótulos do céu"), self.label_scale)
        form.addRow(self.tr("Instrumento da pontuação"), self.instrument)
        hint = QLabel(self.tr("A pontuação de observabilidade e o \"Hoje à noite\" "
                              "avaliam se cada objeto vale a pena com este instrumento."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a93a5;")
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr("Aplicar"))
        buttons.button(QDialogButtonBox.Cancel).setText(self.tr("Cancelar"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self) -> None:
        self.settings.set_value("ui/font_scale", self.font_scale.value())
        self.settings.set_value("sky/label_scale", self.label_scale.value())
        self.settings.set_value("card/instrument", self.instrument.currentData())
