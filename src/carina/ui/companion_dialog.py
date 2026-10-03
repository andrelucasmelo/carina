"""Planejar ▸ Companheiro no celular (v0.19 T5).

Liga o servidor local (:mod:`core.companion_server`) e mostra o QR code
com o endereço. O celular, na mesma rede Wi-Fi, abre o roteiro em vermelho
e marca "observado" — o registro chega aqui por um sinal Qt (o servidor
roda em outra thread) e vai para o diário.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)


class QrWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.matrix: list[list[int]] | None = None

    def set_text(self, text: str | None) -> None:
        from ..core.qr import encode

        self.matrix = encode(text, "M") if text else None
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        if self.matrix:
            n = len(self.matrix) + 8                      # zona de silêncio de 4 módulos
            s = min(self.width(), self.height()) / n
            ox = (self.width() - s * n) / 2 + 4 * s
            oy = (self.height() - s * n) / 2 + 4 * s
            for r, row in enumerate(self.matrix):
                for c, v in enumerate(row):
                    if v:
                        p.fillRect(QRectF(ox + c * s, oy + r * s, s + 0.5, s + 0.5),
                                   QColor(0, 0, 0))
        p.end()


class CompanionDialog(QDialog):
    observedReceived = Signal(str, str, str)      # kind, ident, nome (thread do servidor)

    def __init__(self, plan_provider, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Companheiro no celular"))
        self.plan_provider = plan_provider
        self.server = None
        # o roteiro é montado AQUI, na thread da interface (banco e motor
        # astronômico não podem ser usados de outra thread); o servidor só
        # entrega a cópia pronta
        self._plan_cache: dict = {"title": "Carina", "items": []}
        self.qr = QrWidget()
        self.url = QLabel()
        self.url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url.setAlignment(Qt.AlignCenter)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.btn = QPushButton()
        self.btn.clicked.connect(self.toggle)
        info = QLabel(self.tr(
            "Aponte a câmera do celular para o código. O celular precisa estar na mesma "
            "rede Wi-Fi deste computador. A página abre em vermelho, com o roteiro da noite "
            "e o botão \"observado\", que registra no seu diário.\n\nNa primeira vez o "
            "Windows pode perguntar se o Carina pode usar a rede: permita em redes "
            "privadas. Nada sai da sua rede, e o endereço tem um código de acesso novo a "
            "cada vez."))
        info.setWordWrap(True)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn)
        lay = QVBoxLayout(self)
        lay.addWidget(self.qr, 1)
        lay.addWidget(self.url)
        lay.addWidget(self.status)
        lay.addWidget(info)
        lay.addLayout(row)
        self.resize(460, 640)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(2000)
        self._update()

    def toggle(self) -> None:
        if self.server is not None and self.server.running:
            self.stop()
        else:
            self.start()

    def start(self, port: int | None = None) -> None:
        from ..core.companion_server import DEFAULT_PORT, CompanionServer

        try:
            self.refresh_plan()
            self.server = CompanionServer(lambda: self._plan_cache, self.observedReceived.emit,
                                          port=DEFAULT_PORT if port is None else port)
            self.server.start()
        except OSError as exc:
            self.server = None
            self.status.setText(self.tr("Não foi possível abrir o servidor: {e}").format(e=exc))
        self._update()

    def stop(self) -> None:
        if self.server is not None:
            self.server.stop()
        self.server = None
        self._update()

    def _update(self) -> None:
        on = self.server is not None and self.server.running
        self.btn.setText(self.tr("Desligar") if on else self.tr("Ligar o companheiro"))
        if on:
            url = self.server.url()
            self.qr.set_text(url)
            self.url.setText(f"<a href='{url}'>{url}</a>")
            self.url.setOpenExternalLinks(True)
            self.status.setText(self.tr("Servidor ligado na porta {p}. Aguardando o celular…")
                                .format(p=self.server.port))
        else:
            self.qr.set_text(None)
            self.url.setText("")
            self.status.setText(self.tr("Desligado."))

    def refresh_plan(self) -> None:
        try:
            self._plan_cache = self.plan_provider()
        except Exception as exc:
            self._plan_cache = {"title": "Carina", "items": [], "error": str(exc)}

    def _tick(self) -> None:
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self.server is not None and self._ticks % 10 == 0:
            self.refresh_plan()                      # a cada 20 s
        if self.server is not None and self.server.last_seen:
            self.status.setText(self.tr("Celular conectado ({ip}).").format(ip=self.server.last_seen))

    def closeEvent(self, e) -> None:
        self.stop()
        super().closeEvent(e)
