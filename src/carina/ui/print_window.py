"""Gerador de mapas para impressão com anotações (item 11 completo).

Recebe a imagem do céu renderizada pelo SkyWidget (em modo carta) e permite
anotar por cima antes de imprimir/exportar: texto posicionado com o mouse,
setas, linhas, retângulos, elipses e desenho à mão livre, com escolha de cor
e espessura. Exporta PNG, PDF e SVG ou envia direto para a impressora.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QMarginsF, QPoint, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QFont, QImage, QPageLayout, QPageSize,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QFontDialog, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QSpinBox, QStackedWidget, QToolBar, QWidget,
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
        # anotações vivem nas coordenadas da IMAGEM: páginas grandes (cartas
        # a 200 dpi) pedem traço e fonte proporcionais ao tamanho
        big = max(1.0, base.width() / 1400.0)
        self.width = max(3, int(round(3 * big)))
        self.font = QFont("Segoe UI", 14, QFont.Bold)
        self.font.setPixelSize(int(19 * big))
        self._draft: Annotation | None = None
        self._drag_idx: int | None = None
        self._drag_off = QPointF()
        self.selected: int | None = None
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------------
    def sizeHint(self):
        from PySide6.QtCore import QSize

        k = min(1.0, 1400 / self.base.width(), 860 / self.base.height())
        return QSize(int(self.base.width() * k), int(self.base.height() * k))

    def _view(self) -> tuple[float, float, float]:
        """(escala, deslocamento x, y) que encaixa a página na janela."""
        k = min(self.width_px() / self.base.width(), self.height() / self.base.height())
        k = min(k, 2.0)
        ox = (self.width_px() - self.base.width() * k) / 2
        oy = (self.height() - self.base.height() * k) / 2
        return k, ox, oy

    def width_px(self) -> int:
        return QWidget.width(self)

    def _to_image(self, pos) -> QPointF:
        k, ox, oy = self._view()
        return QPointF((pos.x() - ox) / k, (pos.y() - oy) / k)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(40, 42, 48))
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        k, ox, oy = self._view()
        p.translate(ox, oy)
        p.scale(k, k)
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
        pos = self._to_image(event.position())
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
        pos = self._to_image(event.position())
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
    """Editor de mapas para impressão: uma ou várias páginas (cartas e
    atlas do gerador de carta), cada uma com as próprias anotações (textos,
    setas, desenho). Imprime ou exporta em PNG/PDF/SVG pelo mesmo caminho
    de renderização.

    ``page_mm`` (largura, altura em mm) indica que as páginas já trazem
    margens e moldura: o PDF e a impressão saem sem margem extra, no papel
    exato. Sem ele, vale o comportamento antigo (A4 com 8 mm de margem).
    """

    def __init__(self, base, title: str, parent=None, page_mm=None) -> None:
        super().__init__(parent)
        pages = list(base) if isinstance(base, (list, tuple)) else [base]
        self.setWindowTitle(self.tr("Mapa para impressão — anotações"))
        self.map_title = title
        self.page_mm = page_mm
        self.canvases = [AnnotatedCanvas(img, self) for img in pages]
        self.stack = QStackedWidget()
        for c in self.canvases:
            self.stack.addWidget(c)
        self.setCentralWidget(self.stack)
        first = pages[0]
        k = min(1.0, 1400 / first.width(), 860 / first.height())
        self.resize(int(first.width() * k) + 40, int(first.height() * k) + 140)

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
        spin.setRange(1, 60)
        spin.setValue(self.canvas.width)
        spin.valueChanged.connect(self._set_width)
        bar.addWidget(spin)
        bar.addSeparator()
        act_del = QAction(self.tr("Apagar selecionado"), self)
        act_del.setShortcut("Del")
        act_del.triggered.connect(self._delete_selected)
        bar.addAction(act_del)
        act_clear = QAction(self.tr("Limpar tudo"), self)
        act_clear.triggered.connect(self._clear)
        bar.addAction(act_clear)

        # navegação entre páginas (atlas)
        self.page_label = QLabel()
        if len(self.canvases) > 1:
            nav = QToolBar(self.tr("Páginas"))
            nav.setMovable(False)
            self.addToolBar(nav)
            prev_act = QAction("◀", self)
            prev_act.setShortcut("PgUp")
            prev_act.triggered.connect(lambda: self.go_to_page(self.stack.currentIndex() - 1))
            next_act = QAction("▶", self)
            next_act.setShortcut("PgDown")
            next_act.triggered.connect(lambda: self.go_to_page(self.stack.currentIndex() + 1))
            nav.addAction(prev_act)
            nav.addWidget(self.page_label)
            nav.addAction(next_act)
        self._update_page_label()

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
            "Use 'Selecionar / mover' para reposicionar; Del apaga."))

    # -- páginas ---------------------------------------------------------
    @property
    def canvas(self) -> "AnnotatedCanvas":
        return self.canvases[self.stack.currentIndex()]

    def go_to_page(self, index: int) -> None:
        index = max(0, min(len(self.canvases) - 1, index))
        self.stack.setCurrentIndex(index)
        self._update_page_label()

    def _update_page_label(self) -> None:
        self.page_label.setText(self.tr("  Página {i} de {n}  ").format(
            i=self.stack.currentIndex() + 1, n=len(self.canvases)))

    # -- ferramentas (valem para todas as páginas) ----------------------
    def _set_tool(self, key: str) -> None:
        for c in self.canvases:
            c.tool = key
            c.setCursor(Qt.ArrowCursor if key == "select" else Qt.CrossCursor)

    def _set_width(self, value: int) -> None:
        for c in self.canvases:
            c.width = value

    def _refresh_color(self) -> None:
        c = self.canvas.color
        self.color_action.setText(self.tr("Cor: {n}").format(n=c.name()))

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self.canvas.color, self,
                                      self.tr("Cor das anotações"))
        if color.isValid():
            for c in self.canvases:
                c.color = color
            self._refresh_color()
            if self.canvas.selected is not None:
                self.canvas.annotations[self.canvas.selected].color = color
                self.canvas.update()

    def _pick_font(self) -> None:
        font, ok = QFontDialog.getFont(self.canvas.font, self, self.tr("Fonte do texto"))
        if ok:
            for c in self.canvases:
                c.font = font
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
            self, "Carina", self.tr("Apagar todas as anotações desta página?")
        ) == QMessageBox.Yes:
            self.canvas.annotations.clear()
            self.canvas.selected = None
            self.canvas.update()

    # -- saída -----------------------------------------------------------------
    def _page_layout(self, canvas) -> QPageLayout:
        landscape = canvas.base.width() >= canvas.base.height()
        orient = QPageLayout.Landscape if landscape else QPageLayout.Portrait
        if self.page_mm:
            short, long_ = sorted(float(v) for v in self.page_mm)
            size = QPageSize(QSizeF(short, long_), QPageSize.Millimeter)
            return QPageLayout(size, orient, QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
        return QPageLayout(QPageSize(QPageSize.A4), orient, QMarginsF(8, 8, 8, 8),
                           QPageLayout.Millimeter)

    def write_pdf(self, path: str) -> None:
        """Todas as páginas num PDF (papel exato quando ``page_mm`` existe)."""
        from PySide6.QtGui import QPdfWriter

        writer = QPdfWriter(path)
        writer.setResolution(300)
        writer.setTitle(self.map_title)
        writer.setCreator("Carina")
        writer.setPageLayout(self._page_layout(self.canvases[0]))
        p = QPainter(writer)
        for i, c in enumerate(self.canvases):
            if i:
                writer.setPageLayout(self._page_layout(c))
                writer.newPage()
            c.render_full(p, QRectF(0, 0, writer.width(), writer.height()))
        p.end()

    def _print(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageLayout(self._page_layout(self.canvases[0]))
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        painter = QPainter(printer)
        for i, c in enumerate(self.canvases):
            if i:
                printer.newPage()
            c.render_full(painter, QRectF(printer.pageRect(QPrinter.DevicePixel)))
        painter.end()
        self.statusBar().showMessage(self.tr("Enviado para a impressora"), 5000)

    def _png_of(self, canvas) -> QPixmap:
        pix = QPixmap(canvas.base.size())
        pix.fill(Qt.white)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawImage(0, 0, canvas.base)
        canvas.draw_annotations(p)
        p.end()
        return pix

    def _export(self, fmt: str) -> None:
        filters = {"png": "PNG (*.png)", "pdf": "PDF (*.pdf)", "svg": "SVG (*.svg)"}
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar"), f"carta_ceu.{fmt}", filters[fmt])
        if not path:
            return
        try:
            if fmt == "pdf":
                self.write_pdf(path)
            elif fmt == "png":
                if len(self.canvases) == 1:
                    self._png_of(self.canvas).save(path, "PNG")
                else:                       # atlas: um arquivo por página
                    stem = path[:-4] if path.lower().endswith(".png") else path
                    for i, c in enumerate(self.canvases, 1):
                        self._png_of(c).save(f"{stem}_{i:02d}.png", "PNG")
            else:
                from PySide6.QtSvg import QSvgGenerator

                c = self.canvas
                gen = QSvgGenerator()
                gen.setFileName(path)
                gen.setSize(c.base.size())
                gen.setViewBox(QRectF(QPointF(0, 0), c.base.size()))
                gen.setTitle(self.map_title)
                p = QPainter(gen)
                p.drawImage(0, 0, c.base)
                c.draw_annotations(p)
                p.end()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Carina",
                                self.tr("Falha ao exportar: {e}").format(e=exc))
            return
        self.statusBar().showMessage(self.tr("Exportado: {p}").format(p=path), 6000)
