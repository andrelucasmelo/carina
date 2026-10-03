"""Planejador de foto lunar e programa Lunar 100 (v0.17 T6).

**Planejador**: as próximas noites, uma por linha — fase, nascer e ocaso
com o azimute (para a foto da Lua sobre a paisagem), altura máxima no
escuro e o tipo de foto que a fase favorece. A noite escolhida mostra o
gráfico de altura × hora, as formações do terminador e quantos quadros de
mosaico o seu conjunto (telescópio + câmera) precisa para o disco inteiro.

**Lunar 100**: os cem alvos de Charles Wood com o progresso tirado do
diário; um clique leva à formação na Janela da Lua.
"""

from __future__ import annotations

import datetime as dt
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QProgressBar,
                               QPushButton, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout,
                               QWidget)

from ..core import moon as moonlib
from ..core.formats import num
from ..core.localtime import to_local

WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

KIND_LABEL = {
    "relevo": "Relevo no terminador",
    "disco": "Disco inteiro / paisagem",
    "cinerea": "Luz cinérea",
    "nenhuma": "Lua baixa ou ausente",
}


class AltitudeChart(QWidget):
    """Altura da Lua ao longo da noite, com o crepúsculo ao fundo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.night: moonlib.PhotoNight | None = None

    def set_night(self, night) -> None:
        self.night = night
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(14, 18, 28))
        n = self.night
        if n is None or n.alts is None or not n.times:
            p.end()
            return
        left, right, top, bottom = 34, 8, 8, 22
        w = self.width() - left - right
        h = self.height() - top - bottom
        cnt = len(n.times)

        def x_of(i):
            return left + w * i / max(cnt - 1, 1)

        def y_of(alt):
            return top + h * (1 - max(0.0, min(90.0, alt)) / 90.0)

        # fundo: céu claro / crepúsculo / noite
        for i in range(cnt - 1):
            s = float(n.sun_alts[i])
            shade = 70 if s > 0 else 45 if s > -6 else 30 if s > -12 else 22 if s > -18 else 12
            p.fillRect(QRectF(x_of(i), top, x_of(i + 1) - x_of(i) + 1, h),
                       QColor(shade, shade + 4, shade + 16))
        p.setPen(QPen(QColor(90, 100, 120), 1, Qt.DotLine))
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        for alt in (0, 30, 60):
            y = y_of(alt)
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.drawText(QRectF(0, y - 8, left - 4, 16), Qt.AlignRight | Qt.AlignVCenter, f"{alt}°")
        path = QPainterPath()
        started = False
        for i in range(cnt):
            a = float(n.alts[i])
            if a < 0:
                started = False
                continue
            pt = QPointF(x_of(i), y_of(a))
            if started:
                path.lineTo(pt)
            else:
                path.moveTo(pt)
                started = True
        p.setPen(QPen(QColor(235, 230, 200), 2))
        p.drawPath(path)
        p.setPen(QColor(150, 160, 180))
        for i, t in enumerate(n.times):
            lt = to_local(t)
            if lt.minute == 0 and lt.hour % 2 == 0:
                x = x_of(i)
                p.drawText(QRectF(x - 16, top + h + 3, 32, 16), Qt.AlignCenter, f"{lt:%H}h")
        p.end()


class MoonPlannerDialog(QDialog):
    """Planejar ▸ Lua ▸ Planejador de foto lunar."""

    nightChosen = Signal(object)       # datetime UTC (altura máxima)

    def __init__(self, engine, start_utc: dt.datetime, equipment=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Planejador de foto lunar"))
        self.engine = engine
        self.start = start_utc
        self.equipment = equipment
        self.nights: list[moonlib.PhotoNight] = []

        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Próximas noites:")))
        self.spin = QSpinBox()
        self.spin.setRange(7, 60)
        self.spin.setValue(30)
        top.addWidget(self.spin)
        calc = QPushButton(self.tr("Calcular"))
        calc.clicked.connect(self.recompute)
        top.addWidget(calc)
        top.addStretch(1)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            self.tr("Noite"), self.tr("Fase"), self.tr("Ilum."), self.tr("Nasce (az.)"),
            self.tr("Põe (az.)"), self.tr("Alt. máx. no escuro"), self.tr("Indicada para")])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._go(r))

        self.chart = AltitudeChart()
        self.detail = QTextBrowser()

        mosaic = QGroupBox(self.tr("Mosaico do disco inteiro"))
        form = QFormLayout(mosaic)
        self.cmb_scope = QComboBox()
        self.cmb_cam = QComboBox()
        if equipment is not None:
            for t in equipment.items("telescopes"):
                self.cmb_scope.addItem(t.name, t)
            for c in equipment.items("cameras"):
                self.cmb_cam.addItem(c.name, c)
        self.cmb_scope.currentIndexChanged.connect(self._update_mosaic)
        self.cmb_cam.currentIndexChanged.connect(self._update_mosaic)
        self.lbl_mosaic = QLabel()
        self.lbl_mosaic.setWordWrap(True)
        form.addRow(self.tr("Telescópio"), self.cmb_scope)
        form.addRow(self.tr("Câmera"), self.cmb_cam)
        form.addRow(self.lbl_mosaic)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.chart)
        rl.addWidget(self.detail, 1)
        rl.addWidget(mosaic)
        go = QPushButton(self.tr("Levar o céu a esta noite"))
        go.clicked.connect(lambda: self._go(self.table.currentRow()))
        rl.addWidget(go)

        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        self.resize(1250, 680)
        self.recompute()

    def recompute(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.nights = moonlib.photo_nights(self.engine, self.start, self.spin.value())
        finally:
            QApplication.restoreOverrideCursor()
        self.table.setRowCount(len(self.nights))
        for r, n in enumerate(self.nights):
            def fmt(t, az):
                if t is None:
                    return "—"
                return f"{to_local(t):%H:%M} ({moonlib.azimuth_label(az)} {az:.0f}°)"
            cells = [
                f"{WEEKDAYS[n.date.weekday()]} {n.date:%d/%m}", n.phase_name, f"{n.illumination * 100:.0f}%",
                fmt(n.rise_utc, n.rise_az), fmt(n.set_utc, n.set_az),
                (f"{n.max_alt:.0f}° às {to_local(n.max_alt_utc):%H:%M}"
                 if n.max_alt_utc and n.max_alt > 0 else "—"),
                KIND_LABEL[n.kind],
            ]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if n.kind == "nenhuma":
                    it.setForeground(QColor(130, 130, 130))
                elif n.kind == "relevo" and c == 6:
                    it.setForeground(QColor(150, 220, 255))
                self.table.setItem(r, c, it)
        if self.nights:
            self.table.selectRow(0)
        self._update_mosaic()

    def _on_select(self) -> None:
        r = self.table.currentRow()
        if not (0 <= r < len(self.nights)):
            return
        n = self.nights[r]
        self.chart.set_night(n)
        feats = ", ".join(n.features) if n.features else "—"
        self.detail.setHtml(
            f"<p><b>{n.date:%d/%m/%Y}</b> · {n.phase_name}, "
            f"{n.illumination * 100:.0f}% iluminada</p>"
            f"<p>{n.advice}</p>"
            f"<p><b>No terminador:</b> {feats}</p>"
            "<p style='color:#9aa'>Foto da Lua nascendo sobre a paisagem: aponte para o "
            "azimute do nascer, de preferência um dia antes da cheia, quando ela sobe "
            "ainda com o céu claro.</p>")

    def _update_mosaic(self) -> None:
        scope, cam = self.cmb_scope.currentData(), self.cmb_cam.currentData()
        if scope is None or cam is None or not self.nights:
            self.lbl_mosaic.setText(self.tr("Cadastre telescópio e câmera em Campo de visão."))
            return
        from ..catalogs.equipment import compute_camera_fov

        shape = compute_camera_fov(scope, cam)
        fw, fh = math.degrees(shape.width), math.degrees(shape.height)
        r = max(self.table.currentRow(), 0)
        g = moonlib.geometry(self.engine, self.nights[r].max_alt_utc or self.start)
        diam = g.angular_diameter_arcmin / 60.0
        cols, rows = moonlib.mosaic_panels(diam * 1.05, fw, fh)
        if cols * rows == 1:
            text = (f"Campo de {num(fw, 2)}° × {num(fh, 2)}°: a Lua ({num(diam, 2)}°) "
                    "cabe num quadro só.")
        else:
            text = (f"Campo de {num(fw, 2)}° × {num(fh, 2)}°: {cols} × {rows} = "
                    f"{cols * rows} quadros para o disco de {num(diam, 2)}° "
                    "(20% de sobreposição).")
        self.lbl_mosaic.setText(text)

    def _go(self, row: int) -> None:
        if 0 <= row < len(self.nights):
            n = self.nights[row]
            self.nightChosen.emit(n.max_alt_utc or n.rise_utc or self.start)


class Lunar100Dialog(QDialog):
    """Planejar ▸ Lua ▸ Lunar 100."""

    showFeature = Signal(str)                   # nome da formação
    markObserved = Signal(str, str, str)

    def __init__(self, observed: set, parent=None) -> None:
        super().__init__(parent)
        from ..core.programs import lunar100

        self.setWindowTitle(self.tr("Lunar 100"))
        self.program = lunar100()
        self.observed = observed
        self.bar = QProgressBar()
        self.bar.setRange(0, len(self.program.items))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["nº", self.tr("Alvo"), self.tr("Tipo"), "✓"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.desc = QTextBrowser()
        self.btn_show = QPushButton(self.tr("Mostrar na Janela da Lua"))
        self.btn_show.clicked.connect(self._show)
        self.btn_mark = QPushButton(self.tr("✓ Marcar como observado"))
        self.btn_mark.clicked.connect(self._mark)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.desc, 1)
        row = QHBoxLayout()
        row.addWidget(self.btn_show)
        row.addWidget(self.btn_mark)
        rl.addLayout(row)
        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(self.tr(
            "Os cem alvos lunares de Charles Wood (Sky & Telescope, 2004), do mais fácil "
            "ao mais difícil. O progresso vem do seu diário de observação.")))
        lay.addWidget(self.bar)
        lay.addWidget(split, 1)
        self.resize(980, 640)
        self.reload(observed)

    def reload(self, observed: set) -> None:
        self.observed = observed
        done, total = self.program.progress(observed)
        self.bar.setValue(done)
        self.bar.setFormat(self.tr("%v de %m observados"))
        row = self.table.currentRow()
        self.table.setRowCount(len(self.program.items))
        for r, it in enumerate(self.program.items):
            ok = (it.kind, it.ident) in observed
            for c, text in enumerate([str(it.number), it.name, it.group, "✓" if ok else ""]):
                cell = QTableWidgetItem(text)
                if ok:
                    cell.setForeground(QColor(120, 210, 120))
                self.table.setItem(r, c, cell)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(3)
        self.table.selectRow(max(row, 0))

    def _current(self):
        r = self.table.currentRow()
        return self.program.items[r] if 0 <= r < len(self.program.items) else None

    def _on_select(self) -> None:
        it = self._current()
        if it is None:
            return
        where = ""
        if it.lat is not None:
            where = (f"<p style='color:#9aa'>{num(abs(it.lat))}°{'N' if it.lat >= 0 else 'S'}, "
                     f"{num(abs(it.lon))}°{'L' if it.lon >= 0 else 'O'}</p>")
        self.desc.setHtml(f"<h3>{it.number}. {it.name}</h3><p><i>{it.group}</i></p>"
                          f"{where}<p>{it.description}</p>")
        self.btn_show.setEnabled(it.lat is not None)
        ok = (it.kind, it.ident) in self.observed
        self.btn_mark.setText(self.tr("✓ Observado") if ok else self.tr("✓ Marcar como observado"))

    def _show(self) -> None:
        it = self._current()
        if it is not None:
            self.showFeature.emit(f"L100 {it.number}")

    def _mark(self) -> None:
        it = self._current()
        if it is not None:
            self.markObserved.emit(it.kind, it.ident, it.name)
