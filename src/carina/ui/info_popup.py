"""Popup flutuante com a ficha do objeto (botão direito ▸ Informações).

Hospeda a mesma :class:`ObjectCard` do painel lateral. Pode ser fixado
acima das outras janelas ("Manter no topo") para acompanhar um alvo
enquanto se navega pelo céu; a posição se atualiza a cada segundo.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QPushButton, QVBoxLayout


class InfoPopup(QDialog):
    """Janela leve com a ficha unificada."""

    def __init__(self, card, title: str, parent=None) -> None:
        super().__init__(parent)
        self.card = card
        self.selection = card.selection
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(420, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(card, 1)
        row = QHBoxLayout()
        self.pin = QCheckBox(self.tr("Manter no topo"))
        self.pin.toggled.connect(self._set_pinned)
        btn_close = QPushButton(self.tr("Fechar"))
        btn_close.clicked.connect(self.close)
        row.addWidget(self.pin)
        row.addStretch(1)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def _set_pinned(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    def _refresh(self) -> None:
        try:
            self.card.refresh()
        except Exception:  # noqa: BLE001 — não derrubar o popup
            self._timer.stop()
