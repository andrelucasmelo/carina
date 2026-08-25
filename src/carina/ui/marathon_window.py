"""Janela de planejamento de observação (maratonas).

Exibe o roteiro em ordem cronológica — horário sugerido, altitude,
distância à Lua, instruções de observação — e exporta um PDF de campo com
duas seções:

1. um **checklist compacto** (uma linha por objeto, com caixa para marcar);
2. um **cartão por objeto** com as instruções completas e uma **carta de
   localização** desenhada no estilo do modo de impressão (estrelas, seta
   da estrela-guia até o alvo, escala e orientação).

O texto do PDF é sempre MEDIDO antes de desenhado (``boundingRect``) e o
cursor vertical avança pela altura real — foi assim que o problema de
linhas sobrepostas da primeira versão foi eliminado. Gastar folhas não é
problema; sobrepor texto é.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QMarginsF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHeaderView, QLabel,
    QMainWindow, QMessageBox, QProgressDialog, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.localtime import to_local
from ..core.observing import INSTRUMENT_LABEL
from .pdf_preview import PdfPreviewWindow

COLUMNS = ["Hora", "Objeto", "Nome", "Tipo", "Mag", "Tam", "Alt",
           "Instrumento", "Constelação", "Lua"]


def _hm(value: dt.datetime | None) -> str:
    return to_local(value).strftime("%H:%M") if value else "—"


class MarathonWindow(QMainWindow):
    """Roteiro interativo, configuração, pré-visualização e PDF de campo.

    ``recompute_cb`` (opcional) é chamado com a configuração nova quando o
    usuário usa Configurar → o chamador refaz o plano e devolve um novo
    :class:`ObservingPlan`, que substitui o exibido sem fechar a janela.
    """

    gotoRequested = Signal(str)

    def __init__(self, plan, stars=None, const_lines=None, parent=None,
                 settings=None, recompute_cb=None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.stars = stars              # catálogo p/ cartas de localização
        self.const_lines = const_lines  # linhas de constelação p/ cartas
        self.plan_settings = settings
        self._recompute_cb = recompute_cb
        self.setWindowTitle(
            self.tr("{t} — planejamento").format(t=plan.title)
        )
        self.resize(1240, 780)

        central = QWidget()
        layout = QVBoxLayout(central)

        self.head = QLabel(self._header_html())
        self.head.setTextFormat(Qt.RichText)
        self.head.setWordWrap(True)
        layout.addWidget(self.head)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            COLUMNS.index("Constelação"), QHeaderView.Stretch
        )
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.itemDoubleClicked.connect(self._goto)
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
        act_preview = QAction(self.tr("Pré-visualizar o roteiro…"), self)
        act_preview.setShortcut("Ctrl+Shift+V")
        act_preview.triggered.connect(self._preview_pdf)
        m_file.addAction(act_preview)
        act_pdf = QAction(self.tr("Exportar PDF para impressão…"), self)
        act_pdf.setShortcut("Ctrl+P")
        act_pdf.triggered.connect(self._export_pdf)
        m_file.addAction(act_pdf)
        m_file.addSeparator()
        act_close = QAction(self.tr("Fechar"), self)
        act_close.setShortcut("Ctrl+W")
        act_close.triggered.connect(self.close)
        m_file.addAction(act_close)

        m_cfg = self.menuBar().addMenu(self.tr("&Configurar"))
        act_cfg = QAction(self.tr("Configurar planejamento…"), self)
        act_cfg.setShortcut("Ctrl+,")
        act_cfg.triggered.connect(self._open_settings)
        act_cfg.setEnabled(recompute_cb is not None)
        m_cfg.addAction(act_cfg)

        self._fill_table()

    # ------------------------------------------------------------------
    def _fill_table(self) -> None:
        """(Re)preenche a lista a partir de ``self.plan``."""
        plan = self.plan
        timed = plan.timed
        self.table.setRowCount(len(plan.entries))
        for r, e in enumerate(plan.entries):
            cells = [
                _hm(e.when_utc) if timed else "—",
                e.catalog_id, e.common, e.type_label,
                "" if e.magnitude is None else f"{e.magnitude:.1f}",
                "" if not e.size_arcmin else f"{e.size_arcmin:.0f}'",
                f"{e.altitude:.0f}°",
                INSTRUMENT_LABEL.get(e.instrument, e.instrument),
                e.constellation,
                "—" if e.moon_sep > 360 else f"{e.moon_sep:.0f}°",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if e.moon_warning:
                    item.setForeground(QColor(230, 150, 60))
                elif e.in_twilight:
                    # ainda com o céu claro: só entrou por ser brilhante
                    item.setForeground(QColor(120, 170, 230))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.head.setText(self._header_html())
        self.statusBar().showMessage(self.tr(
            "{n} objetos no roteiro ({m} min cada) · {s} fora de alcance · "
            "duplo clique leva ao objeto no mapa"
        ).format(n=len(plan.entries), m=plan.minutes_per_object,
                 s=plan.skipped))

    def _header_html(self) -> str:
        p = self.plan
        line = ""
        if p.timed and p.night_start and p.night_end:
            line = (f"{to_local(p.night_start):%d/%m/%Y} · janela "
                    f"{_hm(p.night_start)} – {_hm(p.night_end)}")
            if p.window_label:
                line += f" ({p.window_label})"
        elif p.subtitle:
            line = p.subtitle
        extra = ""
        if p.timed:
            extra = (
                f"<br>Lua {p.moon_illumination * 100:.0f}% iluminada — em "
                f"laranja, objetos perto dela; em azul, os agendados com o "
                f"céu ainda claro (só entram os bem brilhantes)."
            )
        elif p.subtitle:
            extra = ("<br>Objetos bem posicionados durante todo o período — "
                     "a coluna Instrumento diz com o que vale a pena tentar.")
        return (
            f"<h2 style='margin-bottom:2px'>{p.title}</h2>"
            f"<p style='color:#8a93a5'>{line} · {p.location}{extra}</p>"
        )

    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        """Configura e recalcula o plano sem fechar a janela."""
        from .plan_settings_dialog import PlanSettingsDialog

        from ..core.observing import PlanSettings

        dlg = PlanSettingsDialog(self.plan_settings or PlanSettings(), self)
        if not dlg.exec():
            return
        self.plan_settings = dlg.settings()
        if self._recompute_cb is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            new_plan = self._recompute_cb(self.plan_settings)
        finally:
            QApplication.restoreOverrideCursor()
        if new_plan is not None:
            self.plan = new_plan
            self._fill_table()
            self.details.setText(self.tr(
                "Roteiro recalculado com a nova configuração."
            ))

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
        if self.plan.timed:
            quando = (f"<b>Melhor horário:</b> {_hm(e.when_utc)} a "
                      f"{e.altitude:.0f}° de altitude")
            if e.in_twilight:
                quando += ("  <span style='color:#78aae6'>(céu ainda "
                           "claro — só por ser brilhante)</span>")
        else:
            quando = f"<b>Chega a</b> {e.altitude:.0f}° de altitude"
        self.details.setText(
            f"<h3 style='margin-bottom:2px'>{e.catalog_id}"
            f"{(' — ' + e.common) if e.common and e.common != e.catalog_id else ''}</h3>"
            f"<p>{quando}"
            f"{(', ' + e.constellation) if e.constellation else ''}"
            f"{moon}<br><b>Instrumento:</b> "
            f"{INSTRUMENT_LABEL.get(e.instrument, e.instrument)}"
            f"{('  ·  ' + e.note) if e.note else ''}</p>"
            f"<p><b>O que ver:</b> {e.what_to_see}<br>"
            f"<b>{e.binocular}</b></p>"
            f"<p><b>Como encontrar:</b> {e.how_to_find}</p>"
        )

    def _goto(self) -> None:
        e = self._current_entry()
        if e is not None:
            self.gotoRequested.emit(e.name)

    # ------------------------------------------------------------------
    # Pré-visualização
    # ------------------------------------------------------------------
    def _preview_pdf(self) -> None:
        """Gera o PDF num arquivo temporário e o exibe para conferência.

        Pré-visualizar é o próprio arquivo final aberto num visualizador —
        nada de uma renderização paralela que poderia divergir do que sai
        na impressora.
        """
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.gettempdir()) / "carina_preview_plano.pdf"
        progress = QProgressDialog(
            self.tr("Gerando a pré-visualização…"), self.tr("Cancelar"),
            0, len(self.plan.entries), self,
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(400)
        try:
            done = self._write_pdf(str(tmp), progress)
        except Exception as exc:  # noqa: BLE001
            progress.close()
            QMessageBox.warning(
                self, "Carina",
                self.tr("Falha ao gerar a pré-visualização: {e}").format(e=exc),
            )
            return
        progress.close()
        if not done:
            return
        win = PdfPreviewWindow(str(tmp), self.plan.title, self)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.exportRequested.connect(self._export_pdf)
        self._preview_win = win
        win.show()

    # ------------------------------------------------------------------
    # Exportação do PDF de campo
    # ------------------------------------------------------------------
    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar roteiro"),
            f"{self.plan.title.lower().replace(' ', '_')}.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        progress = QProgressDialog(
            self.tr("Gerando cartas de localização…"), self.tr("Cancelar"),
            0, len(self.plan.entries), self,
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(400)
        try:
            done = self._write_pdf(path, progress)
        except Exception as exc:  # noqa: BLE001
            progress.close()
            QMessageBox.warning(
                self, "Carina",
                self.tr("Falha ao exportar: {e}").format(e=exc),
            )
            return
        progress.close()
        if done:
            self.statusBar().showMessage(
                self.tr("PDF gerado: {p}").format(p=path), 8000
            )

    def _write_pdf(self, path: str, progress=None) -> bool:
        """Desenha o PDF. Retorna False se o usuário cancelou no meio."""
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageOrientation(QPageLayout.Portrait)
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
        writer.setResolution(300)
        writer.setTitle(self.plan.title)

        p = QPainter(writer)
        width = writer.width()
        height = writer.height()
        margin = 30
        y = margin

        f_title = QFont("Segoe UI", 18, QFont.Bold)
        f_head = QFont("Segoe UI", 12, QFont.Bold)
        f_meta = QFont("Segoe UI", 9)
        f_body = QFont("Segoe UI", 9)
        f_row = QFont("Segoe UI", 8)

        def ensure(space: float) -> None:
            """Quebra de página quando o próximo bloco não couber inteiro."""
            nonlocal y
            if y + space > height - margin:
                writer.newPage()
                y = margin

        def paragraph(text: str, x: float, wrap_w: float,
                      font: QFont, advance: bool = True) -> float:
            """Mede, desenha e devolve a ALTURA REAL do parágrafo.

            Medir antes de desenhar (e avançar o cursor pela altura medida)
            é o que garante que nenhuma linha sobreponha a seguinte.
            """
            nonlocal y
            p.setFont(font)
            probe = QRectF(x, 0, wrap_w, 100000)
            used = p.boundingRect(probe, Qt.TextWordWrap, text)
            rect = QRectF(x, y, wrap_w, used.height())
            p.drawText(rect, Qt.TextWordWrap, text)
            if advance:
                y += used.height() + 8
            return used.height()

        # --- cabeçalho ---------------------------------------------------
        plan = self.plan
        p.setPen(QColor(0, 0, 0))
        if plan.timed and plan.night_start and plan.night_end:
            periodo = (f"{to_local(plan.night_start):%d/%m/%Y} · "
                       f"{_hm(plan.night_start)} – {_hm(plan.night_end)}")
            if plan.window_label:
                periodo += f" ({plan.window_label})"
            resumo = (
                f"Lua {plan.moon_illumination * 100:.0f}% iluminada · "
                f"{len(plan.entries)} objetos · "
                f"{plan.minutes_per_object} min por objeto"
            )
        else:
            periodo = plan.subtitle
            resumo = (f"{len(plan.entries)} objetos bem posicionados "
                      f"durante todo o período")
        paragraph(plan.title, margin, width - 2 * margin, f_title)
        paragraph(
            f"{periodo} · {plan.location}\n{resumo} · "
            f"gerado pelo Carina em {dt.datetime.now():%d/%m/%Y %H:%M}",
            margin, width - 2 * margin, f_meta,
        )
        y += 10

        # --- seção 1: checklist compacto ---------------------------------
        paragraph("Checklist" if not plan.timed else "Checklist da noite",
                  margin, width - 2 * margin, f_head)
        p.setFont(f_row)
        row_h = p.boundingRect(
            QRectF(0, 0, 1000, 1000), 0, "Ag"
        ).height() + 10
        box = row_h * 0.55
        for i, e in enumerate(plan.entries, 1):
            ensure(row_h)
            p.setPen(QColor(90, 90, 90))
            p.drawRect(QRectF(margin, y + (row_h - box) / 2 - 2, box, box))
            p.setPen(QColor(0, 0, 0))
            hora = f"{_hm(e.when_utc)}  " if plan.timed else ""
            label = f"{i:>3}.  {hora}{e.catalog_id}"
            if e.common and e.common != e.catalog_id:
                label += f" — {e.common}"
            extra = (f"{e.type_label} · alt {e.altitude:.0f}° · "
                     f"{INSTRUMENT_LABEL.get(e.instrument, '')}")
            if e.constellation:
                extra += f" · {e.constellation}"
            if e.moon_warning:
                extra += " · LUA PRÓXIMA"
            if e.in_twilight:
                extra += " · CÉU CLARO"
            p.drawText(QRectF(margin + box + 14, y, width * 0.52, row_h),
                       Qt.AlignVCenter, label)
            p.setPen(QColor(110, 110, 110))
            p.drawText(
                QRectF(margin + box + 14 + width * 0.52, y,
                       width - 2 * margin - box - 14 - width * 0.52, row_h),
                Qt.AlignVCenter, extra,
            )
            y += row_h
        y += 20

        # --- seção 2: um cartão por objeto, com carta de localização -----
        chart_px = 0
        chart_img = None
        if self.stars is not None:
            from .finderchart import render_finder_chart

            # ~62 mm a 300 dpi; a carta fica à esquerda, o texto à direita
            chart_px = int(62 / 25.4 * 300)

        for i, e in enumerate(self.plan.entries, 1):
            if progress is not None:
                progress.setValue(i - 1)
                QApplication.processEvents()
                if progress.wasCanceled():
                    p.end()
                    return False

            if self.stars is not None:
                chart_img = render_finder_chart(e, self.stars,
                                                self.const_lines)

            # mede os textos antes de reservar espaço para o cartão
            text_x = margin + (chart_px + 24 if chart_img else 0)
            text_w = width - margin - text_x
            hora = f"{_hm(e.when_utc)} — " if plan.timed else ""
            title = f"{i}. {hora}{e.catalog_id}"
            if e.common and e.common != e.catalog_id:
                title += f" ({e.common})"
            meta = f"{e.type_label}"
            if e.constellation:
                meta += f" em {e.constellation}"
            meta += f" · alt {e.altitude:.0f}° · az {e.azimuth:.0f}°"
            if e.magnitude is not None:
                meta += f" · mag {e.magnitude:.1f}"
            if e.size_arcmin:
                meta += f" · {e.size_arcmin:.0f}'"
            if e.moon_sep <= 360:
                meta += f" · Lua a {e.moon_sep:.0f}°"
                if e.moon_warning:
                    meta += " (ATRAPALHA)"
            instrumento = (
                f"Instrumento:  {INSTRUMENT_LABEL.get(e.instrument, '')}"
            )
            if e.in_twilight:
                instrumento += ("   ·   Céu ainda claro neste horário: "
                                "só entrou por ser bem brilhante.")
            if e.note:
                instrumento += f"   ·   {e.note}"
            blocks = [
                (title, f_head), (meta, f_meta), (instrumento, f_meta),
                (f"O que ver:  {e.what_to_see}", f_body),
                (e.binocular, f_body),
                (f"Como encontrar:  {e.how_to_find}", f_body),
            ]
            total_text = 0.0
            for text, font in blocks:
                p.setFont(font)
                used = p.boundingRect(
                    QRectF(0, 0, text_w, 100000), Qt.TextWordWrap, text
                )
                total_text += used.height() + 8
            card_h = max(total_text, chart_px if chart_img else 0) + 26

            ensure(card_h)
            top = y
            if chart_img is not None:
                p.drawImage(
                    QRectF(margin, top, chart_px, chart_px), chart_img
                )
            for text, font in blocks:
                paragraph(text, text_x, text_w, font)
            y = max(y, top + (chart_px if chart_img else 0) + 8)
            p.setPen(QColor(190, 190, 190))
            p.drawLine(QRectF(margin, y, width - 2 * margin, 0).topLeft(),
                       QRectF(margin, y, width - 2 * margin, 0).topRight())
            p.setPen(QColor(0, 0, 0))
            y += 18

        if progress is not None:
            progress.setValue(len(self.plan.entries))
        p.end()
        return True
