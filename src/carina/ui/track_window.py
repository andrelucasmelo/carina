"""Janela de rastreamento noturno: caminho do objeto no céu durante a noite.

Regras de desenho (definidas pelo usuário):
  A. só o trecho acima do horizonte aparece;
  B. noite civil = pontilhado, náutica = tracejado, astronômica = contínuo;
     trechos afetados pela Lua trocam de cor;
  C. horários rotulados e marcadores a cada 30 minutos;
  D. cores configuráveis para Lua e para altitudes abaixo de 20°/30°/45°;
  E. escolha das linhas horizontais (grade) exibidas;
  F. exportação em PDF, PNG, JPG e SVG;
  G. bordas com dados do objeto e da geração (ano opcional);
  H. todas as opções num menu à parte.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontMetricsF, QPainter, QPageLayout, QPageSize,
    QPdfWriter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..core.tracking import TrackResult

BAND_STYLE = {
    "civil": Qt.DotLine,
    "nautical": Qt.DashLine,
    "astro": Qt.SolidLine,
    "day": Qt.DotLine,
}
BAND_LABEL = {
    "civil": "noite civil", "nautical": "noite náutica",
    "astro": "noite astronômica", "day": "dia",
}


@dataclass
class TrackSettings:
    """Configurações da visualização (menu à parte, item H)."""

    color_normal: QColor = field(default_factory=lambda: QColor(120, 210, 255))
    color_moon: QColor = field(default_factory=lambda: QColor(255, 170, 60))
    color_low20: QColor = field(default_factory=lambda: QColor(235, 90, 90))
    color_low30: QColor = field(default_factory=lambda: QColor(235, 150, 70))
    color_low45: QColor = field(default_factory=lambda: QColor(220, 210, 100))
    use_moon_color: bool = True
    use_alt_colors: bool = True
    thr_low: float = 20.0
    thr_mid: float = 30.0
    thr_high: float = 45.0
    grid_alt_step: float = 15.0     # linhas de altitude
    grid_az_step: float = 30.0      # linhas de azimute
    show_alt_grid: bool = True
    show_az_grid: bool = True
    show_cardinals: bool = True
    label_every_min: int = 60       # rótulos de hora
    marker_every_min: int = 30      # marcadores (item C)
    show_year: bool = True          # item G
    dark_theme: bool = True

    def color_for(self, alt_deg: float, moon_affected: bool) -> QColor:
        if moon_affected and self.use_moon_color:
            return self.color_moon
        if self.use_alt_colors:
            if alt_deg < self.thr_low:
                return self.color_low20
            if alt_deg < self.thr_mid:
                return self.color_low30
            if alt_deg < self.thr_high:
                return self.color_low45
        return self.color_normal


def _hm(value: dt.datetime | None) -> str:
    return value.astimezone().strftime("%H:%M") if value else "—"


class TrackCanvas(QWidget):
    """Desenha a trajetória em projeção azimute × altitude."""

    def __init__(self, result: TrackResult, settings: TrackSettings,
                 location: str, parent=None) -> None:
        super().__init__(parent)
        self.result = result
        self.settings = settings
        self.location = location
        self.setMinimumSize(720, 460)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        self.render_to(painter, QRectF(self.rect()))
        painter.end()

    # ------------------------------------------------------------------
    def render_to(self, painter: QPainter, rect: QRectF) -> None:
        s = self.settings
        bg = QColor(16, 18, 24) if s.dark_theme else QColor(255, 255, 255)
        fg = QColor(225, 230, 240) if s.dark_theme else QColor(25, 25, 25)
        grid = QColor(70, 82, 100) if s.dark_theme else QColor(200, 200, 200)
        painter.fillRect(rect, bg)

        pts = self.result.points
        if not pts:
            painter.setPen(fg)
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(
                rect, Qt.AlignCenter,
                self.tr("O objeto não fica acima do horizonte nesta noite."),
            )
            self._draw_borders(painter, rect, fg)
            return

        self._render_polar(painter, rect, fg, grid)
        self._draw_borders(painter, rect, fg)

    # ------------------------------------------------------------------
    def _render_polar(self, painter: QPainter, rect: QRectF, fg: QColor,
                      grid: QColor) -> None:
        """Céu redondo visto de baixo: zênite no centro, horizonte na borda.

        Azimute cresce do N (topo) para o L (esquerda... veja abaixo): usamos
        a convenção de cartas celestes — N em cima, L à esquerda —, de modo
        que a carta corresponde ao céu quando erguida sobre a cabeça.
        """
        s = self.settings
        pts = self.result.points
        top = rect.top() + 74.0
        bottom = rect.bottom() - 118.0
        radius = max(40.0, min(rect.width() / 2 - 40.0, (bottom - top) / 2))
        cx = rect.center().x()
        cy = (top + bottom) / 2.0

        def to_xy(az_rad: float, alt_deg: float) -> QPointF:
            r = radius * (1.0 - max(0.0, min(90.0, alt_deg)) / 90.0)
            # N no topo, L à esquerda (vista do céu, não do mapa do chão)
            return QPointF(
                cx - r * math.sin(az_rad), cy - r * math.cos(az_rad)
            )

        # --- círculos de altitude ---
        painter.setFont(QFont("Segoe UI", 8))
        if s.show_alt_grid:
            alt = 0.0
            while alt < 90.0:
                rr = radius * (1.0 - alt / 90.0)
                painter.setPen(
                    QPen(grid, 1.4 if alt == 0.0 else 1.0,
                         Qt.SolidLine if alt == 0.0 else Qt.DotLine)
                )
                painter.drawEllipse(QPointF(cx, cy), rr, rr)
                if alt > 0.0:
                    painter.setPen(fg)
                    painter.drawText(
                        QRectF(cx - 18, cy - rr - 9, 36, 16),
                        Qt.AlignCenter, f"{alt:.0f}°",
                    )
                alt += s.grid_alt_step

        # --- raios de azimute ---
        if s.show_az_grid:
            a = 0.0
            while a < 360.0:
                ar = math.radians(a)
                painter.setPen(QPen(grid, 1.0, Qt.DotLine))
                painter.drawLine(QPointF(cx, cy), to_xy(ar, 0.0))
                a += s.grid_az_step

        # --- pontos cardeais na borda (reservam espaço antes dos horários) ---
        taken: list[QRectF] = []
        if s.show_cardinals:
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.setPen(QColor(230, 140, 60) if s.dark_theme
                           else QColor(170, 80, 20))
            for name, az_deg in (
                ("N", 0), ("NE", 45), ("L", 90), ("SE", 135),
                ("S", 180), ("SO", 225), ("O", 270), ("NO", 315),
            ):
                ar = math.radians(az_deg)
                px = cx - (radius + 22) * math.sin(ar)
                py = cy - (radius + 22) * math.cos(ar)
                box = QRectF(px - 16, py - 10, 32, 20)
                taken.append(box)
                painter.drawText(box, Qt.AlignCenter, name)

        # --- trajetória (itens A, B, D) ---
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            if (p1.when_utc - p0.when_utc).total_seconds() > 30 * 60:
                continue
            alt_deg = math.degrees((p0.alt + p1.alt) / 2)
            moon = p0.moon_affected or p1.moon_affected
            pen = QPen(s.color_for(alt_deg, moon), 2.6)
            pen.setStyle(BAND_STYLE.get(p0.band, Qt.SolidLine))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                to_xy(p0.az, math.degrees(p0.alt)),
                to_xy(p1.az, math.degrees(p1.alt)),
            )

        # --- marcadores e horários (item C) ---
        painter.setFont(QFont("Segoe UI", 8))
        for p in pts:
            local = p.when_utc.astimezone()
            minutes = local.hour * 60 + local.minute
            xy = to_xy(p.az, math.degrees(p.alt))
            if minutes % s.marker_every_min == 0:
                color = s.color_for(math.degrees(p.alt), p.moon_affected)
                painter.setPen(QPen(color, 1.4))
                full = minutes % s.label_every_min == 0
                painter.setBrush(color if full else Qt.NoBrush)
                painter.drawEllipse(xy, 3.8 if full else 2.4,
                                    3.8 if full else 2.4)
                painter.setBrush(Qt.NoBrush)
            if minutes % s.label_every_min == 0:
                # afasta o rótulo radialmente e evita sobrepor outros
                dx, dy = xy.x() - cx, xy.y() - cy
                norm = max(1.0, math.hypot(dx, dy))
                placed = None
                for offset in (18, -18, 30, -30):
                    box = QRectF(
                        xy.x() + dx / norm * offset - 24,
                        xy.y() + dy / norm * offset - 8, 48, 16,
                    )
                    if not any(box.intersects(o) for o in taken):
                        placed = box
                        break
                if placed is None:
                    continue
                taken.append(placed)
                painter.setPen(fg)
                painter.drawText(
                    placed, Qt.AlignCenter, local.strftime("%H:%M")
                )

        # legenda no rodapé, abaixo do "S" (não cobre o círculo nem o "N")
        self._draw_legend(painter, QRectF(
            rect.left() + 40, bottom + 44, rect.width() - 80, 20,
        ), fg)

    # ------------------------------------------------------------------
    def _draw_legend(self, painter: QPainter, plot: QRectF, fg: QColor) -> None:
        s = self.settings
        painter.setFont(QFont("Segoe UI", 8))
        items = [
            (Qt.DotLine, s.color_normal, "noite civil"),
            (Qt.DashLine, s.color_normal, "noite náutica"),
            (Qt.SolidLine, s.color_normal, "noite astronômica"),
        ]
        if s.use_moon_color:
            items.append((Qt.SolidLine, s.color_moon, "afetado pela Lua"))
        if s.use_alt_colors:
            items += [
                (Qt.SolidLine, s.color_low20, f"alt < {s.thr_low:.0f}°"),
                (Qt.SolidLine, s.color_low30, f"alt < {s.thr_mid:.0f}°"),
                (Qt.SolidLine, s.color_low45, f"alt < {s.thr_high:.0f}°"),
            ]
        fm = QFontMetricsF(painter.font())
        x = plot.left()
        y = plot.top() - 22
        for style, color, text in items:
            width = 42 + fm.horizontalAdvance(text)
            if x + width > plot.right():   # quebra de linha na legenda
                x = plot.left()
                y -= 16
            pen = QPen(color, 2.2)
            pen.setStyle(style)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, y), QPointF(x + 26, y))
            painter.setPen(fg)
            painter.drawText(QPointF(x + 32, y + 4), text)
            x += width

    def _draw_borders(self, painter: QPainter, rect: QRectF, fg: QColor) -> None:
        """Informações do objeto e da geração nas bordas (item G)."""
        s = self.settings
        res = self.result
        painter.setPen(fg)
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.drawText(
            QRectF(rect.left() + 12, rect.top() + 8, rect.width() - 24, 22),
            Qt.AlignLeft | Qt.AlignVCenter, res.label,
        )

        night = res.night
        fmt = "%d/%m/%Y" if s.show_year else "%d/%m"
        night_txt = ""
        if night and night.sunset:
            night_txt = f"Noite de {night.sunset.astimezone().strftime(fmt)}"
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(
            QRectF(rect.left() + 12, rect.top() + 30, rect.width() - 24, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{night_txt} · {self.location}",
        )

        parts = []
        if res.points:
            parts.append(f"visível {_hm(res.rise_utc)}–{_hm(res.set_utc)}")
            parts.append(f"alt. máx. {math.degrees(res.max_alt):.0f}° "
                         f"às {_hm(res.max_alt_utc)}")
        parts.append(f"Lua {res.moon_illum * 100:.0f}%")
        if night:
            parts.append(
                f"astronômica {_hm(night.astro_dusk)}–{_hm(night.astro_dawn)}"
            )
        painter.drawText(
            QRectF(rect.left() + 12, rect.bottom() - 40, rect.width() - 24, 18),
            Qt.AlignLeft | Qt.AlignVCenter, " · ".join(parts),
        )
        stamp = dt.datetime.now()
        gen = stamp.strftime(
            "%d/%m/%Y %H:%M" if s.show_year else "%d/%m %H:%M"
        )
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            QRectF(rect.left() + 12, rect.bottom() - 22, rect.width() - 24, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"Carina · gerado em {gen}",
        )


class TrackSettingsDialog(QDialog):
    """Menu de configurações da visualização (item H)."""

    def __init__(self, settings: TrackSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Configurações do rastreamento"))
        self.s = settings
        layout = QVBoxLayout(self)

        colors = QGroupBox(self.tr("Cores"))
        form = QFormLayout(colors)
        self._color_buttons = {}
        for attr, label in (
            ("color_normal", self.tr("Traçado normal")),
            ("color_moon", self.tr("Afetado pela Lua")),
            ("color_low20", self.tr("Altitude baixa (1º limiar)")),
            ("color_low30", self.tr("Altitude baixa (2º limiar)")),
            ("color_low45", self.tr("Altitude baixa (3º limiar)")),
        ):
            btn = QPushButton()
            btn.setMinimumWidth(90)
            self._paint_button(btn, getattr(self.s, attr))
            btn.clicked.connect(lambda _c=False, a=attr: self._pick_color(a))
            form.addRow(label, btn)
            self._color_buttons[attr] = btn
        self.chk_moon = QCheckBox(self.tr("Trocar cor com a Lua próxima"))
        self.chk_moon.setChecked(self.s.use_moon_color)
        self.chk_alt = QCheckBox(self.tr("Trocar cor por altitude"))
        self.chk_alt.setChecked(self.s.use_alt_colors)
        form.addRow(self.chk_moon)
        form.addRow(self.chk_alt)
        layout.addWidget(colors)

        thr = QGroupBox(self.tr("Limiares de altitude"))
        tform = QFormLayout(thr)
        self.spin_low = self._spin(self.s.thr_low)
        self.spin_mid = self._spin(self.s.thr_mid)
        self.spin_high = self._spin(self.s.thr_high)
        tform.addRow(self.tr("1º limiar:"), self.spin_low)
        tform.addRow(self.tr("2º limiar:"), self.spin_mid)
        tform.addRow(self.tr("3º limiar:"), self.spin_high)
        layout.addWidget(thr)

        grid = QGroupBox(self.tr("Grade e rótulos"))
        gform = QFormLayout(grid)
        self.chk_alt_grid = QCheckBox(self.tr("Linhas de altitude"))
        self.chk_alt_grid.setChecked(self.s.show_alt_grid)
        self.chk_az_grid = QCheckBox(self.tr("Linhas de azimute"))
        self.chk_az_grid.setChecked(self.s.show_az_grid)
        self.chk_cardinals = QCheckBox(self.tr("Pontos cardeais"))
        self.chk_cardinals.setChecked(self.s.show_cardinals)
        self.spin_alt_step = self._spin(self.s.grid_alt_step, 5.0, 45.0)
        self.spin_az_step = self._spin(self.s.grid_az_step, 5.0, 90.0)
        self.combo_marker = QComboBox()
        for label, val in (("15 min", 15), ("30 min", 30), ("60 min", 60)):
            self.combo_marker.addItem(label, val)
        self.combo_marker.setCurrentIndex(
            [15, 30, 60].index(self.s.marker_every_min)
            if self.s.marker_every_min in (15, 30, 60) else 1
        )
        self.combo_label = QComboBox()
        for label, val in (("30 min", 30), ("1 hora", 60), ("2 horas", 120)):
            self.combo_label.addItem(label, val)
        self.combo_label.setCurrentIndex(
            [30, 60, 120].index(self.s.label_every_min)
            if self.s.label_every_min in (30, 60, 120) else 1
        )
        self.chk_year = QCheckBox(self.tr("Mostrar o ano nas datas"))
        self.chk_year.setChecked(self.s.show_year)
        self.chk_dark = QCheckBox(self.tr("Tema escuro"))
        self.chk_dark.setChecked(self.s.dark_theme)
        gform.addRow(self.chk_alt_grid)
        gform.addRow(self.tr("Passo de altitude:"), self.spin_alt_step)
        gform.addRow(self.chk_az_grid)
        gform.addRow(self.tr("Passo de azimute:"), self.spin_az_step)
        gform.addRow(self.chk_cardinals)
        gform.addRow(self.tr("Marcadores a cada:"), self.combo_marker)
        gform.addRow(self.tr("Horários a cada:"), self.combo_label)
        gform.addRow(self.chk_year)
        gform.addRow(self.chk_dark)
        layout.addWidget(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _spin(value: float, lo: float = 0.0, hi: float = 89.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(0)
        spin.setSuffix("°")
        spin.setValue(value)
        return spin

    @staticmethod
    def _paint_button(btn: QPushButton, color: QColor) -> None:
        btn.setStyleSheet(
            f"background-color: {color.name()}; color: "
            f"{'#000' if color.lightness() > 128 else '#fff'}"
        )
        btn.setText(color.name())

    def _pick_color(self, attr: str) -> None:
        color = QColorDialog.getColor(getattr(self.s, attr), self)
        if color.isValid():
            setattr(self.s, attr, color)
            self._paint_button(self._color_buttons[attr], color)

    def _apply(self) -> None:
        s = self.s
        s.use_moon_color = self.chk_moon.isChecked()
        s.use_alt_colors = self.chk_alt.isChecked()
        s.thr_low = self.spin_low.value()
        s.thr_mid = self.spin_mid.value()
        s.thr_high = self.spin_high.value()
        s.show_alt_grid = self.chk_alt_grid.isChecked()
        s.show_az_grid = self.chk_az_grid.isChecked()
        s.show_cardinals = self.chk_cardinals.isChecked()
        s.grid_alt_step = self.spin_alt_step.value()
        s.grid_az_step = self.spin_az_step.value()
        s.marker_every_min = int(self.combo_marker.currentData())
        s.label_every_min = int(self.combo_label.currentData())
        s.show_year = self.chk_year.isChecked()
        s.dark_theme = self.chk_dark.isChecked()
        self.accept()


class TrackWindow(QMainWindow):
    def __init__(self, result: TrackResult, location: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            self.tr("Rastreamento noturno — {name}").format(name=result.label)
        )
        self.resize(980, 620)
        self.settings = TrackSettings()
        self.canvas = TrackCanvas(result, self.settings, location, self)
        self.setCentralWidget(self.canvas)

        m_file = self.menuBar().addMenu(self.tr("&Arquivo"))
        for label, fmt in (
            (self.tr("Exportar PNG…"), "png"),
            (self.tr("Exportar JPG…"), "jpg"),
            (self.tr("Exportar PDF…"), "pdf"),
            (self.tr("Exportar SVG…"), "svg"),
        ):
            act = QAction(label, self)
            act.triggered.connect(lambda _c=False, f=fmt: self.export(f))
            m_file.addAction(act)
        m_file.addSeparator()
        act_close = QAction(self.tr("Fechar"), self)
        act_close.setShortcut("Ctrl+W")
        act_close.triggered.connect(self.close)
        m_file.addAction(act_close)

        m_cfg = self.menuBar().addMenu(self.tr("&Configurações"))
        act_cfg = QAction(self.tr("Opções da visualização…"), self)
        act_cfg.setShortcut("Ctrl+P")
        act_cfg.triggered.connect(self._open_settings)
        m_cfg.addAction(act_cfg)

        self.statusBar().showMessage(self._summary(result))

    # ------------------------------------------------------------------
    def _summary(self, res: TrackResult) -> str:
        if not res.points:
            return self.tr("Objeto abaixo do horizonte durante toda a noite.")
        moon_pts = sum(1 for p in res.points if p.moon_affected)
        return (
            f"{len(res.points)} pontos · visível {_hm(res.rise_utc)}–"
            f"{_hm(res.set_utc)} · alt. máx. "
            f"{math.degrees(res.max_alt):.0f}° · "
            f"{moon_pts} pontos afetados pela Lua"
        )

    def _open_settings(self) -> None:
        dlg = TrackSettingsDialog(self.settings, self)
        if dlg.exec():
            self.canvas.update()

    # ------------------------------------------------------------------
    def export(self, fmt: str) -> None:
        filters = {
            "png": "PNG (*.png)", "jpg": "JPEG (*.jpg)",
            "pdf": "PDF (*.pdf)", "svg": "SVG (*.svg)",
        }
        name = self.canvas.result.label.replace(" ", "_")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar"), f"{name}_rastreamento.{fmt}",
            filters[fmt],
        )
        if not path:
            return
        try:
            if fmt in ("png", "jpg"):
                scale = 2
                pix = QPixmap(self.canvas.width() * scale,
                              self.canvas.height() * scale)
                pix.fill(Qt.transparent)
                painter = QPainter(pix)
                painter.scale(scale, scale)
                painter.setRenderHint(QPainter.Antialiasing)
                self.canvas.render_to(painter, QRectF(self.canvas.rect()))
                painter.end()
                pix.save(path, fmt.upper(), 95)
            elif fmt == "pdf":
                writer = QPdfWriter(path)
                writer.setPageSize(QPageSize(QPageSize.A4))
                writer.setPageOrientation(QPageLayout.Landscape)
                writer.setPageMargins(QMarginsF(8, 8, 8, 8), QPageLayout.Millimeter)
                writer.setResolution(300)
                painter = QPainter(writer)
                page = QRectF(0, 0, writer.width(), writer.height())
                self.canvas.render_to(painter, page)
                painter.end()
            else:  # svg
                from PySide6.QtSvg import QSvgGenerator

                gen = QSvgGenerator()
                gen.setFileName(path)
                gen.setSize(self.canvas.size())
                gen.setViewBox(self.canvas.rect())
                gen.setTitle(self.canvas.result.label)
                gen.setDescription("Carina — rastreamento noturno")
                painter = QPainter(gen)
                self.canvas.render_to(painter, QRectF(self.canvas.rect()))
                painter.end()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, "Carina",
                self.tr("Falha ao exportar: {e}").format(e=exc),
            )
            return
        self.statusBar().showMessage(
            self.tr("Exportado: {p}").format(p=path), 6000
        )
