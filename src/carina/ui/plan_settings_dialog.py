"""Diálogo "Configurar planejamento".

Reúne o que antes estava espalhado em menus: o tempo reservado a cada
objeto, os extremos da janela de observação (início e fim) e a altitude
mínima aceitável. É acessível pelo menu Planejar e também pelo menu
Configurar de dentro de uma janela de planejamento, para ajustar e
recalcular sem sair da lista.

A janela padrão é a **noite astronômica** — o céu de fato escuro. Quem
esticar para o crepúsculo civil (ou fixar horários) verá que os trechos
claros só recebem objetos brilhantes: é uma decisão do planejador, não
uma limitação, e o diálogo explica isso ao usuário.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QLabel, QSpinBox, QTimeEdit, QVBoxLayout,
)

from ..core.observing import PlanSettings

# (valor interno, rótulo do início, rótulo do fim)
MODES = [
    ("astro", "Início da noite astronômica (padrão)",
     "Fim da noite astronômica (padrão)"),
    ("civil", "Crepúsculo civil (logo após o pôr do sol)",
     "Crepúsculo civil (pouco antes do nascer do sol)"),
    ("sunset", "Pôr do sol", "Nascer do sol"),
    ("custom", "Horário fixo…", "Horário fixo…"),
]


class PlanSettingsDialog(QDialog):
    """Edita um :class:`PlanSettings` (devolvido por :meth:`settings`)."""

    def __init__(self, settings: PlanSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Configurar planejamento"))
        self.setMinimumWidth(520)
        self._s = settings

        layout = QVBoxLayout(self)

        # --- ritmo ------------------------------------------------------
        box_pace = QGroupBox(self.tr("Ritmo"))
        f_pace = QFormLayout(box_pace)
        self.spin_minutes = QSpinBox()
        self.spin_minutes.setRange(3, 10)
        self.spin_minutes.setSuffix(self.tr(" minutos"))
        self.spin_minutes.setValue(settings.minutes_per_object)
        f_pace.addRow(self.tr("Tempo por objeto:"), self.spin_minutes)

        self.spin_alt = QDoubleSpinBox()
        self.spin_alt.setRange(5.0, 60.0)
        self.spin_alt.setDecimals(0)
        self.spin_alt.setSuffix("°")
        self.spin_alt.setValue(settings.min_altitude)
        self.spin_alt.setToolTip(self.tr(
            "Abaixo desta altura a atmosfera degrada demais a imagem."
        ))
        f_pace.addRow(self.tr("Altitude mínima:"), self.spin_alt)
        layout.addWidget(box_pace)

        # --- janela de observação --------------------------------------
        box_win = QGroupBox(self.tr("Janela de observação"))
        f_win = QFormLayout(box_win)

        self.combo_start = QComboBox()
        self.combo_end = QComboBox()
        for value, start_label, end_label in MODES:
            self.combo_start.addItem(self.tr(start_label), value)
            self.combo_end.addItem(self.tr(end_label), value)
        self._select(self.combo_start, settings.start_mode)
        self._select(self.combo_end, settings.end_mode)

        self.time_start = QTimeEdit(self._to_qtime(settings.custom_start))
        self.time_start.setDisplayFormat("HH:mm")
        self.time_end = QTimeEdit(self._to_qtime(settings.custom_end))
        self.time_end.setDisplayFormat("HH:mm")

        self.combo_start.currentIndexChanged.connect(self._update_enabled)
        self.combo_end.currentIndexChanged.connect(self._update_enabled)

        f_win.addRow(self.tr("Começar em:"), self.combo_start)
        f_win.addRow(self.tr("Hora fixa de início:"), self.time_start)
        f_win.addRow(self.tr("Terminar em:"), self.combo_end)
        f_win.addRow(self.tr("Hora fixa de fim:"), self.time_end)
        layout.addWidget(box_win)

        # --- crepúsculo -------------------------------------------------
        box_tw = QGroupBox(self.tr("Fora da noite astronômica"))
        f_tw = QFormLayout(box_tw)
        self.spin_tw = QDoubleSpinBox()
        self.spin_tw.setRange(0.0, 9.0)
        self.spin_tw.setDecimals(1)
        self.spin_tw.setSingleStep(0.5)
        self.spin_tw.setValue(settings.twilight_mag_limit)
        f_tw.addRow(self.tr("Só objetos até magnitude:"), self.spin_tw)
        hint = QLabel(self.tr(
            "Enquanto o céu ainda tem luz — entre o pôr do sol e a noite "
            "astronômica, e de novo ao amanhecer — apenas objetos bem "
            "brilhantes são agendados. Os demais ficam para o miolo escuro "
            "da noite, onde realmente aparecem."
        ))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a93a5")
        f_tw.addRow(hint)
        layout.addWidget(box_tw)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            | QDialogButtonBox.RestoreDefaults,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self._restore
        )
        layout.addWidget(buttons)
        self._update_enabled()

    # ------------------------------------------------------------------
    @staticmethod
    def _to_qtime(value: dt.time) -> QTime:
        return QTime(value.hour, value.minute)

    @staticmethod
    def _select(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(max(0, idx))

    def _update_enabled(self) -> None:
        """Os campos de hora só valem no modo "horário fixo"."""
        self.time_start.setEnabled(
            self.combo_start.currentData() == "custom"
        )
        self.time_end.setEnabled(self.combo_end.currentData() == "custom")

    def _restore(self) -> None:
        default = PlanSettings()
        self.spin_minutes.setValue(default.minutes_per_object)
        self.spin_alt.setValue(default.min_altitude)
        self._select(self.combo_start, default.start_mode)
        self._select(self.combo_end, default.end_mode)
        self.time_start.setTime(self._to_qtime(default.custom_start))
        self.time_end.setTime(self._to_qtime(default.custom_end))
        self.spin_tw.setValue(default.twilight_mag_limit)
        self._update_enabled()

    def settings(self) -> PlanSettings:
        """Configuração escolhida (já dentro das faixas válidas)."""
        t0 = self.time_start.time()
        t1 = self.time_end.time()
        return PlanSettings(
            minutes_per_object=self.spin_minutes.value(),
            start_mode=self.combo_start.currentData(),
            end_mode=self.combo_end.currentData(),
            custom_start=dt.time(t0.hour(), t0.minute()),
            custom_end=dt.time(t1.hour(), t1.minute()),
            min_altitude=self.spin_alt.value(),
            twilight_mag_limit=self.spin_tw.value(),
        ).clamp()


# ---------------------------------------------------------------------------
# Persistência (QSettings)
# ---------------------------------------------------------------------------

def load_settings(store) -> PlanSettings:
    """Lê a configuração salva; valores ausentes caem no padrão."""
    d = PlanSettings()
    return PlanSettings(
        minutes_per_object=int(store.value(
            "plan/minutes", d.minutes_per_object, int)),
        start_mode=str(store.value("plan/start_mode", d.start_mode, str)),
        end_mode=str(store.value("plan/end_mode", d.end_mode, str)),
        custom_start=_parse_time(
            store.value("plan/custom_start", "19:00", str), d.custom_start),
        custom_end=_parse_time(
            store.value("plan/custom_end", "05:00", str), d.custom_end),
        min_altitude=float(store.value("plan/min_alt", d.min_altitude, float)),
        twilight_mag_limit=float(store.value(
            "plan/twilight_mag", d.twilight_mag_limit, float)),
    ).clamp()


def save_settings(store, s: PlanSettings) -> None:
    """Persiste a configuração do planejamento."""
    store.set_value("plan/minutes", s.minutes_per_object)
    store.set_value("plan/start_mode", s.start_mode)
    store.set_value("plan/end_mode", s.end_mode)
    store.set_value("plan/custom_start", s.custom_start.strftime("%H:%M"))
    store.set_value("plan/custom_end", s.custom_end.strftime("%H:%M"))
    store.set_value("plan/min_alt", s.min_altitude)
    store.set_value("plan/twilight_mag", s.twilight_mag_limit)


def _parse_time(raw, default: dt.time) -> dt.time:
    try:
        hour, minute = (int(p) for p in str(raw).split(":"))
        return dt.time(hour, minute)
    except (ValueError, TypeError):
        return default
