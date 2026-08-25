"""Gerador de mapas para impressão com anotações (item 11 completo).

Recebe a imagem do céu renderizada pelo SkyWidget (em modo carta) e permite
anotar por cima antes de imprimir/exportar: texto posicionado com o mouse,
setas, linhas, retângulos, elipses e desenho à mão livre, com escolha de cor
e espessura. Exporta PNG, PDF e SVG ou envia direto para a impressora.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QMarginsF, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QFont, QImage, QPageLayout, QPageSize,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QFontDialog, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QSpinBox, QToolBar, QWidget,
)

TOOLS = [
    ("select", "Selecionar / mover"),
    ("text", "Texto"),
    ("arrow", "Seta"),
    ("line", "Linha"),
    ("rect", "Retângulo"),
    ("ellipse", "Elipse"),
    ("free", "Desenho livre"),
]


@dataclass
class Annotation:
    """Uma anotação do mapa: texto, seta, linha, retângulo, elipse ou
    traço livre — com cor, espessura e fonte próprias."""

    kind: str
    color: QColor
    width: int = 2
    p0: QPointF = field(default_factory=QPointF)
    p1: QPointF = field(default_factory=QPointF)
    text: str = ""
    font: QFont = field(default_factory=lambda: QFont("Segoe UI", 14))
    points: list = field(default_factory=list)   # desenho livre

    def bounds(self) -> QRectF:
        """Retângulo envolvente — usado para seleção, arrasto e destaque."""
        if self.kind == "free" and self.points:
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            return QRectF(min(xs), min(ys), max(xs) - min(xs) or 1,
                          max(ys) - min(ys) or 1)
        if self.kind == "text":
            return QRectF(self.p0.x() - 4, self.p0.y() - 20,
                          max(40.0, 10 * len(self.text)), 26)
        return QRectF(self.p0, self.p1).normalized().adjusted(-6, -6, 6, 6)

    def draw(self, p: QPainter) -> None:
        """Desenha a anotação conforme o tipo (a seta calcula as duas
        hastes da ponta pela direção da linha)."""
        pen = QPen(self.color, self.width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if self.kind == "text":
            p.setFont(self.font)
            p.drawText(self.p0, self.text)
        elif self.kind == "line":
            p.drawLine(self.p0, self.p1)
        elif self.kind == "arrow":
            p.drawLine(self.p0, self.p1)
            ang = math.atan2(self.p1.y() - self.p0.y(),
                             self.p1.x() - self.p0.x())
            size = 9 + 2.5 * self.width
            for sign in (+1, -1):
                a = ang + sign * math.radians(155)
                p.drawLine(
                    self.p1,
                    QPointF(self.p1.x() + size * math.cos(a),
                            self.p1.y() + size * math.sin(a)),
                )
        elif self.kind == "rect":
            p.drawRect(QRectF(self.p0, self.p1).normalized())
        elif self.kind == "ellipse":
            p.drawEllipse(QRectF(self.p0, self.p1).normalized())
        elif self.kind == "free" and len(self.points) > 1:
            path = QPainterPath(self.points[0])
            for pt in self.points[1:]:
                path.lineTo(pt)
            p.drawPath(path)


class AnnotatedCanvas(QWidget):
    """Imagem do céu + camada de anotações, editável com o mouse."""

    def __init__(self, base: QImage, parent=None) -> None:
        super().__init__(parent)
        self.base = base
        self.annotations: list[Annotation] = []
        self.tool = "select"
        self.color = QColor(220, 40, 40)
        self.width = 3
        self.font = QFont("Segoe UI", 14, QFont.Bold)
        self._draft: Annotation | None = None
        self._drag_idx: int | None = None
        self._drag_off = QPointF()
        self.selected: int | None = None
        self.setMinimumSize(base.size())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------------
    def sizeHint(self):
        return self.base.size()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.drawImage(0, 0, self.base)
        self.draw_annotations(p, show_selection=True)
        p.end()

    def draw_annotations(self, p: QPainter, show_selection: bool = False) -> None:
        """Todas as anotações + o rascunho em andamento; a selecionada
        ganha o retângulo tracejado azul (só na tela, nunca na exportação)."""
        for i, ann in enumerate(self.annotations):
            ann.draw(p)
            if show_selection and i == self.selected:
                p.setPen(QPen(QColor(90, 170, 255), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(ann.bounds())
        if self._draft is not None:
            self._draft.draw(p)

    def render_full(self, painter: QPainter, target: QRectF) -> None:
        """Desenha céu + anotações escalados para o alvo (PDF/impressão)."""
        scale = min(target.width() / self.base.width(),
                    target.height() / self.base.height())
        w = self.base.width() * scale
        h = self.base.height() * scale
        ox = target.left() + (target.width() - w) / 2
        oy = target.top() + (target.height() - h) / 2
        painter.drawImage(QRectF(ox, oy, w, h), self.base)
        painter.save()
        painter.translate(ox, oy)
        painter.scale(scale, scale)
        self.draw_annotations(painter)
        painter.restore()

    # ------------------------------------------------------------------
    def _hit(self, pos: QPointF) -> int | None:
        """Anotação sob o ponto (a mais recente vence, como no desenho)."""
        for i in range(len(self.annotations) - 1, -1, -1):
            if self.annotations[i].bounds().contains(pos):
                return i
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = QPointF(event.position())
        if self.tool == "select":
            idx = self._hit(pos)
            self.selected = idx
            if idx is not None:
                self._drag_idx = idx
                self._drag_off = pos - self.annotations[idx].p0
            self.update()
            return
        if self.tool == "text":
            text, ok = QInputDialog.getText(
                self, self.tr("Texto"), self.tr("Texto a inserir:")
            )
            if ok and text.strip():
                self.annotations.append(
                    Annotation("text", QColor(self.color), self.width,
                               p0=pos, text=text.strip(), font=QFont(self.font))
                )
                self.selected = len(self.annotations) - 1
            self.update()
            return
        self._draft = Annotation(
            self.tool, QColor(self.color), self.width, p0=pos, p1=pos,
            points=[pos] if self.tool == "free" else [],
        )
        self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = QPointF(event.position())
        if self._drag_idx is not None:
            ann = self.annotations[self._drag_idx]
            delta = pos - self._drag_off - ann.p0
            ann.p0 += delta
            ann.p1 += delta
            ann.points = [pt + delta for pt in ann.points]
            self.update()
            return
        if self._draft is not None:
            self._draft.p1 = pos
            if self._draft.kind == "free":
                self._draft.points.append(pos)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        self._drag_idx = None
        if self._draft is not None:
            keep = (self._draft.kind == "free" and len(self._draft.points) > 2) \
                or (QRectF(self._draft.p0, self._draft.p1)
                    .normalized().width() > 3) \
                or (QRectF(self._draft.p0, self._draft.p1)
                    .normalized().height() > 3)
            if keep:
                self.annotations.append(self._draft)
                self.selected = len(self.annotations) - 1
            self._draft = None
            self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and \
                self.selected is not None:
            del self.annotations[self.selected]
            self.selected = None
            self.update()
        elif event.key() == Qt.Key_Escape:
            self.selected = None
            self.update()
        else:
            super().keyPressEvent(event)


class PrintMapWindow(QMainWindow):
    """Editor do mapa para impressão: recebe a captura do céu em modo
    carta, permite anotar livremente (textos, setas, desenho) e imprime ou
    exporta em PNG/PDF/SVG pelo mesmo caminho de renderização."""

    def __init__(self, base: QImage, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Mapa para impressão — anotações"))
        self.canvas = AnnotatedCanvas(base, self)
        self.setCentralWidget(self.canvas)
        self.map_title = title
        self.resize(min(1500, base.width() + 40), min(950, base.height() + 120))

        bar = QToolBar(self.tr("Ferramentas"))
        bar.setMovable(False)
        self.addToolBar(bar)
        group = QActionGroup(self)
        for key, label in TOOLS:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(group)
            act.triggered.connect(lambda _c=False, k=key: self._set_tool(k))
            bar.addAction(act)
            if key == "select":
                act.setChecked(True)
        bar.addSeparator()

        self.color_action = QAction(self.tr("Cor…"), self)
        self.color_action.triggered.connect(self._pick_color)
        bar.addAction(self.color_action)
        self._refresh_color()

        act_font = QAction(self.tr("Fonte…"), self)
        act_font.triggered.connect(self._pick_font)
        bar.addAction(act_font)

        bar.addWidget(QLabel(self.tr("  Espessura: ")))
        spin = QSpinBox()
        spin.setRange(1, 20)
        spin.setValue(self.canvas.width)
        spin.valueChanged.connect(lambda v: setattr(self.canvas, "width", v))
        bar.addWidget(spin)

        bar.addSeparator()
        act_del = QAction(self.tr("Apagar selecionado"), self)
        act_del.setShortcut("Del")
        act_del.triggered.connect(self._delete_selected)
        bar.addAction(act_del)
        act_clear = QAction(self.tr("Limpar tudo"), self)
        act_clear.triggered.connect(self._clear)
        bar.addAction(act_clear)

        m_file = self.menuBar().addMenu(self.tr("&Arquivo"))
        for label, slot, shortcut in (
            (self.tr("Imprimir…"), self._print, "Ctrl+P"),
            (self.tr("Exportar PNG…"), lambda: self._export("png"), ""),
            (self.tr("Exportar PDF…"), lambda: self._export("pdf"), ""),
            (self.tr("Exportar SVG…"), lambda: self._export("svg"), ""),
        ):
            act = QAction(label, self)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(slot)
            m_file.addAction(act)
        m_file.addSeparator()
        act_close = QAction(self.tr("Fechar"), self)
        act_close.setShortcut("Ctrl+W")
        act_close.triggered.connect(self.close)
        m_file.addAction(act_close)

        self.statusBar().showMessage(self.tr(
            "Escolha uma ferramenta e desenhe sobre o mapa. "
            "Use 'Selecionar / mover' para reposicionar; Del apaga."
        ))

    # ------------------------------------------------------------------
    def _set_tool(self, key: str) -> None:
        self.canvas.tool = key
        self.canvas.setCursor(
            Qt.ArrowCursor if key == "select" else Qt.CrossCursor
        )

    def _refresh_color(self) -> None:
        c = self.canvas.color
        self.color_action.setText(self.tr("Cor: {n}").format(n=c.name()))

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self.canvas.color, self,
                                      self.tr("Cor das anotações"))
        if color.isValid():
            self.canvas.color = color
            self._refresh_color()
            if self.canvas.selected is not None:
                self.canvas.annotations[self.canvas.selected].color = color
                self.canvas.update()

    def _pick_font(self) -> None:
        font, ok = QFontDialog.getFont(self.canvas.font, self,
                                       self.tr("Fonte do texto"))
        if ok:
            self.canvas.font = font
            if self.canvas.selected is not None:
                ann = self.canvas.annotations[self.canvas.selected]
                if ann.kind == "text":
                    ann.font = font
                    self.canvas.update()

    def _delete_selected(self) -> None:
        if self.canvas.selected is not None:
            del self.canvas.annotations[self.canvas.selected]
            self.canvas.selected = None
            self.canvas.update()

    def _clear(self) -> None:
        if not self.canvas.annotations:
            return
        if QMessageBox.question(
            self, "Carina", self.tr("Apagar todas as anotações?")
        ) == QMessageBox.Yes:
            self.canvas.annotations.clear()
            self.canvas.selected = None
            self.canvas.update()

    # ------------------------------------------------------------------
    def _print(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(
            QPageLayout.Landscape
            if self.canvas.base.width() >= self.canvas.base.height()
            else QPageLayout.Portrait
        )
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        painter = QPainter(printer)
        rect = QRectF(printer.pageRect(QPrinter.DevicePixel))
        self.canvas.render_full(painter, rect)
        painter.end()
        self.statusBar().showMessage(self.tr("Enviado para a impressora"), 5000)

    def _export(self, fmt: str) -> None:
        filters = {"png": "PNG (*.png)", "pdf": "PDF (*.pdf)",
                   "svg": "SVG (*.svg)"}
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar"), f"carta_ceu.{fmt}", filters[fmt]
        )
        if not path:
            return
        try:
            if fmt == "png":
                pix = QPixmap(self.canvas.base.size())
                pix.fill(Qt.white)
                p = QPainter(pix)
                p.setRenderHint(QPainter.Antialiasing)
                p.drawImage(0, 0, self.canvas.base)
                self.canvas.draw_annotations(p)
                p.end()
                pix.save(path, "PNG")
            elif fmt == "pdf":
                from PySide6.QtGui import QPdfWriter

                writer = QPdfWriter(path)
                writer.setPageSize(QPageSize(QPageSize.A4))
                writer.setPageOrientation(
                    QPageLayout.Landscape
                    if self.canvas.base.width() >= self.canvas.base.height()
                    else QPageLayout.Portrait
                )
                writer.setPageMargins(QMarginsF(8, 8, 8, 8),
                                      QPageLayout.Millimeter)
                writer.setResolution(300)
                p = QPainter(writer)
                self.canvas.render_full(
                    p, QRectF(0, 0, writer.width(), writer.height())
                )
                p.end()
            else:
                from PySide6.QtSvg import QSvgGenerator

                gen = QSvgGenerator()
                gen.setFileName(path)
                gen.setSize(self.canvas.base.size())
                gen.setViewBox(QRectF(QPointF(0, 0), self.canvas.base.size()))
                gen.setTitle(self.map_title)
                p = QPainter(gen)
                p.drawImage(0, 0, self.canvas.base)
                self.canvas.draw_annotations(p)
                p.end()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, "Carina",
                self.tr("Falha ao exportar: {e}").format(e=exc),
            )
            return
        self.statusBar().showMessage(
            self.tr("Exportado: {p}").format(p=path), 6000
        )
