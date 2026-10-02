"""Janela de planejamento v2 (v0.15 T10) — substitui a de maratonas.

* **tabela** do roteiro com hora, designação e nome, nota da noite, janela
  útil, instrumento, Lua (vazia quando ela está abaixo do horizonte) e ✓
  de observado;
* **painel lateral** com a carta de localização, o gráfico da noite e as
  instruções do objeto selecionado — sem precisar abrir o PDF;
* **linha do tempo** (Gantt) com crepúsculos, Lua e uma barra por parada;
  arrastar a barra muda o horário e reagenda o resto;
* **barra de filtros** (instrumento, tipos, máximo, altitude mínima,
  distância da Lua) que recalcula o roteiro;
* botões por linha: ir para no mapa, **ir para na hora**, rastrear,
  observado, anotar, subir, descer, remover.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDoubleSpinBox, QFileDialog,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMainWindow, QMenu,
    QMessageBox, QProgressDialog, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from ..core.localtime import to_local
from ..core.observing import INSTRUMENT_LABEL, INSTRUMENT_ORDER
from .widgets.altitude_mini import AltitudeMini
from .widgets.timeline import NightTimeline, score_color

COLUMNS = ["#", "Hora", "Objeto", "Tipo", "Mag", "Alt", "Janela", "Nota",
           "Instrumento", "Constelação", "Lua", "✓"]
CLASS_CHOICES = [("GC", "Aglomerados globulares"), ("OC", "Aglomerados abertos"),
                 ("GAL", "Galáxias"), ("NEB", "Nebulosas"), ("PN", "Nebulosas planetárias"),
                 ("DARK", "Nebulosas escuras"), ("PLANET", "Planetas"), ("MOON", "Lua"),
                 ("STAR", "Estrelas")]


def _hm(value: dt.datetime | None) -> str:
    return to_local(value).strftime("%H:%M") if value else "—"


class PlanWindow(QMainWindow):
    """Roteiro interativo da noite."""

    gotoRequested = Signal(str, str)                  # (kind, ident)
    gotoAtTimeRequested = Signal(str, str, object)    # (kind, ident, quando)
    trackRequested = Signal(str, str)
    observedRequested = Signal(str, str, object)      # (kind, ident, quando)

    def __init__(self, plan, stars=None, const_lines=None, parent=None,
                 settings=None, recompute_cb=None, observed=None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.stars = stars
        self.const_lines = const_lines
        self.plan_settings = settings
        self._recompute_cb = recompute_cb
        self._observed = observed or (lambda: set())
        self._chart_cache: dict[str, QPixmap] = {}
        self.resize(1360, 860)

        self.head = QLabel()
        self.head.setTextFormat(Qt.RichText)
        self.head.setWordWrap(True)

        # --- filtros -----------------------------------------------------
        self.f_instr = QComboBox()
        self.f_instr.addItem(self.tr("Qualquer instrumento"), "")
        for key in INSTRUMENT_ORDER:
            self.f_instr.addItem(self.tr("até ") + INSTRUMENT_LABEL[key].lower(), key)
        self.f_types = QToolButton()
        self.f_types.setText(self.tr("Tipos"))
        self.f_types.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.f_types)
        self._type_acts = {}
        for key, label in CLASS_CHOICES:
            act = menu.addAction(self.tr(label))
            act.setCheckable(True)
            self._type_acts[key] = act
        self.f_types.setMenu(menu)
        self.f_max = QSpinBox()
        self.f_max.setRange(0, 200)
        self.f_max.setSpecialValueText(self.tr("sem limite"))
        self.f_max.setPrefix(self.tr("máx. "))
        self.f_alt = QSpinBox()
        self.f_alt.setRange(5, 60)
        self.f_alt.setSuffix("°")
        self.f_alt.setPrefix(self.tr("alt ≥ "))
        self.f_moon = QDoubleSpinBox()
        self.f_moon.setRange(0, 90)
        self.f_moon.setDecimals(0)
        self.f_moon.setSuffix("°")
        self.f_moon.setPrefix(self.tr("Lua ≥ "))
        self.f_moon.setSpecialValueText(self.tr("Lua: sem filtro"))
        self.btn_apply = QPushButton(self.tr("Recalcular"))
        filters = QHBoxLayout()
        filters.addWidget(QLabel(self.tr("Filtros:")))
        for wdg in (self.f_instr, self.f_types, self.f_max, self.f_alt, self.f_moon,
                    self.btn_apply):
            filters.addWidget(wdg)
        filters.addStretch(1)
        self.btn_apply.clicked.connect(self._apply_filters)
        self._load_filters()

        # --- tabela + botões ---------------------------------------------
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([self.tr(c) for c in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(lambda *_: self._emit("map"))

        self.buttons = {}
        row_bar = QHBoxLayout()
        for key, label in (("map", "Ir para no mapa"), ("time", "Ir para na hora"),
                           ("track", "Rastrear"), ("observed", "✓ Observado"),
                           ("note", "Anotar…"), ("up", "Subir"), ("down", "Descer"),
                           ("remove", "Remover")):
            b = QPushButton(self.tr(label))
            b.clicked.connect(lambda _c=False, k=key: self._row_action(k))
            row_bar.addWidget(b)
            self.buttons[key] = b
        row_bar.addStretch(1)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self.table, 1)
        left_lay.addLayout(row_bar)

        # --- painel do objeto ---------------------------------------------
        self.chart = QLabel()
        self.chart.setAlignment(Qt.AlignCenter)
        self.chart.setMinimumSize(300, 300)
        self.mini = AltitudeMini()
        self.details = QLabel(self.tr("Selecione uma linha do roteiro."))
        self.details.setTextFormat(Qt.RichText)
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        panel = QWidget()
        pl = QVBoxLayout(panel)
        pl.addWidget(self.chart)
        pl.addWidget(self.mini)
        pl.addWidget(self.details, 1)
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setWidget(panel)
        panel_scroll.setMinimumWidth(360)

        top_split = QSplitter(Qt.Horizontal)
        top_split.addWidget(left)
        top_split.addWidget(panel_scroll)
        top_split.setStretchFactor(0, 3)
        top_split.setStretchFactor(1, 2)

        self.timeline = NightTimeline()
        self.timeline.entryClicked.connect(self.table.selectRow)
        self.timeline.slotMoved.connect(self._on_slot_moved)
        tl_scroll = QScrollArea()
        tl_scroll.setWidgetResizable(True)
        tl_scroll.setWidget(self.timeline)

        v_split = QSplitter(Qt.Vertical)
        v_split.addWidget(top_split)
        v_split.addWidget(tl_scroll)
        v_split.setStretchFactor(0, 3)
        v_split.setStretchFactor(1, 2)
        v_split.setSizes([520, 300])
        top_split.setSizes([880, 460])

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(self.head)
        lay.addLayout(filters)
        lay.addWidget(v_split, 1)
        self.setCentralWidget(central)

        # --- menus --------------------------------------------------------
        m_file = self.menuBar().addMenu(self.tr("&Arquivo"))
        for text, slot, key in ((self.tr("Pré-visualizar o roteiro…"), self._preview_pdf,
                                 "Ctrl+Shift+V"),
                                (self.tr("Exportar PDF para impressão…"), self._export_pdf,
                                 "Ctrl+P")):
            act = QAction(text, self)
            act.setShortcut(key)
            act.triggered.connect(slot)
            m_file.addAction(act)
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

        self.refresh()

    # -- filtros -----------------------------------------------------------
    def _load_filters(self) -> None:
        from ..core.observing import PlanSettings

        s = self.plan_settings or PlanSettings()
        self.f_instr.setCurrentIndex(max(0, self.f_instr.findData(s.instrument_max)))
        for key, act in self._type_acts.items():
            act.setChecked(key in s.classes)
        self.f_max.setValue(s.max_objects)
        self.f_alt.setValue(int(round(s.min_altitude)))
        self.f_moon.setValue(s.moon_min_sep)
        enabled = self._recompute_cb is not None and self.plan.timed
        for wdg in (self.f_instr, self.f_types, self.f_max, self.f_alt, self.f_moon,
                    self.btn_apply):
            wdg.setEnabled(enabled)

    def _apply_filters(self) -> None:
        from ..core.observing import PlanSettings

        base = self.plan_settings or PlanSettings()
        classes = tuple(k for k, a in self._type_acts.items() if a.isChecked())
        new = dataclasses.replace(
            base, instrument_max=self.f_instr.currentData(), classes=classes,
            max_objects=self.f_max.value(), min_altitude=float(self.f_alt.value()),
            moon_min_sep=float(self.f_moon.value())).clamp()
        self._recompute(new)

    def _recompute(self, new_settings) -> None:
        if self._recompute_cb is None:
            return
        self.plan_settings = new_settings
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            plan = self._recompute_cb(new_settings)
        finally:
            QApplication.restoreOverrideCursor()
        if plan is not None:
            self.plan = plan
            self._chart_cache.clear()
            self.refresh()

    def _open_settings(self) -> None:
        from ..core.observing import PlanSettings
        from .plan_settings_dialog import PlanSettingsDialog

        dlg = PlanSettingsDialog(self.plan_settings or PlanSettings(), self)
        if dlg.exec():
            self._recompute(dlg.settings())
            self._load_filters()

    # -- conteúdo ----------------------------------------------------------
    def refresh(self, select: int | None = None) -> None:
        """Redesenha tabela, cabeçalho e linha do tempo a partir do plano."""
        plan = self.plan
        self.setWindowTitle(self.tr("{t} — planejamento").format(t=plan.title))
        self.head.setText(self._header_html())
        observed = self._observed()
        keep = self._current_index() if select is None else select
        self.table.blockSignals(True)
        self.table.setRowCount(len(plan.entries))
        for r, e in enumerate(plan.entries):
            window = (f"{_hm(e.window_start)}–{_hm(e.window_end)}"
                      if e.window_start and e.window_end else "—")
            cells = [
                str(r + 1), _hm(e.when_utc) if plan.timed else "—", e.label,
                e.type_label, "" if e.magnitude is None else f"{e.magnitude:.1f}",
                f"{e.altitude:.0f}°", window,
                str(e.score) if e.score else "—",
                INSTRUMENT_LABEL.get(e.instrument, e.instrument)
                + (" · difuso" if e.diffuse else ""),
                e.constellation,
                "" if e.moon_sep > 360 else f"{e.moon_sep:.0f}°",
                "✓" if (e.kind, e.ident) in observed else "",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if e.late:
                    item.setForeground(QColor(235, 90, 90))
                elif e.moon_warning:
                    item.setForeground(QColor(230, 150, 60))
                elif e.in_twilight:
                    item.setForeground(QColor(120, 170, 230))
                if c == 7 and e.score:
                    item.setForeground(score_color(e.score))
                    item.setToolTip(e.score_text)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.blockSignals(False)

        grid = None
        if plan.timed and plan.engine is not None and plan.night_start is not None:
            from ..core.visibility import night_grid

            grid = night_grid(plan.engine, plan.night_start)
        self.timeline.set_plan(plan if plan.timed else None, grid)
        self.timeline.setVisible(plan.timed)
        skipped = ", ".join(plan.skipped_names[:12])
        if len(plan.skipped_names) > 12:
            skipped += "…"
        self.statusBar().showMessage(self.tr(
            "{n} objetos ({m} min cada) · {s} fora de alcance · vermelho = fora da "
            "janela útil · laranja = Lua próxima · azul = céu ainda claro").format(
                n=len(plan.entries), m=plan.minutes_per_object, s=plan.skipped))
        self.statusBar().setToolTip(
            self.tr("Fora de alcance: {l}").format(l=skipped) if skipped else "")
        if 0 <= keep < len(plan.entries):
            self.table.selectRow(keep)
        elif plan.entries:
            self.table.selectRow(0)
        self._update_buttons()

    def _header_html(self) -> str:
        p = self.plan
        line = p.subtitle
        if p.timed and p.night_start and p.night_end:
            line = (f"{to_local(p.night_start):%d/%m/%Y} · janela "
                    f"{_hm(p.night_start)} – {_hm(p.night_end)}")
            if p.window_label:
                line += f" ({p.window_label})"
            line += f" · Lua {p.moon_illumination * 100:.0f}%"
        horizon = ""
        if getattr(p, "horizon", None) is not None:
            horizon = f" · horizonte: {p.horizon.name}"
        return (f"<h2 style='margin-bottom:2px'>{p.title}</h2>"
                f"<p style='color:#8a93a5'>{line} · {p.location}{horizon}</p>")

    def _current_index(self) -> int:
        model = self.table.selectionModel()
        rows = model.selectedRows() if model is not None else []
        return rows[0].row() if rows else -1

    def current_entry(self):
        i = self._current_index()
        return self.plan.entries[i] if 0 <= i < len(self.plan.entries) else None

    def _update_buttons(self) -> None:
        i = self._current_index()
        has = i >= 0
        timed = self.plan.timed and self.plan.engine is not None
        for b in self.buttons.values():
            b.setEnabled(has)
        self.buttons["time"].setEnabled(has and self.plan.timed)
        self.buttons["up"].setEnabled(has and timed and i > 0)
        self.buttons["down"].setEnabled(has and timed and i < len(self.plan.entries) - 1)
        self.buttons["remove"].setEnabled(has and timed)

    def _on_select(self) -> None:
        i = self._current_index()
        self.timeline.set_selected(i)
        self._update_buttons()
        e = self.current_entry()
        if e is None:
            return
        self._show_chart(e)
        self._show_mini(e)
        moon = ""
        if e.moon_sep <= 360:
            state = ("<span style='color:#e69640'>atrapalha</span>" if e.moon_warning
                     else "sem prejuízo")
            moon = f"<br><b>Lua:</b> a {e.moon_sep:.0f}° — {state}"
        if self.plan.timed:
            when = (f"<b>Horário:</b> {_hm(e.when_utc)} a {e.altitude:.0f}° "
                    f"(az {e.azimuth:.0f}°)")
        else:
            when = f"<b>Chega a</b> {e.altitude:.0f}°"
        vis = ""
        if e.rise_utc or e.set_utc or e.transit_utc:
            vis = (f"<br><b>Nasce · culmina · se põe:</b> {_hm(e.rise_utc)} · "
                   f"{_hm(e.transit_utc)} ({e.transit_alt:.0f}°) · {_hm(e.set_utc)}")
        if e.window_start and e.window_end:
            vis += f"<br><b>Janela útil:</b> {_hm(e.window_start)}–{_hm(e.window_end)}"
        if e.late:
            vis += " <span style='color:#eb5a5a'>(o horário caiu fora da janela)</span>"
        score = f"<br><b>Nota da noite:</b> {e.score_text}" if e.score_text else ""
        note = f"<br><b>Anotação:</b> {e.note}" if e.note else ""
        where = f" em {e.constellation}" if e.constellation else ""
        self.details.setText(
            f"<h3 style='margin-bottom:2px'>{e.label}</h3>"
            f"<p>{e.type_label}{where}<br>{when}{vis}{moon}{score}"
            f"<br><b>Instrumento:</b> {INSTRUMENT_LABEL.get(e.instrument, e.instrument)}"
            f"{note}</p><p><b>O que ver:</b> {e.what_to_see}<br><i>{e.binocular}</i></p>"
            f"<p><b>Como encontrar:</b> {e.how_to_find}</p>")

    def _show_chart(self, e) -> None:
        if self.stars is None or e.klass in ("PLANET", "MOON"):
            self.chart.clear()
            if e.klass in ("PLANET", "MOON"):
                self.chart.setText(self.tr("(sem carta para corpos do Sistema Solar)"))
            return
        key = f"{e.kind}:{e.ident}"
        pix = self._chart_cache.get(key)
        if pix is None:
            from .finderchart import render_finder_chart

            pix = QPixmap.fromImage(render_finder_chart(e, self.stars, self.const_lines,
                                                        size_px=360))
            self._chart_cache[key] = pix
        self.chart.setPixmap(pix)

    def _show_mini(self, e) -> None:
        plan = self.plan
        if not plan.timed or plan.engine is None or plan.night_start is None:
            self.mini.hide()
            return
        from ..core.visibility import Target, compute_visibility

        target = (Target(body=e.name) if e.klass in ("PLANET", "MOON")
                  else Target.from_radec(e.ra, e.dec))
        s = plan.settings
        vis = compute_visibility(plan.engine, target, plan.night_start,
                                 s.min_altitude if s else 20.0, plan.horizon,
                                 refine=False)
        self.mini.set_visibility(vis, plan.horizon, e.when_utc)
        self.mini.show()

    # -- ações por linha ---------------------------------------------------
    def _emit(self, kind: str) -> None:
        e = self.current_entry()
        if e is None:
            return
        if kind == "map":
            self.gotoRequested.emit(e.kind, e.ident)
        elif kind == "time":
            self.gotoAtTimeRequested.emit(e.kind, e.ident, e.when_utc)
        elif kind == "track":
            self.trackRequested.emit(e.kind, e.ident)
        elif kind == "observed":
            self.observedRequested.emit(e.kind, e.ident, e.when_utc)

    def _row_action(self, key: str) -> None:
        i = self._current_index()
        if i < 0:
            return
        if key in ("map", "time", "track", "observed"):
            self._emit(key)
        elif key == "note":
            e = self.plan.entries[i]
            text, ok = QInputDialog.getText(self, self.tr("Anotação"), e.label,
                                            text=e.note)
            if ok:
                e.note = text
                self.refresh(i)
        elif key == "up" and i > 0:
            self.plan.move(i, i - 1)
            self.refresh(i - 1)
        elif key == "down" and i < len(self.plan.entries) - 1:
            self.plan.move(i, i + 1)
            self.refresh(i + 1)
        elif key == "remove":
            self.plan.remove(i)
            self.refresh(min(i, len(self.plan.entries) - 1))

    def _on_slot_moved(self, index: int, when) -> None:
        entry = self.plan.entries[index]
        self.plan.set_slot(index, when)
        self.refresh(self.plan.entries.index(entry))

    def mark_observed_refresh(self) -> None:
        """Chamado pelo dono depois de registrar no diário."""
        self.refresh(self._current_index())

    # -- PDF -------------------------------------------------------------------
    def write_pdf(self, path: str, progress=None) -> bool:
        from .plan_pdf import write_plan_pdf

        return write_plan_pdf(path, self.plan, self.stars, self.const_lines, progress)

    def _progress(self, text: str) -> QProgressDialog:
        dlg = QProgressDialog(text, self.tr("Cancelar"), 0, len(self.plan.entries), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(400)
        return dlg

    def _preview_pdf(self) -> None:
        import tempfile
        from pathlib import Path

        from .pdf_preview import PdfPreviewWindow

        tmp = Path(tempfile.gettempdir()) / "carina_preview_plano.pdf"
        progress = self._progress(self.tr("Gerando a pré-visualização…"))
        try:
            done = self.write_pdf(str(tmp), progress)
        except Exception as exc:  # noqa: BLE001
            progress.close()
            QMessageBox.warning(self, "Carina", self.tr(
                "Falha ao gerar a pré-visualização: {e}").format(e=exc))
            return
        progress.close()
        if done:
            win = PdfPreviewWindow(str(tmp), self.plan.title, self)
            win.setAttribute(Qt.WA_DeleteOnClose, True)
            win.exportRequested.connect(self._export_pdf)
            self._preview_win = win
            win.show()

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar roteiro"),
            f"{self.plan.title.lower().replace(' ', '_')}.pdf", "PDF (*.pdf)")
        if not path:
            return
        progress = self._progress(self.tr("Gerando cartas de localização…"))
        try:
            done = self.write_pdf(path, progress)
        except Exception as exc:  # noqa: BLE001
            progress.close()
            QMessageBox.warning(self, "Carina", self.tr(
                "Falha ao exportar: {e}").format(e=exc))
            return
        progress.close()
        if done:
            self.statusBar().showMessage(self.tr("PDF gerado: {p}").format(p=path), 8000)
