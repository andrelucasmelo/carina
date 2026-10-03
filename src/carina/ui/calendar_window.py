"""Calendário do céu (v0.17 T7) e o cartão "Hoje no céu".

A janela mostra o mês em grade — cada dia com os eventos em cores por
categoria — ou o ano inteiro em lista (só os destaques, por padrão). Os
filtros escolhem as categorias; um evento pode virar **lembrete** (o
programa avisa ao abrir, na véspera) ou ir para a agenda do celular pelo
``.ics``. "Ir para" leva o céu ao instante do evento.
"""

from __future__ import annotations

import calendar
import datetime as dt

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QSplitter, QTableWidget,
                               QTextBrowser, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core import events as ev
from ..core.localtime import to_local

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
STARS = {1: "", 2: "★ ", 3: "★★ "}


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


class CalendarWindow(QMainWindow):
    """Planejar ▸ Calendário do céu."""

    gotoEvent = Signal(object)            # SkyEvent

    def __init__(self, engine, today: dt.date, location: str = "", parent=None,
                 settings=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Calendário do céu"))
        self.engine = engine
        self.location = location
        self.settings = settings
        self.year, self.month = today.year, today.month
        self.today = today
        self.selected_day: dt.date | None = today
        self.events: list[ev.SkyEvent] = []
        self.mode = "month"

        top = QHBoxLayout()
        prev = QPushButton("◀")
        prev.clicked.connect(lambda: self.shift(-1))
        nxt = QPushButton("▶")
        nxt.clicked.connect(lambda: self.shift(1))
        self.lbl = QLabel()
        self.lbl.setMinimumWidth(170)
        self.lbl.setAlignment(Qt.AlignCenter)
        f = self.lbl.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        f.setBold(True)
        self.lbl.setFont(f)
        btn_today = QPushButton(self.tr("Hoje"))
        btn_today.clicked.connect(self.go_today)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem(self.tr("Mês"), "month")
        self.cmb_mode.addItem(self.tr("Ano (lista)"), "year")
        self.cmb_mode.currentIndexChanged.connect(self._mode_changed)
        top.addWidget(prev)
        top.addWidget(self.lbl)
        top.addWidget(nxt)
        top.addWidget(btn_today)
        top.addWidget(self.cmb_mode)
        top.addStretch(1)
        self.chk_top = QCheckBox(self.tr("Só destaques"))
        self.chk_top.toggled.connect(self._refilter)
        top.addWidget(self.chk_top)
        export = QPushButton(self.tr("Exportar .ics…"))
        export.clicked.connect(self.export_ics)
        top.addWidget(export)

        filt = QHBoxLayout()
        filt.addWidget(QLabel(self.tr("Mostrar:")))
        self.chk_cat: dict[str, QCheckBox] = {}
        saved = None
        if settings is not None:
            saved = settings.value("calendar/categories", "", str)
        on = set(saved.split(",")) if saved else set(ev.CATEGORIES)
        for key, (label, rgb) in ev.CATEGORIES.items():
            chk = QCheckBox(self.tr(label))
            chk.setChecked(key in on)
            chk.setStyleSheet(f"QCheckBox {{ color: {_hex(rgb)}; }}")
            chk.toggled.connect(self._cats_changed)
            self.chk_cat[key] = chk
            filt.addWidget(chk)
        filt.addStretch(1)

        self.grid = QTableWidget(6, 7)
        self.grid.setHorizontalHeaderLabels([self.tr(d) for d in WEEKDAYS])
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.grid.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.grid.setEditTriggers(QTableWidget.NoEditTriggers)
        self.grid.setSelectionMode(QTableWidget.SingleSelection)
        self.grid.cellClicked.connect(self._cell_clicked)
        self.year_list = QTreeWidget()
        self.year_list.setHeaderLabels([self.tr("Data"), self.tr("Evento")])
        self.year_list.setRootIsDecorated(True)
        self.year_list.itemClicked.connect(self._year_clicked)
        self.year_list.hide()

        self.day_list = QTreeWidget()
        self.day_list.setHeaderLabels([self.tr("Hora"), self.tr("Evento")])
        self.day_list.setRootIsDecorated(False)
        self.day_list.itemSelectionChanged.connect(self._event_selected)
        self.detail = QTextBrowser()
        self.btn_remind = QPushButton(self.tr("🔔 Lembrar-me"))
        self.btn_remind.setCheckable(True)
        self.btn_remind.clicked.connect(self._toggle_reminder)
        self.btn_go = QPushButton(self.tr("Ir para"))
        self.btn_go.clicked.connect(self._goto)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.lbl_day = QLabel()
        rl.addWidget(self.lbl_day)
        rl.addWidget(self.day_list, 2)
        rl.addWidget(self.detail, 1)
        row = QHBoxLayout()
        row.addWidget(self.btn_remind)
        row.addWidget(self.btn_go)
        rl.addLayout(row)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.grid)
        ll.addWidget(self.year_list)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addLayout(filt)
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self.resize(1300, 760)
        self.reload()

    # -- dados --------------------------------------------------------------
    def categories(self) -> list[str]:
        return [k for k, c in self.chk_cat.items() if c.isChecked()]

    def _period(self) -> tuple[dt.datetime, dt.datetime]:
        if self.mode == "year":
            s, _ = ev.month_range(self.year, 1)
            _, f = ev.month_range(self.year, 12)
            return s, f
        return ev.month_range(self.year, self.month)

    def reload(self) -> None:
        from PySide6.QtWidgets import QApplication, QProgressDialog

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.mode == "year":
                out = []
                prog = QProgressDialog(self.tr("Calculando o ano…"), self.tr("Cancelar"),
                                       0, 12, self)
                prog.setWindowModality(Qt.WindowModal)
                prog.setMinimumDuration(300)
                for m in range(1, 13):
                    prog.setValue(m - 1)
                    QApplication.processEvents()
                    if prog.wasCanceled():
                        break
                    s, f = ev.month_range(self.year, m)
                    out += ev.compute_events(self.engine, s, f, list(ev.SOURCES))
                prog.setValue(12)
                self.events = out
            else:
                s, f = self._period()
                self.events = ev.compute_events(self.engine, s, f, list(ev.SOURCES))
        finally:
            QApplication.restoreOverrideCursor()
        self._refilter()

    def visible_events(self) -> list[ev.SkyEvent]:
        cats = set(self.categories())
        min_imp = 2 if self.chk_top.isChecked() else 1
        return [e for e in self.events if e.category in cats and e.importance >= min_imp]

    def _cats_changed(self) -> None:
        if self.settings is not None:
            self.settings.set_value("calendar/categories", ",".join(self.categories()))
        self._refilter()

    def _refilter(self) -> None:
        if self.mode == "year":
            self.lbl.setText(str(self.year))
            self._fill_year()
        else:
            self.lbl.setText(f"{MONTHS[self.month - 1].capitalize()} de {self.year}")
            self._fill_grid()
        self._fill_day()

    # -- grade do mês -------------------------------------------------------
    def _fill_grid(self) -> None:
        self.grid.clearContents()
        for r in range(6):
            for c in range(7):
                self.grid.removeCellWidget(r, c)
        evs = self.visible_events()
        first_wd = (dt.date(self.year, self.month, 1).weekday() + 1) % 7  # domingo = 0
        days = calendar.monthrange(self.year, self.month)[1]
        for d in range(1, days + 1):
            day = dt.date(self.year, self.month, d)
            pos = first_wd + d - 1
            r, c = divmod(pos, 7)
            # na grade, eventos de vários dias aparecem só no primeiro
            items = [e for e in evs if e.local_start().date() == day]
            items.sort(key=lambda e: (-e.importance, e.start_utc))
            lines = []
            for e in items[:4]:
                rgb = ev.CATEGORIES[e.category][1]
                title = e.title if len(e.title) <= 26 else e.title[:25] + "…"
                lines.append(f"<span style='color:{_hex(rgb)}'>{STARS[e.importance]}{title}</span>")
            if len(items) > 4:
                lines.append(f"<span style='color:#999'>+{len(items) - 4}</span>")
            head = f"<b>{d}</b>" if day != self.today else \
                f"<b style='color:#ffcc66'>{d} · hoje</b>"
            lab = QLabel(head + "<br>" + "<br>".join(lines))
            lab.setTextFormat(Qt.RichText)
            lab.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            lab.setWordWrap(True)
            lab.setStyleSheet("QLabel { font-size: 8pt; padding: 2px; }")
            lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.grid.setCellWidget(r, c, lab)
            if day == self.selected_day:
                self.grid.setCurrentCell(r, c)

    def _cell_clicked(self, r: int, c: int) -> None:
        first_wd = (dt.date(self.year, self.month, 1).weekday() + 1) % 7
        d = r * 7 + c - first_wd + 1
        days = calendar.monthrange(self.year, self.month)[1]
        if 1 <= d <= days:
            self.selected_day = dt.date(self.year, self.month, d)
            self._fill_day()

    # -- lista do ano -------------------------------------------------------
    def _fill_year(self) -> None:
        self.year_list.clear()
        groups: dict[int, QTreeWidgetItem] = {}
        for e in self.visible_events():
            lt = e.local_start()
            if lt.year != self.year:
                continue
            g = groups.get(lt.month)
            if g is None:
                g = QTreeWidgetItem([MONTHS[lt.month - 1].capitalize(), ""])
                groups[lt.month] = g
                self.year_list.addTopLevelItem(g)
            it = QTreeWidgetItem([f"{lt:%d/%m %H:%M}", STARS[e.importance] + e.title])
            it.setForeground(1, QColor(*ev.CATEGORIES[e.category][1]))
            it.setData(0, Qt.UserRole, e)
            g.addChild(it)
        self.year_list.expandAll()
        self.year_list.resizeColumnToContents(0)

    def _year_clicked(self, item, _col) -> None:
        e = item.data(0, Qt.UserRole)
        if e is not None:
            self.selected_day = e.local_start().date()
            self._fill_day(select=e)

    # -- lista do dia e detalhe ---------------------------------------------
    def _fill_day(self, select: ev.SkyEvent | None = None) -> None:
        self.day_list.clear()
        day = self.selected_day
        if day is None:
            return
        self.lbl_day.setText(f"<b>{day:%d/%m/%Y}</b>")
        evs = ev.events_on(self.visible_events(), day)
        for e in evs:
            it = QTreeWidgetItem([f"{e.local_start():%H:%M}", STARS[e.importance] + e.title])
            it.setForeground(1, QColor(*ev.CATEGORIES[e.category][1]))
            it.setData(0, Qt.UserRole, e)
            self.day_list.addTopLevelItem(it)
            if select is not None and e.uid == select.uid:
                self.day_list.setCurrentItem(it)
        self.day_list.resizeColumnToContents(0)
        if select is None and self.day_list.topLevelItemCount():
            self.day_list.setCurrentItem(self.day_list.topLevelItem(0))
        if not self.day_list.topLevelItemCount():
            self.detail.setHtml(f"<p style='color:#999'>{self.tr('Nenhum evento neste dia.')}</p>")
            self.btn_remind.setEnabled(False)
            self.btn_go.setEnabled(False)

    def current_event(self) -> ev.SkyEvent | None:
        it = self.day_list.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def _event_selected(self) -> None:
        e = self.current_event()
        if e is None:
            return
        when = e.local_start()
        span = ""
        if e.end_utc:
            span = f" até {to_local(e.end_utc):%d/%m %H:%M}"
        vis = ""
        if e.visible is True:
            vis = "<p style='color:#7d7'>Visível do seu local.</p>"
        elif e.visible is False:
            vis = "<p style='color:#d97'>Não visível do seu local.</p>"
        self.detail.setHtml(
            f"<h3>{e.title}</h3><p style='color:#9aa'>{e.category_label} · "
            f"{when:%d/%m/%Y %H:%M}{span}</p><p>{e.detail}</p>{vis}")
        self.btn_remind.setEnabled(True)
        self.btn_go.setEnabled(True)
        on = ev.is_reminded(e)
        self.btn_remind.setChecked(on)
        self.btn_remind.setText(self.tr("🔔 Lembrete ativo") if on else self.tr("🔔 Lembrar-me"))

    def _toggle_reminder(self) -> None:
        e = self.current_event()
        if e is None:
            return
        if ev.is_reminded(e):
            ev.remove_reminder(e.uid)
        else:
            ev.add_reminder(e)
        self._event_selected()

    def _goto(self) -> None:
        e = self.current_event()
        if e is not None:
            self.gotoEvent.emit(e)

    # -- navegação ----------------------------------------------------------
    def shift(self, delta: int) -> None:
        if self.mode == "year":
            self.year += delta
        else:
            m = self.month + delta
            self.year += (m - 1) // 12
            self.month = (m - 1) % 12 + 1
        self.selected_day = dt.date(self.year, self.month, 1) if \
            (self.year, self.month) != (self.today.year, self.today.month) else self.today
        self.reload()

    def go_today(self) -> None:
        self.year, self.month = self.today.year, self.today.month
        self.selected_day = self.today
        self.reload()

    def _mode_changed(self) -> None:
        self.mode = self.cmb_mode.currentData()
        self.grid.setVisible(self.mode == "month")
        self.year_list.setVisible(self.mode == "year")
        if self.mode == "year":
            self.chk_top.setChecked(True)
        self.reload()

    # -- exportação ---------------------------------------------------------
    def export_ics(self, path: str | None = None) -> str | None:
        from ..core.ics import to_ics

        evs = self.visible_events()
        if not evs:
            QMessageBox.information(self, self.tr("Exportar"), self.tr("Nenhum evento a exportar."))
            return None
        if not path:
            name = (f"carina-{self.year}.ics" if self.mode == "year"
                    else f"carina-{self.year}-{self.month:02d}.ics")
            path, _ = QFileDialog.getSaveFileName(self, self.tr("Exportar calendário"), name,
                                                  "iCalendar (*.ics)")
            if not path:
                return None
        reminded = {e.uid for e in ev.reminders()}
        text = to_ics([e.to_ics(self.location, 60 if e.uid in reminded else None)
                       for e in evs])
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        self.statusBar().showMessage(self.tr("{n} eventos exportados para {p}").format(
            n=len(evs), p=path), 6000)
        return path


class TodayDialog(QDialog):
    """O cartão "Hoje no céu" mostrado ao abrir o programa."""

    openCalendar = Signal()

    def __init__(self, today_events: list, reminders: list, parent=None, settings=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Hoje no céu"))
        self.settings = settings
        text = QTextBrowser()
        html = []
        if reminders:
            html.append("<h3>🔔 Seus lembretes</h3><ul>")
            for e in reminders:
                html.append(f"<li><b>{e.local_start():%d/%m %H:%M}</b> — {e.title}</li>")
            html.append("</ul>")
        html.append("<h3>Hoje</h3>")
        if today_events:
            html.append("<ul>")
            for e in today_events:
                rgb = ev.CATEGORIES[e.category][1]
                html.append(f"<li><span style='color:{_hex(rgb)}'>{STARS[e.importance]}"
                            f"{e.title}</span> — {e.local_start():%H:%M}"
                            + (f"<br><span style='color:#9aa'>{e.detail}</span>" if e.detail else "")
                            + "</li>")
            html.append("</ul>")
        else:
            html.append("<p>Nenhum evento especial hoje.</p>")
        text.setHtml("".join(html))
        self.chk = QCheckBox(self.tr("Mostrar ao abrir o programa"))
        self.chk.setChecked(True if settings is None else
                            settings.value("calendar/show_today", True, bool))
        self.chk.toggled.connect(self._save)
        open_cal = QPushButton(self.tr("Abrir o calendário"))
        open_cal.clicked.connect(lambda: (self.openCalendar.emit(), self.accept()))
        close = QPushButton(self.tr("Fechar"))
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(self.chk)
        row.addStretch(1)
        row.addWidget(open_cal)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(text, 1)
        lay.addLayout(row)
        self.resize(520, 420)

    def _save(self, on: bool) -> None:
        if self.settings is not None:
            self.settings.set_value("calendar/show_today", on)


TODAY_CATEGORIES = ("lua", "eclipse", "planeta", "encontro", "meteoros", "estacao",
                    "ocultacao")


def today_events(engine, now_utc: dt.datetime) -> list:
    """Eventos do dia local de ``now_utc`` (inclusive os de vários dias)."""
    from ..core.localtime import from_local_naive

    day = to_local(now_utc).date()
    s = from_local_naive(dt.datetime.combine(day, dt.time(0))).astimezone(dt.timezone.utc)
    f = s + dt.timedelta(days=1)
    evs = ev.compute_events(engine, s - dt.timedelta(days=3), f, TODAY_CATEGORIES)
    return [e for e in ev.events_on(evs, day)]
