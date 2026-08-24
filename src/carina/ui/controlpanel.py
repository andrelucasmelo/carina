"""Painel lateral de controle: magnitude, camadas, tempo e ferramentas."""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
    QVBoxLayout, QWidget,
)

from ..core.twilight import format_night_summary, night_info

# Passos de tempo oferecidos (rótulo, segundos)
TIME_STEPS = [
    ("1 minuto", 60), ("5 minutos", 300), ("15 minutos", 900),
    ("30 minutos", 1800), ("1 hora", 3600), ("3 horas", 10800),
    ("6 horas", 21600), ("12 horas", 43200), ("1 dia", 86400),
    ("1 semana", 604800), ("1 mês (30 d)", 2592000), ("1 ano (365 d)", 31536000),
]

CATALOG_TOGGLES = [
    ("M", "Messier"), ("C", "Caldwell"), ("NGC", "NGC"), ("IC", "IC"),
    ("SH2", "Sharpless"), ("B", "Barnard"), ("Mel", "Melotte"),
]


class ControlPanel(QScrollArea):
    """Painel lateral; emite sinais para a janela principal agir."""

    magCapChanged = Signal(object)        # float | None
    layerToggled = Signal(str, bool)
    catalogToggled = Signal(str, bool)
    timeStep = Signal(float)              # segundos (sinal define o sentido)
    timeNow = Signal()
    mouseModeChanged = Signal(str)
    chartModeChanged = Signal(bool)
    trackRequested = Signal()

    def __init__(self, engine, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setWidgetResizable(True)
        self.setMinimumWidth(280)
        self.setMaximumWidth(360)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setSpacing(10)

        layout.addWidget(self._build_visibility())
        layout.addWidget(self._build_catalogs())
        layout.addWidget(self._build_time())
        layout.addWidget(self._build_night())
        layout.addWidget(self._build_tools())
        layout.addStretch(1)
        self.setWidget(root)

    # ------------------------------------------------------------------
    def _build_visibility(self) -> QGroupBox:
        box = QGroupBox(self.tr("Visibilidade"))
        grid = QGridLayout(box)

        self.mag_check = QCheckBox(self.tr("Limitar magnitude"))
        self.mag_slider = QSlider(Qt.Horizontal)
        self.mag_slider.setRange(-10, 130)   # -1,0 .. 13,0 (décimos)
        self.mag_slider.setValue(65)
        self.mag_label = QLabel("6,5")
        self.mag_label.setMinimumWidth(34)
        self.mag_slider.setEnabled(False)
        self.mag_check.toggled.connect(self._on_mag_changed)
        self.mag_slider.valueChanged.connect(self._on_mag_changed)

        grid.addWidget(self.mag_check, 0, 0, 1, 3)
        grid.addWidget(QLabel(self.tr("Mag. máx.")), 1, 0)
        grid.addWidget(self.mag_slider, 1, 1)
        grid.addWidget(self.mag_label, 1, 2)

        self.chk_planets = QCheckBox(self.tr("Sistema Solar (planetas, Sol, Lua)"))
        self.chk_planets.setChecked(True)
        self.chk_planets.toggled.connect(
            lambda on: self.layerToggled.emit("planets", on)
        )
        self.chk_dso = QCheckBox(self.tr("Objetos de céu profundo"))
        self.chk_dso.setChecked(True)
        self.chk_dso.toggled.connect(
            lambda on: self.layerToggled.emit("dso", on)
        )
        self.chk_stars = QCheckBox(self.tr("Estrelas"))
        self.chk_stars.setChecked(True)
        self.chk_stars.toggled.connect(
            lambda on: self.layerToggled.emit("stars", on)
        )
        grid.addWidget(self.chk_stars, 2, 0, 1, 3)
        grid.addWidget(self.chk_planets, 3, 0, 1, 3)
        grid.addWidget(self.chk_dso, 4, 0, 1, 3)
        return box

    def _on_mag_changed(self) -> None:
        enabled = self.mag_check.isChecked()
        self.mag_slider.setEnabled(enabled)
        value = self.mag_slider.value() / 10.0
        self.mag_label.setText(f"{value:.1f}".replace(".", ","))
        self.magCapChanged.emit(value if enabled else None)

    # ------------------------------------------------------------------
    def _build_catalogs(self) -> QGroupBox:
        box = QGroupBox(self.tr("Catálogos exibidos"))
        grid = QGridLayout(box)
        self.catalog_checks = {}
        for i, (key, label) in enumerate(CATALOG_TOGGLES):
            chk = QCheckBox(label)
            chk.setChecked(True)
            chk.toggled.connect(
                lambda on, k=key: self.catalogToggled.emit(k, on)
            )
            grid.addWidget(chk, i // 2, i % 2)
            self.catalog_checks[key] = chk
        return box

    # ------------------------------------------------------------------
    def _build_time(self) -> QGroupBox:
        box = QGroupBox(self.tr("Tempo"))
        layout = QVBoxLayout(box)

        self.step_combo = QComboBox()
        for label, secs in TIME_STEPS:
            self.step_combo.addItem(label, secs)
        self.step_combo.setCurrentIndex(4)  # 1 hora

        row = QHBoxLayout()
        btn_back = QPushButton("◀◀")
        btn_back.setToolTip(self.tr("Retroceder um passo"))
        btn_back.clicked.connect(
            lambda: self.timeStep.emit(-float(self.step_combo.currentData()))
        )
        btn_fwd = QPushButton("▶▶")
        btn_fwd.setToolTip(self.tr("Avançar um passo"))
        btn_fwd.clicked.connect(
            lambda: self.timeStep.emit(float(self.step_combo.currentData()))
        )
        btn_now = QPushButton(self.tr("Agora"))
        btn_now.clicked.connect(self.timeNow.emit)
        for w in (btn_back, btn_fwd, btn_now):
            row.addWidget(w)

        layout.addWidget(QLabel(self.tr("Passo:")))
        layout.addWidget(self.step_combo)
        layout.addLayout(row)
        return box

    # ------------------------------------------------------------------
    def _build_night(self) -> QGroupBox:
        box = QGroupBox(self.tr("Crepúsculos e noite"))
        layout = QVBoxLayout(box)
        self.night_label = QLabel(self.tr("calculando…"))
        self.night_label.setTextFormat(Qt.RichText)
        self.night_label.setWordWrap(True)
        layout.addWidget(self.night_label)
        btn = QPushButton(self.tr("Atualizar"))
        btn.clicked.connect(self.refresh_night)
        layout.addWidget(btn)
        return box

    def refresh_night(self) -> None:
        try:
            info = night_info(self.engine, self.engine.time.current_datetime())
        except Exception as exc:  # noqa: BLE001 — não derrubar a UI
            self.night_label.setText(f"<i>indisponível ({exc})</i>")
            return
        rows = "".join(
            f"<tr><td style='color:#8a93a5;padding-right:8px'><b>{k}</b></td>"
            f"<td style='white-space:nowrap'>{v}</td></tr>"
            for k, v in format_night_summary(info)
        )
        dates = info.label_date()
        title = ""
        if dates:
            d0, d1 = dates
            title = (
                f"<b>Noite de {d0.strftime('%d/%m')} → {d1.strftime('%d/%m')}</b><br>"
            )
        self.night_label.setText(
            f"{title}<table style='font-size:8pt'>{rows}</table>"
        )

    # ------------------------------------------------------------------
    def _build_tools(self) -> QGroupBox:
        box = QGroupBox(self.tr("Ferramentas"))
        layout = QVBoxLayout(box)

        self.btn_pan = QPushButton(self.tr("Mover (arrastar)"))
        self.btn_measure = QPushButton(self.tr("Medir distância angular"))
        self.btn_zoom = QPushButton(self.tr("Zoom por área"))
        group = QButtonGroup(self)
        for btn, mode in (
            (self.btn_pan, "pan"), (self.btn_measure, "measure"),
            (self.btn_zoom, "zoom_rect"),
        ):
            btn.setCheckable(True)
            group.addButton(btn)
            btn.clicked.connect(
                lambda _c=False, m=mode: self.mouseModeChanged.emit(m)
            )
            layout.addWidget(btn)
        self.btn_pan.setChecked(True)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        self.btn_chart = QPushButton(self.tr("Modo mapa para impressão"))
        self.btn_chart.setCheckable(True)
        self.btn_chart.toggled.connect(self.chartModeChanged.emit)
        layout.addWidget(self.btn_chart)

        btn_track = QPushButton(self.tr("Rastrear objeto na noite…"))
        btn_track.clicked.connect(self.trackRequested.emit)
        layout.addWidget(btn_track)
        return box
