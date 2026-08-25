"""Simulador de campo de visão de equipamentos (item 7).

Duas abas: "Campo" monta o setup ativo (telescópio + acessório + câmera ou
ocular) e mostra os números; "Equipamentos" faz o CRUD do banco pessoal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QSlider, QSpinBox, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..catalogs.equipment import (
    Accessory, Camera, EquipmentStore, Eyepiece, Mount, Telescope,
    compute_camera_fov, compute_eyepiece_fov,
)

SECTION_LABELS = [
    ("telescopes", "Telescópios e lentes"),
    ("cameras", "Câmeras"),
    ("eyepieces", "Oculares"),
    ("accessories", "Acessórios"),
    ("mounts", "Montagens"),
]

# campos editáveis por seção: (atributo, rótulo, tipo, mínimo, máximo, casas)
SECTION_FIELDS = {
    "telescopes": [
        ("name", "Nome", "text", 0, 0, 0),
        ("aperture_mm", "Abertura (mm)", "float", 1.0, 5000.0, 1),
        ("focal_mm", "Distância focal (mm)", "float", 1.0, 20000.0, 0),
        ("kind", "Tipo", "choice:telescopio,lente", 0, 0, 0),
    ],
    "cameras": [
        ("name", "Nome", "text", 0, 0, 0),
        ("width_mm", "Sensor — largura (mm)", "float", 0.1, 200.0, 2),
        ("height_mm", "Sensor — altura (mm)", "float", 0.1, 200.0, 2),
        ("pixel_um", "Tamanho do pixel (µm)", "float", 0.0, 50.0, 2),
        ("width_px", "Resolução — largura (px)", "int", 0, 60000, 0),
        ("height_px", "Resolução — altura (px)", "int", 0, 60000, 0),
    ],
    "eyepieces": [
        ("name", "Nome", "text", 0, 0, 0),
        ("focal_mm", "Distância focal (mm)", "float", 1.0, 100.0, 1),
        ("afov_deg", "Campo aparente (°)", "float", 20.0, 120.0, 0),
    ],
    "accessories": [
        ("name", "Nome", "text", 0, 0, 0),
        ("factor", "Fator (2,0 = barlow 2×)", "float", 0.1, 10.0, 2),
    ],
    "mounts": [
        ("name", "Nome", "text", 0, 0, 0),
        ("kind", "Tipo", "choice:equatorial,altazimute", 0, 0, 0),
        ("payload_kg", "Capacidade (kg)", "float", 0.0, 200.0, 1),
    ],
}
SECTION_CLASSES = {
    "telescopes": Telescope, "cameras": Camera, "eyepieces": Eyepiece,
    "accessories": Accessory, "mounts": Mount,
}


class ItemDialog(QDialog):
    """Formulário genérico de inclusão/edição de um equipamento."""

    def __init__(self, section: str, item=None, parent=None) -> None:
        super().__init__(parent)
        self.section = section
        self.setWindowTitle(
            self.tr("Editar equipamento") if item else self.tr("Novo equipamento")
        )
        form = QFormLayout(self)
        self.widgets = {}
        for attr, label, kind, lo, hi, dec in SECTION_FIELDS[section]:
            value = getattr(item, attr, None) if item else None
            if kind == "text":
                w = QLineEdit(str(value or ""))
            elif kind.startswith("choice:"):
                w = QComboBox()
                for opt in kind.split(":", 1)[1].split(","):
                    w.addItem(opt)
                if value:
                    idx = w.findText(str(value))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
            elif kind == "int":
                w = QSpinBox()
                w.setRange(int(lo), int(hi))
                w.setValue(int(value or 0))
            else:
                w = QDoubleSpinBox()
                w.setRange(lo, hi)
                w.setDecimals(dec)
                w.setValue(float(value or lo))
            form.addRow(label + ":", w)
            self.widgets[attr] = (w, kind)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _validate(self) -> None:
        w, _ = self.widgets["name"]
        if not w.text().strip():
            QMessageBox.warning(self, "Carina", self.tr("Informe o nome."))
            return
        self.accept()

    def build(self):
        kwargs = {}
        for attr, (w, kind) in self.widgets.items():
            if kind == "text":
                kwargs[attr] = w.text().strip()
            elif kind.startswith("choice:"):
                kwargs[attr] = w.currentText()
            elif kind == "int":
                kwargs[attr] = int(w.value())
            else:
                kwargs[attr] = float(w.value())
        return SECTION_CLASSES[self.section](**kwargs)


class FovDialog(QDialog):
    """Simulador de campo de visão: combina telescópio + câmera/ocular +
    acessório, mostra a ficha técnica (ampliação, escala de placa,
    amostragem) e projeta o retângulo/círculo resultante sobre o céu.
    A segunda aba gerencia o acervo de equipamentos do usuário."""

    fovChanged = Signal(list, float, bool)   # shapes, ângulo, seguir seleção

    def __init__(self, store: EquipmentStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(self.tr("Campo de visão dos equipamentos"))
        self.resize(700, 560)

        tabs = QTabWidget()
        tabs.addTab(self._build_fov_tab(), self.tr("Campo"))
        tabs.addTab(self._build_manage_tab(), self.tr("Equipamentos"))

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        row = QHBoxLayout()
        btn_clear = QPushButton(self.tr("Remover campos do céu"))
        btn_clear.clicked.connect(self._clear)
        btn_close = QPushButton(self.tr("Fechar"))
        btn_close.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(btn_clear)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self._refresh_combos()
        self._recompute()

    # ------------------------------------------------------------------
    def _build_fov_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        setup = QGroupBox(self.tr("Setup"))
        form = QFormLayout(setup)
        self.cb_scope = QComboBox()
        self.cb_accessory = QComboBox()
        self.cb_camera = QComboBox()
        self.cb_eyepiece = QComboBox()
        self.cb_mount = QComboBox()
        for cb in (self.cb_scope, self.cb_accessory, self.cb_camera,
                   self.cb_eyepiece, self.cb_mount):
            cb.currentIndexChanged.connect(self._recompute)
        self.chk_camera = QCheckBox(self.tr("Câmera"))
        self.chk_camera.setChecked(True)
        self.chk_eyepiece = QCheckBox(self.tr("Ocular"))
        self.chk_camera.toggled.connect(self._recompute)
        self.chk_eyepiece.toggled.connect(self._recompute)

        form.addRow(self.tr("Telescópio/lente:"), self.cb_scope)
        form.addRow(self.tr("Acessório:"), self.cb_accessory)
        form.addRow(self.chk_camera, self.cb_camera)
        form.addRow(self.chk_eyepiece, self.cb_eyepiece)
        form.addRow(self.tr("Montagem:"), self.cb_mount)
        layout.addWidget(setup)

        opts = QGroupBox(self.tr("Exibição"))
        oform = QFormLayout(opts)
        self.slider_angle = QSlider(Qt.Horizontal)
        self.slider_angle.setRange(0, 359)
        self.slider_angle.valueChanged.connect(self._recompute)
        self.lbl_angle = QLabel("0°")
        row = QHBoxLayout()
        row.addWidget(self.slider_angle)
        row.addWidget(self.lbl_angle)
        holder = QWidget()
        holder.setLayout(row)
        oform.addRow(self.tr("Rotação do campo (rotacionador):"), holder)
        self.chk_follow = QCheckBox(
            self.tr("Centralizar no objeto selecionado")
        )
        self.chk_follow.setChecked(True)
        self.chk_follow.toggled.connect(self._recompute)
        oform.addRow(self.chk_follow)
        layout.addWidget(opts)

        self.result_label = QLabel()
        self.result_label.setTextFormat(Qt.RichText)
        self.result_label.setWordWrap(True)
        self.result_label.setAlignment(Qt.AlignTop)
        layout.addWidget(self.result_label, 1)
        return page

    def _build_manage_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.cb_section = QComboBox()
        for key, label in SECTION_LABELS:
            self.cb_section.addItem(label, key)
        self.cb_section.currentIndexChanged.connect(self._refresh_list)
        layout.addWidget(self.cb_section)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._edit_item())
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        for text, slot in (
            (self.tr("Novo…"), self._new_item),
            (self.tr("Editar…"), self._edit_item),
            (self.tr("Remover"), self._remove_item),
            (self.tr("Restaurar padrão…"), self._restore),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        layout.addLayout(row)
        self._refresh_list()
        return page

    # ------------------------------------------------------------------
    def _refresh_combos(self) -> None:
        pairs = [
            (self.cb_scope, "telescopes"), (self.cb_accessory, "accessories"),
            (self.cb_camera, "cameras"), (self.cb_eyepiece, "eyepieces"),
            (self.cb_mount, "mounts"),
        ]
        for cb, section in pairs:
            current = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            for item in self.store.items(section):
                cb.addItem(item.name)
            idx = cb.findText(current)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            cb.blockSignals(False)

    def _refresh_list(self) -> None:
        section = self.cb_section.currentData()
        self.list.clear()
        for item in self.store.items(section):
            if section == "telescopes":
                text = (f"{item.name} — {item.aperture_mm:.0f} mm "
                        f"f/{item.ratio:.1f}")
            elif section == "cameras":
                text = f"{item.name} — {item.width_mm}×{item.height_mm} mm"
            elif section == "eyepieces":
                text = f"{item.name} — {item.focal_mm} mm, {item.afov_deg}°"
            elif section == "accessories":
                text = f"{item.name} — ×{item.factor}"
            else:
                text = f"{item.name} — {item.kind}, {item.payload_kg} kg"
            self.list.addItem(text)

    # ------------------------------------------------------------------
    def _new_item(self) -> None:
        section = self.cb_section.currentData()
        dlg = ItemDialog(section, None, self)
        if dlg.exec():
            self.store.add(section, dlg.build())
            self._refresh_list()
            self._refresh_combos()
            self._recompute()

    def _edit_item(self) -> None:
        section = self.cb_section.currentData()
        row = self.list.currentRow()
        if row < 0:
            return
        dlg = ItemDialog(section, self.store.items(section)[row], self)
        if dlg.exec():
            self.store.replace(section, row, dlg.build())
            self._refresh_list()
            self._refresh_combos()
            self._recompute()

    def _remove_item(self) -> None:
        section = self.cb_section.currentData()
        row = self.list.currentRow()
        if row < 0:
            return
        name = self.store.items(section)[row].name
        if QMessageBox.question(
            self, "Carina",
            self.tr("Remover \"{n}\"?").format(n=name),
        ) == QMessageBox.Yes:
            self.store.remove(section, row)
            self._refresh_list()
            self._refresh_combos()
            self._recompute()

    def _restore(self) -> None:
        if QMessageBox.question(
            self, "Carina",
            self.tr("Restaurar a lista padrão de equipamentos? "
                    "Os itens que você cadastrou serão perdidos."),
        ) == QMessageBox.Yes:
            self.store.restore_defaults()
            self._refresh_list()
            self._refresh_combos()
            self._recompute()

    # ------------------------------------------------------------------
    def _recompute(self) -> None:
        self.lbl_angle.setText(f"{self.slider_angle.value()}°")
        scope = self.store.find("telescopes", self.cb_scope.currentText())
        accessory = self.store.find("accessories", self.cb_accessory.currentText())
        shapes = []
        blocks = []
        if scope is not None:
            if self.chk_camera.isChecked():
                cam = self.store.find("cameras", self.cb_camera.currentText())
                if cam is not None:
                    shapes.append(compute_camera_fov(scope, cam, accessory))
            if self.chk_eyepiece.isChecked():
                eye = self.store.find("eyepieces", self.cb_eyepiece.currentText())
                if eye is not None:
                    shapes.append(compute_eyepiece_fov(scope, eye, accessory))
        for shape in shapes:
            rows = "".join(
                f"<tr><td style='color:#8a93a5;padding-right:8px'>{k}</td>"
                f"<td>{v}</td></tr>"
                for k, v in shape.details
            )
            blocks.append(
                f"<p><b>{shape.label}</b>"
                f"<table style='font-size:9pt'>{rows}</table></p>"
            )
        mount = self.store.find("mounts", self.cb_mount.currentText())
        if mount is not None:
            blocks.append(
                f"<p style='color:#8a93a5;font-size:8pt'>Montagem: "
                f"{mount.name} ({mount.kind}, até {mount.payload_kg:.0f} kg)"
                + ("" if mount.kind == "equatorial" else
                   " — altazimutal: há rotação de campo em longas exposições")
                + "</p>"
            )
        self.result_label.setText(
            "".join(blocks) or self.tr("<i>Escolha um telescópio e uma "
                                       "câmera ou ocular.</i>")
        )
        self.fovChanged.emit(
            shapes, float(self.slider_angle.value()),
            self.chk_follow.isChecked(),
        )

    def _clear(self) -> None:
        self.chk_camera.setChecked(False)
        self.chk_eyepiece.setChecked(False)
        self.fovChanged.emit([], 0.0, True)
