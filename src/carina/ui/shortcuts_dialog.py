"""Janela "Atalhos do teclado e do mouse" (Ajuda ▸ Atalhos).

A lista NÃO é escrita à mão: percorre a barra de menus e lê o atalho de
cada ação — assim nunca fica desatualizada quando um atalho muda. Os
gestos tratados diretamente pelo mapa (roda, duplo clique, setas…) não
são ações do Qt e entram por uma tabela fixa deste módulo, que
``docs/ATALHOS.md`` reaproveita.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

# (gesto, efeito) — o que o SkyWidget trata fora das QActions
MOUSE_AND_KEYS = [
    ("Arrastar com o botão esquerdo", "Move a vista (o ponto sob o cursor acompanha o mouse)"),
    ("Roda do mouse", "Zoom ancorado no ponto sob o cursor"),
    ("Clique", "Seleciona a estrela, planeta ou objeto mais próximo (ou o rótulo)"),
    ("Duplo clique", "Centraliza o ponto do céu sob o cursor"),
    ("Botão direito", "Menu de contexto do objeto ou do céu"),
    ("Pairar o mouse", "Tooltip com nome, magnitude e altitude"),
    ("Setas ← → ↑ ↓", "Desloca a vista"),
    ("+ / − (ou PgUp / PgDn)", "Aproxima / afasta"),
    ("Esc", "Limpa a seleção (durante um tour: sai do tour)"),
    ("→ / ←", "Durante um tour: próximo passo / passo anterior"),
    ("Espaço", "Durante um tour: avança sozinho (liga e desliga)"),
    ("F5", "Durante um tour: modo apresentação (tela cheia, texto grande)"),
]


def collect_menu_shortcuts(menubar) -> list[tuple[str, str, str]]:
    """(menu, ação, atalho) para toda ação com atalho na barra de menus,
    percorrendo submenus em profundidade. Uma ação que aparece em dois menus
    (os asterismos em Exibir e em Tours) entra uma vez só, onde aparece
    primeiro."""
    rows: list[tuple[str, str, str]] = []
    seen: set[int] = set()

    def clean(text: str) -> str:
        return text.replace("&", "").replace("…", "").strip()

    def walk(menu, path: str) -> None:
        for act in menu.actions():
            if act.isSeparator():
                continue
            if act.menu() is not None:
                walk(act.menu(), f"{path} ▸ {clean(act.text())}")
                continue
            keys = [k.toString(QKeySequence.SequenceFormat.PortableText) for k in act.shortcuts()
                    if not k.isEmpty()]
            if keys and id(act) not in seen:
                seen.add(id(act))
                rows.append((path, clean(act.text()), " ou ".join(keys)))

    for top in menubar.actions():
        if top.menu() is not None:
            walk(top.menu(), clean(top.text()))
    return rows


def shortcuts_markdown(rows: list[tuple[str, str, str]]) -> str:
    """Tabela Markdown dos atalhos (gera ``docs/ATALHOS.md``)."""
    out = ["| Onde | Ação | Atalho |", "|---|---|---|"]
    for menu, action, keys in rows:
        out.append(f"| {menu} | {action} | `{keys}` |")
    out += ["", "| Gesto | Efeito |", "|---|---|"]
    for gesture, effect in MOUSE_AND_KEYS:
        out.append(f"| {gesture} | {effect} |")
    return "\n".join(out) + "\n"


class ShortcutsDialog(QDialog):
    """Tabela pesquisável de todos os atalhos, com botão para copiar."""

    def __init__(self, menubar, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Atalhos do teclado e do mouse"))
        self.resize(720, 560)
        self.rows = collect_menu_shortcuts(menubar)

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Filtrar (ex.: zoom, grade, Ctrl)…"))
        self.search.textChanged.connect(self._fill)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Onde"), self.tr("Ação"), self.tr("Atalho")]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        note = QLabel(self.tr(
            "Os atalhos de uma letra (estrelas, grades, solo…) valem com a "
            "janela principal ativa. A lista é lida dos menus, por isso "
            "está sempre em dia."
        ))
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a93a5")
        layout.addWidget(note)

        row = QHBoxLayout()
        btn_copy = QPushButton(self.tr("Copiar como texto"))
        btn_copy.clicked.connect(self._copy)
        row.addWidget(btn_copy)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)
        self._fill()

    def _all_rows(self) -> list[tuple[str, str, str]]:
        return self.rows + [(self.tr("Mapa"), effect, gesture)
                            for gesture, effect in MOUSE_AND_KEYS]

    def _fill(self) -> None:
        needle = self.search.text().strip().lower()
        rows = [r for r in self._all_rows()
                if not needle or needle in " ".join(r).lower()]
        self.table.setRowCount(len(rows))
        for i, (menu, action, keys) in enumerate(rows):
            for j, text in enumerate((menu, action, keys)):
                item = QTableWidgetItem(text)
                if j == 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def _copy(self) -> None:
        QApplication.clipboard().setText(shortcuts_markdown(self.rows))


__all__ = ["ShortcutsDialog", "collect_menu_shortcuts", "shortcuts_markdown",
           "MOUSE_AND_KEYS", "QAction"]
