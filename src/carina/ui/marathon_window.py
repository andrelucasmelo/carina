"""Janela de planejamento de observação: maratonas Messier e Caldwell.

Mostra o roteiro em ordem cronológica com horário sugerido, altitude,
distância à Lua, o que se espera ver ao binóculo e ao telescópio e como
localizar cada objeto. Exporta um PDF pronto para levar ao campo.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QMarginsF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

COLUMNS = ["Hora", "Objeto", "Nome", "Tipo", "Mag", "Tam", "Alt",
           "Constelação", "Lua"]


def _hm(value: dt.datetime | None) -> str:
    return value.astimezone().strftime("%H:%M") if value else "—"


class MarathonWindow(QMainWindow):
    gotoRequested = Signal(str)

    def __init__(self, plan, parent=None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle(
            self.tr("{t} — planejamento").format(t=plan.title)
        )
        self.resize(1180, 760)

        central = QWidget()
        layout = QVBoxLayout(central)

        head = QLabel(self._header_html())
        head.setTextFormat(Qt.RichText)
        head.setWordWrap(True)
        layout.addWidget(head)

        self.table = QTableWidget(len(plan.entries), len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            7, QHeaderView.Stretch
        )
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.itemDoubleClicked.connect(self._goto)
        for r, e in enumerate(plan.entries):
            cells = [
                _hm(e.when_utc), e.catalog_id, e.common,
                e.type_label,
                "" if e.magnitude is None else f"{e.magnitude:.1f}",
                "" if not e.size_arcmin else f"{e.size_arcmin:.0f}'",
                f"{e.altitude:.0f}°", e.constellation,
                "—" if e.moon_sep > 360 else f"{e.moon_sep:.0f}°",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if e.moon_warning:
                    item.setForeground(QColor(230, 150, 60))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 3)

        self.details = QLabel(self.tr(
            "Selecione uma linha para ver as instruções de observação."
        ))
        self.details.setTextFormat(Qt.RichText)
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignTop)
        self.details.setMinimumHeight(120)
        layout.addWidget(self.details, 1)
        self.setCentralWidget(central)

        m_file = self.menuBar().addMenu(self.tr("&Arquivo"))
        act_pdf = QAction(self.tr("Exportar PDF para impressão…"), self)
        act_pdf.setShortcut("Ctrl+P")
        act_pdf.triggered.connect(self._export_pdf)
        m_file.addAction(act_pdf)
        m_file.addSeparator()
        act_close = QAction(self.tr("Fechar"), self)
        act_close.setShortcut("Ctrl+W")
        act_close.triggered.connect(self.close)
        m_file.addAction(act_close)

        self.statusBar().showMessage(self.tr(
            "{n} objetos no roteiro · {s} fora de alcance nesta noite · "
            "duplo clique leva ao objeto no mapa"
        ).format(n=len(plan.entries), s=plan.skipped))

    # ------------------------------------------------------------------
    def _header_html(self) -> str:
        p = self.plan
        night = ""
        if p.night_start and p.night_end:
            night = (f"{p.night_start.astimezone():%d/%m/%Y} · janela de "
                     f"observação {_hm(p.night_start)} – {_hm(p.night_end)}")
        return (
            f"<h2 style='margin-bottom:2px'>{p.title}</h2>"
            f"<p style='color:#8a93a5'>{night} · {p.location}<br>"
            f"Lua {p.moon_illumination * 100:.0f}% iluminada — objetos "
            f"marcados em laranja estão perto dela e ficam prejudicados.</p>"
        )

    def _current_entry(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.plan.entries[rows[0].row()]

    def _show_details(self) -> None:
        e = self._current_entry()
        if e is None:
            return
        moon = (
            "" if e.moon_sep > 360 else
            f"<br><b>Lua:</b> a {e.moon_sep:.0f}° "
            + ("— <span style='color:#e69640'>atrapalha</span>"
               if e.moon_warning else "— sem prejuízo")
        )
        self.details.setText(
            f"<h3 style='margin-bottom:2px'>{e.catalog_id}"
            f"{(' — ' + e.common) if e.common else ''}</h3>"
            f"<p><b>Melhor horário:</b> {_hm(e.when_utc)} a "
            f"{e.altitude:.0f}° de altitude, {e.constellation}"
            f"{moon}</p>"
            f"<p><b>O que ver:</b> {e.what_to_see}<br>"
            f"<b>{e.binocular}</b></p>"
            f"<p><b>Como encontrar:</b> {e.how_to_find}</p>"
        )

    def _goto(self) -> None:
        e = self._current_entry()
        if e is not None:
            self.gotoRequested.emit(e.name)

    # ------------------------------------------------------------------
    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar roteiro"),
            f"{self.plan.title.lower().replace(' ', '_')}.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            self._write_pdf(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, "Carina",
                self.tr("Falha ao exportar: {e}").format(e=exc),
            )
            return
        self.statusBar().showMessage(
            self.tr("PDF gerado: {p}").format(p=path), 8000
        )

    def _write_pdf(self, path: str) -> None:
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageOrientation(QPageLayout.Portrait)
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
        writer.setResolution(300)
        writer.setTitle(self.plan.title)

        p = QPainter(writer)
        width = writer.width()
        height = writer.height()
        margin = 40
        y = margin
        line_h = 46

        def new_page_if_needed(space: int) -> None:
            nonlocal y
            if y + space > height - margin:
                writer.newPage()
                y = margin

        # cabeçalho
        p.setFont(QFont("Segoe UI", 18, QFont.Bold))
        p.setPen(QColor(0, 0, 0))
        p.drawText(margin, y + 40, self.plan.title)
        y += 70
        p.setFont(QFont("Segoe UI", 10))
        night = ""
        if self.plan.night_start and self.plan.night_end:
            night = (f"{self.plan.night_start.astimezone():%d/%m/%Y} · "
                     f"{_hm(self.plan.night_start)} – "
                     f"{_hm(self.plan.night_end)}")
        p.drawText(margin, y, f"{night} · {self.plan.location}")
        y += 34
        p.drawText(
            margin, y,
            f"Lua {self.plan.moon_illumination * 100:.0f}% iluminada · "
            f"{len(self.plan.entries)} objetos · gerado por Carina em "
            f"{dt.datetime.now():%d/%m/%Y %H:%M}"
        )
        y += 46

        for i, e in enumerate(self.plan.entries, 1):
            new_page_if_needed(int(line_h * 4.6))
            p.setFont(QFont("Segoe UI", 12, QFont.Bold))
            title = f"{i:>3}. {_hm(e.when_utc)}  —  {e.catalog_id}"
            if e.common:
                title += f" ({e.common})"
            p.drawText(margin, y, title)
            y += line_h
            p.setFont(QFont("Segoe UI", 9))
            details = (
                f"{e.type_label} em {e.constellation} · "
                f"alt {e.altitude:.0f}° · az {e.azimuth:.0f}°"
            )
            if e.magnitude is not None:
                details += f" · mag {e.magnitude:.1f}"
            if e.size_arcmin:
                details += f" · {e.size_arcmin:.0f}'"
            if e.moon_sep <= 360:
                details += f" · Lua a {e.moon_sep:.0f}°"
                if e.moon_warning:
                    details += " (atrapalha)"
            p.drawText(margin + 30, y, details)
            y += line_h

            for label, text in (("Ver:", e.what_to_see),
                                ("", e.binocular),
                                ("Achar:", e.how_to_find)):
                rect = QRectF(margin + 30, y - 24,
                              width - 2 * margin - 30, line_h * 2.2)
                content = f"{label} {text}".strip()
                p.drawText(rect, Qt.TextWordWrap, content)
                used = p.boundingRect(rect, Qt.TextWordWrap, content)
                y += max(line_h, int(used.height()) + 6)
            y += 10
            p.setPen(QColor(190, 190, 190))
            p.drawLine(margin, y, width - margin, y)
            p.setPen(QColor(0, 0, 0))
            y += 24
        p.end()
