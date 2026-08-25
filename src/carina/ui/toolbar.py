"""Barra lateral compacta: botões quadrados com ícones desenhados.

Substitui os checkboxes/botões de texto do painel antigo — as opções
detalhadas migraram para o menu do topo.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget

BUTTON_PX = 40
ICON_PX = 26


def _icon(kind: str) -> QIcon:
    """Desenha o ícone (evita depender de arquivos externos)."""
    pix = QPixmap(ICON_PX, ICON_PX)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    fg = QColor(225, 232, 242)
    pen = QPen(fg, 1.6)
    p.setPen(pen)
    c = ICON_PX / 2

    if kind == "stars":
        for x, y, r in ((7, 8, 2.6), (17, 7, 1.8), (12, 15, 3.4),
                        (19, 18, 2.0), (8, 19, 1.6)):
            p.setBrush(fg)
            p.drawEllipse(QRectF(x - r / 2, y - r / 2, r, r))
    elif kind == "planets":
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(7, 7, 12, 12))
        p.save()
        p.translate(c, c)
        p.rotate(-25)
        p.drawEllipse(QRectF(-11, -3.2, 22, 6.4))
        p.restore()
    elif kind == "dso":
        p.drawEllipse(QRectF(4, 8, 18, 10))
        p.setBrush(fg)
        p.drawEllipse(QRectF(11.5, 11.5, 3, 3))
    elif kind == "milkyway":
        p.drawArc(QRectF(-2, 4, 30, 18), 20 * 16, 140 * 16)
        p.drawArc(QRectF(-2, 8, 30, 18), 20 * 16, 140 * 16)
    elif kind == "constellations":
        pts = [(5, 19), (10, 8), (17, 14), (21, 5)]
        p.setPen(QPen(fg, 1.4))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a[0], a[1], b[0], b[1])
        p.setBrush(fg)
        p.setPen(Qt.NoPen)
        for x, y in pts:
            p.drawEllipse(QRectF(x - 2, y - 2, 4, 4))
    elif kind == "grid":
        p.setPen(QPen(fg, 1.2))
        for i in range(1, 4):
            v = 6.5 * i
            p.drawLine(int(v), 4, int(v), 22)
            p.drawLine(4, int(v), 22, int(v))
    elif kind == "ground":
        p.drawLine(3, 14, 23, 14)
        p.setBrush(QColor(120, 150, 120))
        p.drawRect(QRectF(3, 14, 20, 8))
    elif kind == "back":
        p.drawLine(16, 6, 8, 13)
        p.drawLine(8, 13, 16, 20)
        p.drawLine(21, 6, 13, 13)
        p.drawLine(13, 13, 21, 20)
    elif kind == "forward":
        p.drawLine(10, 6, 18, 13)
        p.drawLine(18, 13, 10, 20)
        p.drawLine(5, 6, 13, 13)
        p.drawLine(13, 13, 5, 20)
    elif kind == "now":
        p.drawEllipse(QRectF(4, 4, 18, 18))
        p.drawLine(13, 8, 13, 13)
        p.drawLine(13, 13, 17, 16)
    elif kind == "measure":
        p.drawLine(5, 20, 21, 7)
        for x, y in ((5, 20), (21, 7)):
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(x - 2.5, y - 2.5, 5, 5))
    elif kind == "zoom":
        # retângulo de seleção com setas para dentro
        pen_dash = QPen(fg, 1.4)
        pen_dash.setStyle(Qt.DashLine)
        p.setPen(pen_dash)
        p.drawRect(QRectF(4, 6, 18, 14))
        p.setPen(QPen(fg, 1.6))
        p.drawLine(9, 11, 13, 13)
        p.drawLine(17, 11, 13, 13)
        p.drawLine(9, 15, 13, 13)
        p.drawLine(17, 15, 13, 13)
    elif kind == "chart":
        p.drawRect(QRectF(5, 4, 16, 19))
        p.drawLine(8, 10, 18, 10)
        p.drawLine(8, 14, 18, 14)
        p.drawLine(8, 18, 14, 18)
    elif kind == "track":
        p.drawEllipse(QRectF(4, 4, 18, 18))
        p.drawArc(QRectF(1, 7, 24, 16), 200 * 16, 140 * 16)
        p.setBrush(fg)
        p.drawEllipse(QRectF(11, 8, 4, 4))
    elif kind == "fov":
        p.drawRect(QRectF(4, 7, 18, 12))
        p.drawLine(13, 4, 13, 22)
        p.drawLine(4, 13, 22, 13)
    elif kind == "search":
        p.drawEllipse(QRectF(4, 4, 13, 13))
        p.drawLine(16, 16, 22, 22)
    elif kind == "below":
        # horizonte com céu acima e abaixo
        p.drawLine(3, 13, 23, 13)
        p.setBrush(fg)
        for x, y, r in ((8, 7, 2.4), (16, 6, 1.8), (12, 9, 1.6)):
            p.drawEllipse(QRectF(x - r / 2, y - r / 2, r, r))
        p.setBrush(Qt.NoBrush)
        for x, y, r in ((9, 19, 2.0), (17, 20, 1.6), (13, 17, 1.4)):
            p.drawEllipse(QRectF(x - r / 2, y - r / 2, r, r))
    elif kind == "moonpath":
        # luas em fases ao longo de um arco
        p.drawArc(QRectF(2, 6, 22, 20), 30 * 16, 120 * 16)
        p.setBrush(fg)
        p.drawEllipse(QRectF(4, 12, 5, 5))
        p.drawEllipse(QRectF(19, 12, 5, 5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(11, 6, 6, 6))
    elif kind == "marathon":
        # lista com marcadores
        p.drawLine(9, 7, 22, 7)
        p.drawLine(9, 13, 22, 13)
        p.drawLine(9, 19, 22, 19)
        p.setBrush(fg)
        for y in (7, 13, 19):
            p.drawEllipse(QRectF(3, y - 1.6, 3.2, 3.2))
        p.setBrush(Qt.NoBrush)
    elif kind == "print":
        p.drawRect(QRectF(7, 4, 12, 6))
        p.drawRect(QRectF(4, 10, 18, 8))
        p.drawRect(QRectF(7, 17, 12, 6))
    elif kind == "info":
        p.drawEllipse(QRectF(4, 4, 18, 18))
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.drawText(QRectF(4, 4, 18, 18), Qt.AlignCenter, "i")
    p.end()
    return QIcon(pix)


class SideToolBar(QWidget):
    """Coluna de botões quadrados (alterna camadas e aciona ferramentas)."""

    layerToggled = Signal(str, bool)
    mouseModeChanged = Signal(str)
    chartModeChanged = Signal(bool)
    timeStep = Signal(float)
    timeNow = Signal()
    action = Signal(str)          # 'search' | 'track' | 'fov' | 'info'

    # (chave da camada, dica, nome do ícone)
    LAYER_BUTTONS = [
        ("stars", "Estrelas", "stars"),
        ("planets", "Sistema Solar", "planets"),
        # mestre: apaga marcações e imagens juntas (no menu Exibir elas
        # continuam independentes)
        ("dso_master", "Céu profundo (marcações e imagens)", "dso"),
        ("milkyway", "Via Láctea", "milkyway"),
        ("const_lines", "Constelações", "constellations"),
        ("grid_altaz", "Grade horizontal", "grid"),
        # botão ÚNICO: marcado = solo opaco; desmarcado = vê abaixo do
        # horizonte (o SkyWidget mantém 'below_horizon' como o oposto)
        ("ground", "Solo opaco — desmarque para ver abaixo do horizonte",
         "ground"),
    ]

    STYLE = """
    QToolButton {
        border: 1px solid transparent;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.04);
    }
    QToolButton:hover {
        background: rgba(255, 255, 255, 0.13);
    }
    QToolButton:checked {
        background: rgba(80, 150, 235, 0.30);
        border-color: rgba(130, 190, 255, 0.65);
    }
    QToolButton:pressed {
        background: rgba(255, 255, 255, 0.22);
    }
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(BUTTON_PX + 14)
        self.setStyleSheet(self.STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.layer_buttons: dict[str, QToolButton] = {}
        for key, tip, icon_name in self.LAYER_BUTTONS:
            btn = self._button(icon_name, tip, checkable=True)
            btn.setChecked(True)
            btn.toggled.connect(
                lambda on, k=key: self.layerToggled.emit(k, on)
            )
            layout.addWidget(btn)
            self.layer_buttons[key] = btn

        layout.addWidget(self._separator())

        for kind, tip, secs in (
            ("back", "Retroceder um passo", -1.0),
            ("forward", "Avançar um passo", 1.0),
        ):
            btn = self._button(kind, tip)
            btn.clicked.connect(
                lambda _c=False, s=secs: self.timeStep.emit(s)
            )
            layout.addWidget(btn)
        btn_now = self._button("now", "Agora")
        btn_now.clicked.connect(self.timeNow.emit)
        layout.addWidget(btn_now)

        layout.addWidget(self._separator())

        self.tool_buttons: dict[str, QToolButton] = {}
        for kind, tip, mode in (
            ("measure", "Medir distância angular", "measure"),
            ("zoom", "Zoom por área", "zoom_rect"),
        ):
            btn = self._button(kind, tip, checkable=True)
            btn.clicked.connect(
                lambda _c=False, m=mode: self._on_tool(m)
            )
            layout.addWidget(btn)
            self.tool_buttons[mode] = btn

        self.btn_chart = self._button("chart", "Modo mapa para impressão",
                                      checkable=True)
        self.btn_chart.toggled.connect(self.chartModeChanged.emit)
        layout.addWidget(self.btn_chart)

        layout.addWidget(self._separator())

        btn_moon = self._button(
            "moonpath", "Previsão da Lua (28 dias)", checkable=True
        )
        btn_moon.toggled.connect(
            lambda on: self.layerToggled.emit("moon_forecast", on)
        )
        layout.addWidget(btn_moon)
        self.layer_buttons["moon_forecast"] = btn_moon

        for kind, tip in (
            ("search", "Buscar objeto"), ("track", "Rastrear na noite"),
            ("fov", "Campo de visão"), ("marathon", "Planejar maratona"),
            ("print", "Mapa para impressão"), ("info", "Crepúsculos e noite"),
        ):
            btn = self._button(kind, tip)
            btn.clicked.connect(lambda _c=False, k=kind: self.action.emit(k))
            layout.addWidget(btn)

        layout.addStretch(1)

    # ------------------------------------------------------------------
    def _button(self, kind: str, tip: str, checkable: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(_icon(kind))
        btn.setIconSize(QSize(ICON_PX, ICON_PX))
        btn.setFixedSize(BUTTON_PX, BUTTON_PX)
        btn.setToolTip(tip)
        btn.setCheckable(checkable)
        btn.setAutoRaise(True)
        return btn

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(8)
        return line

    def _on_tool(self, mode: str) -> None:
        """Ferramentas de mouse são exclusivas; reclicar volta para mover."""
        active = None
        for key, btn in self.tool_buttons.items():
            if key == mode and btn.isChecked():
                active = key
            elif key != mode:
                btn.setChecked(False)
        self.mouseModeChanged.emit(active or "pan")

    def set_layer_state(self, key: str, value: bool) -> None:
        btn = self.layer_buttons.get(key)
        if btn is not None and btn.isChecked() != value:
            btn.blockSignals(True)
            btn.setChecked(value)
            btn.blockSignals(False)
