"""Ajuda interna (v0.16 T6) — F1.

Lê a documentação do usuário (``docs/*.md``, embarcada no build) num
visualizador próprio: índice à esquerda, página à direita, busca na
página, links internos entre os documentos e imagens. O "O que há de
novo" é o ``docs/NOVIDADES.md``.

O Markdown é convertido pelo próprio Qt (``QTextDocument.setMarkdown``,
GitHub Flavored: títulos, listas, tabelas, código, links). As imagens que
os documentos escrevem em HTML (``<img src=…>`` para centralizar no
GitHub) viram a sintaxe de imagem do Markdown antes da conversão.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from ..config import docs_dir

# (arquivo, título no índice) — a ordem é a de leitura sugerida
INDEX = [
    ("README.md", "Início"),
    ("NOVIDADES.md", "O que há de novo"),
    ("PRIMEIROS_PASSOS.md", "Primeiros passos"),
    ("TOURS.md", "Tours guiados"),
    ("INTERFACE.md", "Interface"),
    ("ATALHOS.md", "Atalhos"),
    ("FUNCIONALIDADES.md", "Funcionalidades"),
    ("PLANEJAMENTO.md", "Planejamento"),
    ("PLANETAS.md", "Os planetas"),
    ("LUA.md", "A Lua"),
    ("CALENDARIO.md", "Calendário do céu"),
    ("DIARIO.md", "Diário e listas"),
    ("PROGRAMAS.md", "Programas de observação"),
    ("ASTROFOTOGRAFIA.md", "Astrofotografia"),
    ("IMPRESSAO.md", "Impressão e cartas"),
    ("CATALOGOS.md", "Catálogos e dados"),
    ("SOLUCAO_DE_PROBLEMAS.md", "Solução de problemas"),
    ("GLOSSARIO.md", "Glossário"),
    ("INSTALACAO.md", "Instalação"),
]

_IMG = re.compile(r"<img\s+[^>]*>", re.I)
_ATTR = re.compile(r'(\w+)="([^"]*)"')
MAX_IMAGE_W = 760
_TAG = re.compile(r"</?(div|br|em|p)(\s[^>]*)?/?>", re.I)


def preprocess(markdown: str) -> str:
    """Trocas que o leitor de Markdown do Qt precisa (HTML embutido)."""
    def img(m):
        attrs = dict(_ATTR.findall(m.group(0)))
        src = attrs.get("src", "")
        # o leitor do Qt descarta imagens sem texto alternativo
        alt = attrs.get("alt") or "imagem"
        return f"\n\n![{alt}]({src})\n\n" if src else ""

    text = _IMG.sub(img, markdown)
    text = re.sub(r"<br\s*/?>", "  \n", text, flags=re.I)
    text = re.sub(r"<em>(.*?)</em>", r"*\1*", text, flags=re.I | re.S)
    return _TAG.sub("", text)


def markdown_to_html(markdown: str, base: Path | None = None) -> str:
    """Markdown (GFM) → HTML, com as imagens resolvidas a partir de ``base``."""
    doc = QTextDocument()
    if base is not None:
        doc.setBaseUrl(QUrl.fromLocalFile(str(base) + "/"))
    doc.setMarkdown(preprocess(markdown), QTextDocument.MarkdownDialectGitHub)
    html = doc.toHtml()
    if base is None:
        return html

    def limit(m):
        from PySide6.QtGui import QImageReader

        src = m.group(1)
        size = QImageReader(str(base / src)).size()
        if size.isValid() and size.width() > MAX_IMAGE_W:
            return f'<img width="{MAX_IMAGE_W}" src="{src}"'
        return m.group(0)

    return re.sub(r'<img src="([^"]+)"', limit, html)


class HelpViewer(QDialog):
    """Janela da Ajuda: índice, página e busca."""

    def __init__(self, page: str = "README.md", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Ajuda do Carina"))
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1100, 760)
        self.base = docs_dir()
        self.current = ""

        self.index = QListWidget()
        for name, title in INDEX:
            if (self.base / name).exists():
                item = QListWidgetItem(self.tr(title))
                item.setData(Qt.UserRole, name)
                self.index.addItem(item)
        self.index.setMaximumWidth(230)
        self.index.currentItemChanged.connect(
            lambda cur, _prev: cur is not None and self.open_page(cur.data(Qt.UserRole)))

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setSearchPaths([str(self.base)])
        self.browser.anchorClicked.connect(self._link)
        self.find = QLineEdit()
        self.find.setPlaceholderText(self.tr("Procurar nesta página…"))
        self.find.returnPressed.connect(self._find_next)
        btn_back = QPushButton(self.tr("◀ Voltar"))
        btn_back.clicked.connect(self.browser.backward)
        btn_web = QPushButton(self.tr("Abrir no navegador"))
        btn_web.clicked.connect(self._open_external)
        top = QHBoxLayout()
        top.addWidget(btn_back)
        top.addWidget(self.find, 1)
        top.addWidget(btn_web)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(top)
        rl.addWidget(self.browser, 1)
        split = QSplitter()
        split.addWidget(self.index)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        self.open_page(page)

    def open_page(self, name: str, anchor: str = "") -> bool:
        path = self.base / name
        if not path.exists():
            self.browser.setHtml(self.tr(
                "<h2>Documentação indisponível</h2><p>A pasta <code>docs/</code> não "
                "foi encontrada nesta instalação.</p>"))
            return False
        if name != self.current:
            html = markdown_to_html(path.read_text(encoding="utf-8"), self.base)
            self.browser.document().setBaseUrl(QUrl.fromLocalFile(str(self.base) + "/"))
            self.browser.setHtml(html)
            self.current = name
            for i in range(self.index.count()):
                item = self.index.item(i)
                if item.data(Qt.UserRole) == name and self.index.currentItem() is not item:
                    self.index.blockSignals(True)
                    self.index.setCurrentItem(item)
                    self.index.blockSignals(False)
        if anchor:
            self.browser.scrollToAnchor(anchor)
        else:
            self.browser.verticalScrollBar().setValue(0)
        return True

    def _link(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return
        target = url.toString()
        name, _, anchor = target.partition("#")
        name = Path(name).name if name else self.current
        if name.lower().endswith(".md"):
            self.open_page(name, anchor)
        elif anchor:
            self.browser.scrollToAnchor(anchor)

    def _find_next(self) -> None:
        text = self.find.text().strip()
        if text and not self.browser.find(text):
            cursor = self.browser.textCursor()
            cursor.movePosition(cursor.Start)
            self.browser.setTextCursor(cursor)
            self.browser.find(text)

    def _open_external(self) -> None:
        path = self.base / (self.current or "README.md")
        url = (QUrl.fromLocalFile(str(path)) if path.exists()
               else QUrl("https://github.com/andrelucasmelo/carina/tree/main/docs"))
        QDesktopServices.openUrl(url)
