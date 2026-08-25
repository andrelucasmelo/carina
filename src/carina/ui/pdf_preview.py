"""Pré-visualização do roteiro de observação.

Mostra o PDF **exatamente como foi gerado** — o arquivo é escrito num
temporário e aberto aqui com o visualizador do Qt. Nada de uma segunda
renderização "de tela", que poderia divergir do que sai na impressora.

Daqui o usuário navega pelas páginas, ajusta o zoom e, se aprovar, manda
salvar de vez (o sinal ``exportRequested`` devolve o controle à janela do
planejamento, que já sabe exportar).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QMainWindow, QMessageBox


class PdfPreviewWindow(QMainWindow):
    """Janela de leitura do PDF gerado."""

    exportRequested = Signal()

    def __init__(self, path: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            self.tr("Pré-visualização — {t}").format(t=title)
        )
        self.resize(900, 1000)

        self._doc = QPdfDocument(self)
        status = self._doc.load(path)
        if status != QPdfDocument.Error.None_:
            QMessageBox.warning(
                self, "Carina",
                self.tr("Não foi possível abrir a pré-visualização."),
            )

        self.view = QPdfView(self)
        self.view.setDocument(self._doc)
        # rolagem contínua: o roteiro é lido de ponta a ponta, não página
        # a página como um livro
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.setCentralWidget(self.view)

        m_file = self.menuBar().addMenu(self.tr("&Arquivo"))
        act_save = QAction(self.tr("Salvar como PDF…"), self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.exportRequested.emit)
        m_file.addAction(act_save)
        m_file.addSeparator()
        act_close = QAction(self.tr("Fechar"), self)
        act_close.setShortcut("Ctrl+W")
        act_close.triggered.connect(self.close)
        m_file.addAction(act_close)

        m_view = self.menuBar().addMenu(self.tr("&Exibir"))
        for label, shortcut, mode in (
            (self.tr("Ajustar à largura"), "Ctrl+1",
             QPdfView.ZoomMode.FitToWidth),
            (self.tr("Página inteira"), "Ctrl+2",
             QPdfView.ZoomMode.FitInView),
            (self.tr("Tamanho real"), "Ctrl+0",
             QPdfView.ZoomMode.Custom),
        ):
            act = QAction(label, self)
            act.setShortcut(shortcut)
            act.triggered.connect(
                lambda _c=False, m=mode: self._set_zoom(m)
            )
            m_view.addAction(act)

        self.statusBar().showMessage(self.tr(
            "{n} páginas · role para percorrer o roteiro"
        ).format(n=self._doc.pageCount()))

    def _set_zoom(self, mode) -> None:
        self.view.setZoomMode(mode)
        if mode == QPdfView.ZoomMode.Custom:
            self.view.setZoomFactor(1.0)
