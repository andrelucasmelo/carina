"""Modo noturno da interface (v0.16 T2).

Pinta toda a aplicação — menus, diálogos, painéis, fichas — em vermelho
escuro sobre preto, junto com o céu no tema ``red``. O olho adaptado ao
escuro é sensível sobretudo ao verde e ao azul; uma tela vermelha e fraca
não desfaz a adaptação. Nenhuma cor da paleta tem verde ou azul acima de
um limiar baixo (:data:`MAX_GB`).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QGraphicsEffect, QMainWindow, QMenu, QWidget,
)

MAX_GB = 24          # teto de verde/azul em qualquer cor da paleta noturna

_BG = QColor(8, 0, 0)
_BASE = QColor(16, 2, 2)
_ALT = QColor(26, 4, 4)
_TEXT = QColor(215, 22, 14)
_MUTED = QColor(135, 14, 9)
_HILITE = QColor(90, 10, 8)
_BUTTON = QColor(30, 5, 4)

NIGHT_STYLESHEET = """
QWidget { color: rgb(215, 22, 14); }
QToolTip { color: rgb(215, 22, 14); background: rgb(20, 2, 2);
           border: 1px solid rgb(90, 10, 8); }
QMenu::item:selected, QMenuBar::item:selected { background: rgb(90, 10, 8); }
QHeaderView::section { background: rgb(26, 4, 4); color: rgb(215, 22, 14);
                       border: 1px solid rgb(50, 6, 5); }
QPushButton, QToolButton { border: 1px solid rgb(70, 8, 6); }
"""


def night_palette() -> QPalette:
    """Paleta Qt toda em vermelho escuro (todas as funções e grupos)."""
    pal = QPalette()
    roles = {
        QPalette.Window: _BG, QPalette.WindowText: _TEXT, QPalette.Base: _BASE,
        QPalette.AlternateBase: _ALT, QPalette.ToolTipBase: _BASE,
        QPalette.ToolTipText: _TEXT, QPalette.PlaceholderText: _MUTED,
        QPalette.Text: _TEXT, QPalette.Button: _BUTTON, QPalette.ButtonText: _TEXT,
        QPalette.BrightText: QColor(255, 24, 16), QPalette.Highlight: _HILITE,
        QPalette.HighlightedText: QColor(245, 22, 15), QPalette.Link: QColor(235, 20, 12),
        QPalette.LinkVisited: QColor(170, 16, 10), QPalette.Light: _ALT,
        QPalette.Midlight: _BUTTON, QPalette.Mid: QColor(40, 6, 5),
        QPalette.Dark: QColor(4, 0, 0), QPalette.Shadow: QColor(0, 0, 0),
    }
    # papéis novos do Qt (Accent no 6.6+…) herdariam a cor do sistema
    for role in QPalette.ColorRole:
        if role.name not in ("NColorRoles", "NoRole") and role not in roles:
            roles[role] = _HILITE
    for group in (QPalette.Active, QPalette.Inactive):
        for role, color in roles.items():
            pal.setColor(group, role, color)
    for role, color in roles.items():
        dim = QColor(max(color.red() // 2, 0), 0, 0)
        pal.setColor(QPalette.Disabled, role, dim)
    return pal


def palette_max_gb(pal: QPalette) -> int:
    """Maior componente verde/azul da paleta (para testes e conferência)."""
    worst = 0
    roles = [r for r in QPalette.ColorRole if r.name not in ("NColorRoles", "NoRole")]
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role in roles:
            c = pal.color(group, role)
            worst = max(worst, c.green(), c.blue())
    return worst


class RedOnlyEffect(QGraphicsEffect):
    """Efeito que mantém só o canal vermelho do widget (como o céu ``red``).

    Os selos, gráficos e ícones desenhados com cores próprias passam a ter
    apenas o vermelho que já tinham — o fundo escuro continua escuro.
    """

    def draw(self, painter) -> None:
        pix = self.sourcePixmap(Qt.LogicalCoordinates)
        if pix.isNull():
            return
        img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
        w, h = img.width(), img.height()
        buf = np.frombuffer(img.bits(), dtype=np.uint8, count=img.sizeInBytes())
        arr = buf.reshape(h, img.bytesPerLine() // 4, 4)
        arr[:, :w, 0] = 0               # azul  (ARGB32 little-endian: B, G, R, A)
        arr[:, :w, 1] = 0               # verde
        img.setDevicePixelRatio(pix.devicePixelRatio())
        painter.drawImage(self.sourceBoundingRect(Qt.LogicalCoordinates).topLeft(), img)


class NightMode(QObject):
    """Liga e desliga o modo noturno da aplicação, guardando o estado.

    Além da paleta, aplica um :class:`RedOnlyEffect` aos
    painéis e às janelas abertas (e às que abrirem depois): gráficos e
    selos desenhados com cores próprias — o selo verde da nota, o gráfico
    da noite, os ícones da barra lateral, as cartas — também ficam
    vermelhos. O céu OpenGL não recebe o efeito: ele tem o tema ``red``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.active = False
        self._palette = None
        self._style = ""
        self._tinted: list = []

    def apply(self, on: bool, app: QApplication | None = None) -> None:
        app = app or QApplication.instance()
        if app is None or on == self.active:
            return
        if on:
            self._palette = QPalette(app.palette())
            self._style = app.styleSheet()
            app.setPalette(night_palette())
            app.setStyleSheet(self._style + NIGHT_STYLESHEET)
            app.installEventFilter(self)
            for w in app.topLevelWidgets():
                if w.isVisible():
                    self.tint_window(w)
        else:
            app.removeEventFilter(self)
            for w in self._tinted:
                try:
                    w.setGraphicsEffect(None)
                except RuntimeError:
                    pass                    # widget já destruído
            self._tinted.clear()
            if self._palette is not None:
                app.setPalette(self._palette)
            app.setStyleSheet(self._style)
        self.active = on

    # -- colorização -------------------------------------------------------
    @staticmethod
    def _has_gl(widget) -> bool:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget

        return isinstance(widget, QOpenGLWidget) or bool(
            widget.findChildren(QOpenGLWidget))

    def tint(self, widget) -> None:
        if widget is None or widget in self._tinted or self._has_gl(widget):
            return
        widget.setGraphicsEffect(RedOnlyEffect(widget))
        self._tinted.append(widget)

    def tint_window(self, window) -> None:
        """Colore o conteúdo de uma janela (o efeito não vale em janelas)."""
        if isinstance(window, QMainWindow):
            central = window.centralWidget()
            if central is not None and not self._has_gl(central):
                self.tint(central)
            for dock in window.findChildren(QDockWidget):
                self.tint(dock.widget())
            if window.statusBar() is not None:
                self.tint(window.statusBar())
        else:
            for child in window.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                if not child.isWindow():
                    self.tint(child)

    def eventFilter(self, obj, event) -> bool:
        if (event.type() == QEvent.Show and isinstance(obj, QWidget)
                and obj.isWindow() and not isinstance(obj, QMenu)):
            self.tint_window(obj)
        return False
