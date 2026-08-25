"""Popup de informações do objeto (item 7): alternativa ao painel lateral."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
)


class InfoPopup(QDialog):
    """Janela leve com a ficha do objeto e a imagem, atualizada a cada segundo."""

    detailsRequested = Signal(object)
    trackRequested = Signal(object)

    def __init__(self, selection, title: str, html: str, image_path,
                 refresh_cb=None, parent=None) -> None:
        super().__init__(parent)
        self.selection = selection
        self.refresh_cb = refresh_cb
        self.setWindowTitle(title)
        self.setMinimumWidth(430)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        layout = QVBoxLayout(self)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        if image_path is not None:
            pix = QPixmap(str(image_path))
            if not pix.isNull():
                self.image_label.setPixmap(
                    pix.scaled(400, 400, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
                )
                layout.addWidget(self.image_label)

        self.label = QLabel(html)
        self.label.setTextFormat(Qt.RichText)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.label)
        scroll.setMinimumHeight(230)
        layout.addWidget(scroll, 1)

        row = QHBoxLayout()
        btn_details = QPushButton(self.tr("Detalhes e gráfico anual…"))
        btn_details.clicked.connect(
            lambda: self.detailsRequested.emit(self.selection)
        )
        btn_track = QPushButton(self.tr("Rastrear na noite…"))
        btn_track.clicked.connect(
            lambda: self.trackRequested.emit(self.selection)
        )
        btn_close = QPushButton(self.tr("Fechar"))
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_details)
        row.addWidget(btn_track)
        row.addStretch(1)
        row.addWidget(btn_close)
        layout.addLayout(row)

        if refresh_cb is not None:
            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._refresh)
            self._timer.start()

    def _refresh(self) -> None:
        try:
            self.label.setText(self.refresh_cb(self.selection))
        except Exception:  # noqa: BLE001 — não derrubar o popup
            self._timer.stop()
