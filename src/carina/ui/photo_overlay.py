"""Minha foto no mapa (v0.19 T4).

O usuário abre uma foto do céu, clica em duas estrelas dela e diz quais
são (pelo nome, ou "a selecionada no mapa"). Com isso a foto é alinhada
(:mod:`core.photo_align`) e desenhada sobre o céu, no lugar e na escala
certos, com opacidade ajustável — útil para conferir o enquadramento de
uma astrofoto ou comparar o que a câmera pegou com o que o mapa mostra.
A configuração fica salva no ``carina.sqlite`` (perfil ``kind='photo'``)
e volta na próxima abertura.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDialog,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSlider, QVBoxLayout,
                               QWidget)

from ..core.photo_align import PhotoAlignment, solve

PHOTO_KIND = "photo"
MAX_TEX = 2048


@dataclass
class PhotoOverlay:
    """Foto alinhada pronta para o céu."""

    path: str
    rgb: np.ndarray            # textura reduzida (até 2048 px)
    width: int                 # tamanho original (pixels da transformação)
    height: int
    alignment: PhotoAlignment
    alpha: float = 0.8
    texture: int = 0           # identificador na GPU (preenchido pelo céu)


def load_rgb(path: str) -> tuple[np.ndarray, int, int] | None:
    from ..render.moontex import qimage_rgb

    img = QImage(path)
    if img.isNull():
        return None
    w, h = img.width(), img.height()
    if max(w, h) > MAX_TEX:
        img = img.scaled(MAX_TEX, MAX_TEX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    tmp = img.convertToFormat(QImage.Format_RGB888)
    tw, th = tmp.width(), tmp.height()
    buf = np.frombuffer(tmp.constBits(), np.uint8).reshape(th, tmp.bytesPerLine())
    return buf[:, : tw * 3].reshape(th, tw, 3).copy(), w, h


def overlay_from_profile(d: dict) -> PhotoOverlay | None:
    got = load_rgb(d.get("path", ""))
    if got is None:
        return None
    rgb, w, h = got
    return PhotoOverlay(d["path"], rgb, w, h, PhotoAlignment.from_dict(d["alignment"]),
                        float(d.get("alpha", 0.8)))


class _PhotoView(QWidget):
    """A foto, com clique para marcar as estrelas A e B."""

    clicked = Signal(float, float)       # pixel na imagem original

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 360)
        self.pix: QPixmap | None = None
        self.size_orig = (1, 1)
        self.marks: dict[str, tuple[float, float]] = {}

    def set_image(self, path: str) -> bool:
        pix = QPixmap(path)
        if pix.isNull():
            return False
        self.size_orig = (pix.width(), pix.height())
        self.pix = pix
        self.marks = {}
        self.update()
        return True

    def _geom(self):
        w, h = self.size_orig
        s = min(self.width() / w, self.height() / h)
        ox = (self.width() - w * s) / 2
        oy = (self.height() - h * s) / 2
        return s, ox, oy

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 12, 18))
        if self.pix is not None:
            s, ox, oy = self._geom()
            p.drawPixmap(int(ox), int(oy), int(self.size_orig[0] * s),
                         int(self.size_orig[1] * s), self.pix)
            p.setRenderHint(QPainter.Antialiasing, True)
            for label, (x, y) in self.marks.items():
                cx, cy = ox + x * s, oy + y * s
                p.setPen(QPen(QColor(255, 180, 60), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), 10, 10)
                p.drawText(QPointF(cx + 12, cy - 10), label)
        else:
            p.setPen(QColor(150, 155, 170))
            p.drawText(self.rect(), Qt.AlignCenter, "Abra uma foto do céu")
        p.end()

    def mousePressEvent(self, e) -> None:
        if self.pix is None:
            return
        s, ox, oy = self._geom()
        x = (e.position().x() - ox) / s
        y = (e.position().y() - oy) / s
        if 0 <= x <= self.size_orig[0] and 0 <= y <= self.size_orig[1]:
            self.clicked.emit(x, y)


class PhotoOverlayDialog(QDialog):
    """Arquivo ▸ Minha foto no mapa."""

    overlayChanged = Signal(object)      # PhotoOverlay ou None

    def __init__(self, stars, selected_star=lambda: None, parent=None,
                 userdata=None, current: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Minha foto no mapa"))
        self.stars = stars
        self.selected_star = selected_star
        self.userdata = userdata
        self.path = ""
        self.view = _PhotoView()
        self.view.clicked.connect(self._clicked)
        self.step = "A"

        names = sorted({n for n in stars.proper.values()})
        self.cb_a = self._star_combo(names)
        self.cb_b = self._star_combo(names)
        self.btn_sel_a = QPushButton(self.tr("Usar a estrela selecionada no mapa"))
        self.btn_sel_a.clicked.connect(lambda: self._use_selected(self.cb_a))
        self.btn_sel_b = QPushButton(self.tr("Usar a estrela selecionada no mapa"))
        self.btn_sel_b.clicked.connect(lambda: self._use_selected(self.cb_b))
        self.chk_mirror = QCheckBox(self.tr("Foto espelhada (diagonal ou imagem invertida)"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(10, 100)
        self.slider.setValue(80)
        self.slider.valueChanged.connect(self._alpha_changed)
        self.info = QLabel(self.tr("1. Abra a foto. 2. Clique na estrela A e escolha o nome dela. "
                                   "3. Faça o mesmo com a estrela B, longe da A."))
        self.info.setWordWrap(True)

        open_btn = QPushButton(self.tr("Abrir foto…"))
        open_btn.clicked.connect(self._open)
        self.btn_mark = QPushButton(self.tr("Marcar: estrela A"))
        self.btn_mark.setCheckable(True)
        self.btn_mark.clicked.connect(self._toggle_step)
        apply_btn = QPushButton(self.tr("Alinhar e mostrar no céu"))
        apply_btn.clicked.connect(self.apply)
        remove_btn = QPushButton(self.tr("Tirar do céu"))
        remove_btn.clicked.connect(self._remove)

        form = QFormLayout()
        ra = QHBoxLayout()
        ra.addWidget(self.cb_a, 1)
        ra.addWidget(self.btn_sel_a)
        rb = QHBoxLayout()
        rb.addWidget(self.cb_b, 1)
        rb.addWidget(self.btn_sel_b)
        form.addRow(self.tr("Estrela A:"), ra)
        form.addRow(self.tr("Estrela B:"), rb)
        form.addRow(self.chk_mirror)
        form.addRow(self.tr("Opacidade:"), self.slider)
        top = QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(self.btn_mark)
        top.addStretch(1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(remove_btn)
        bottom.addWidget(apply_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.info)
        lay.addLayout(form)
        lay.addLayout(bottom)
        self.resize(820, 720)
        self.overlay: PhotoOverlay | None = None
        if current:
            self._restore(current)

    def _star_combo(self, names) -> QComboBox:
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItems([""] + names)
        comp = QCompleter(names, cb)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        cb.setCompleter(comp)
        return cb

    def _use_selected(self, cb: QComboBox) -> None:
        idx = self.selected_star()
        if idx is None:
            QMessageBox.information(self, self.tr("Minha foto no mapa"),
                                    self.tr("Selecione uma estrela no mapa primeiro."))
            return
        name = self.stars.proper.get(idx) or self.stars.full_designation(idx)
        cb.setEditText(name)
        cb.setProperty("star_index", int(idx))

    def _star_vec(self, cb: QComboBox):
        idx = cb.property("star_index")
        text = cb.currentText().strip()
        if idx is not None and (self.stars.proper.get(int(idx)) == text
                                or self.stars.full_designation(int(idx)) == text):
            return np.asarray(self.stars.xyz[int(idx)], np.float64)
        for i, n in self.stars.proper.items():
            if n.lower() == text.lower():
                return np.asarray(self.stars.xyz[i], np.float64)
        return None

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Abrir foto do céu"), "",
                                              self.tr("Imagens (*.jpg *.jpeg *.png *.tif *.tiff)"))
        if path:
            self.load(path)

    def load(self, path: str) -> bool:
        if not self.view.set_image(path):
            QMessageBox.warning(self, self.tr("Minha foto no mapa"),
                                self.tr("Não foi possível abrir a imagem."))
            return False
        self.path = path
        self.step = "A"
        self.btn_mark.setChecked(True)
        self.btn_mark.setText(self.tr("Marcar: estrela A"))
        return True

    def _toggle_step(self) -> None:
        self.step = "B" if self.step == "A" else "A"
        self.btn_mark.setText(self.tr("Marcar: estrela {s}").format(s=self.step))

    def _clicked(self, x: float, y: float) -> None:
        self.view.marks[self.step] = (x, y)
        self.view.update()
        if self.step == "A":
            self.step = "B"
            self.btn_mark.setText(self.tr("Marcar: estrela B"))

    def mark(self, label: str, x: float, y: float) -> None:
        self.view.marks[label] = (x, y)

    def apply(self) -> PhotoOverlay | None:
        if not self.path or "A" not in self.view.marks or "B" not in self.view.marks:
            QMessageBox.information(self, self.tr("Minha foto no mapa"),
                                    self.tr("Marque as duas estrelas na foto."))
            return None
        va, vb = self._star_vec(self.cb_a), self._star_vec(self.cb_b)
        if va is None or vb is None:
            QMessageBox.information(self, self.tr("Minha foto no mapa"),
                                    self.tr("Escolha o nome das duas estrelas."))
            return None
        w, h = self.view.size_orig
        try:
            al = solve(self.view.marks["A"], self.view.marks["B"], va, vb,
                       mirror=self.chk_mirror.isChecked(), center=(w / 2, h / 2))
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Minha foto no mapa"), str(exc))
            return None
        got = load_rgb(self.path)
        if got is None:
            return None
        rgb, ow, oh = got
        self.overlay = PhotoOverlay(self.path, rgb, ow, oh, al, self.slider.value() / 100.0)
        self.info.setText(self.tr("Alinhada: {s:.1f}″ por pixel, 'para cima' da foto no ângulo "
                                  "de posição {r:.0f}°.").format(s=al.scale_arcsec,
                                                               r=al.rotation_deg))
        if self.userdata is not None:
            self.userdata.save_profile(PHOTO_KIND, "atual", {
                "path": self.path, "alignment": al.to_dict(), "alpha": self.overlay.alpha,
                "marks": self.view.marks, "a": self.cb_a.currentText(),
                "b": self.cb_b.currentText(), "mirror": self.chk_mirror.isChecked()})
        self.overlayChanged.emit(self.overlay)
        return self.overlay

    def _alpha_changed(self, v: int) -> None:
        if self.overlay is not None:
            self.overlay.alpha = v / 100.0
            self.overlayChanged.emit(self.overlay)

    def _remove(self) -> None:
        self.overlay = None
        if self.userdata is not None:
            self.userdata.delete_profile(PHOTO_KIND, "atual")
        self.overlayChanged.emit(None)

    def _restore(self, d: dict) -> None:
        if not d.get("path") or not self.view.set_image(d["path"]):
            return
        self.path = d["path"]
        self.view.marks = {k: tuple(v) for k, v in (d.get("marks") or {}).items()}
        self.cb_a.setEditText(d.get("a", ""))
        self.cb_b.setEditText(d.get("b", ""))
        self.chk_mirror.setChecked(bool(d.get("mirror")))
        self.slider.setValue(int(round(float(d.get("alpha", 0.8)) * 100)))
