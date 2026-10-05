"""Galeria de tours (v0.20 T6) — Tours ▸ Galeria (``Ctrl+Shift+T``).

Uma aba por categoria; cada tour aparece num cartão com título, resumo,
nível, duração e dois selos: **✓ feito** (já concluído uma vez) e **para
hoje à noite** (todos os alvos ficam no céu na data escolhida — os tours
gerados são sempre feitos para a data). A data do céu dos tours pode ser
trocada no alto; na primeira abertura, um cartão de boas-vindas sugere
por onde começar.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (QDateEdit, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from ..core import tours as T
from ..core.localtime import from_local_naive, to_local

LEVELS = {1: "nível 1 · iniciante", 2: "nível 2 · intermediário", 3: "nível 3 · avançado"}


class ToursGallery(QDialog):
    startRequested = Signal(str, object)        # chave, instante de referência (UTC)

    def __init__(self, main, parent=None, only_keys: list[str] | None = None,
                 title: str = "") -> None:
        super().__init__(parent or main)
        self.main = main
        self.only_keys = only_keys
        self.setWindowTitle(title or self.tr("Tours guiados"))
        self.resize(760, 620)
        self._viable: dict = {}
        lay = QVBoxLayout(self)

        self.welcome = QFrame()
        self.welcome.setStyleSheet("QFrame{background:#18233a; border-radius:6px;}")
        wl = QHBoxLayout(self.welcome)
        wtxt = QLabel(self.tr(
            "<b>Bem-vindo aos tours!</b><br>Um tour leva o céu, passo a passo, às estrelas, "
            "constelações e objetos de que fala. Use ◀ ▶ para navegar e <b>Esc</b> para sair "
            "— o céu volta exatamente como estava."))
        wtxt.setWordWrap(True)
        wbtn = QPushButton(self.tr("Começar por “Como se orientar”"))
        wbtn.clicked.connect(lambda: self._start("como-se-orientar"))
        wl.addWidget(wtxt, 1)
        wl.addWidget(wbtn)
        lay.addWidget(self.welcome)
        settings = getattr(main, "settings", None)
        seen = settings.value("tours/welcome_seen", False, bool) if settings else True
        self._welcome_on = not seen and not only_keys
        self.welcome.setVisible(self._welcome_on)

        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Céu da noite de:")))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        today = to_local(main.engine.time.current_datetime()).date()
        self.date.setDate(QDate(today.year, today.month, today.day))
        self.date.dateChanged.connect(self._date_changed)
        btn_today = QPushButton(self.tr("Hoje"))
        btn_today.clicked.connect(self._to_today)
        top.addWidget(self.date)
        top.addWidget(btn_today)
        top.addStretch(1)
        self.lbl_place = QLabel()
        self.lbl_place.setStyleSheet("color:#8a93a5")
        top.addWidget(self.lbl_place)
        lay.addLayout(top)

        self.tabs = QTabWidget()
        self.lists: dict[str, QListWidget] = {}
        entries = main.tour_entries()
        if only_keys is not None:
            entries = [e for e in entries if e["key"] in only_keys]
        cats = [c for c in T.CATEGORIES if any(e["category"] == c for e in entries)]
        for cat in cats:
            lw = QListWidget()
            lw.setSpacing(3)
            lw.setAlternatingRowColors(False)
            lw.itemDoubleClicked.connect(lambda it: self._start(it.data(Qt.UserRole)))
            self.lists[cat] = lw
            self.tabs.addTab(lw, T.CATEGORIES[cat].split(" — ")[0])
        self.entries = entries
        lay.addWidget(self.tabs, 1)

        bb = QDialogButtonBox()
        self.btn_start = bb.addButton(self.tr("Começar o tour ▶"), QDialogButtonBox.AcceptRole)
        bb.addButton(self.tr("Fechar"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._start_current)
        bb.rejected.connect(self._close)
        lay.addWidget(bb)
        self._fill()

    # ------------------------------------------------------------------
    def ref_utc(self) -> dt.datetime:
        """Instante de referência dos tours: hoje = o relógio do programa; outra
        data = 15h locais daquele dia (o tour vai ao início da noite)."""
        d = self.date.date().toPython()
        now = self.main.engine.time.current_datetime()
        if d == to_local(now).date():
            return now
        return from_local_naive(dt.datetime(d.year, d.month, d.day, 15, 0)).astimezone(
            dt.timezone.utc)

    def _to_today(self) -> None:
        today = to_local(self.main.engine.time.current_datetime()).date()
        self.date.setDate(QDate(today.year, today.month, today.day))

    def _date_changed(self, *_a) -> None:
        self._viable.clear()
        self._fill()

    def _fill(self) -> None:
        loc = self.main.settings.location() if hasattr(self.main, "settings") else None
        if loc is not None:
            self.lbl_place.setText(loc.name)
        done = T.done_keys(getattr(self.main, "userdata", None))
        ref = self.ref_utc()
        for cat, lw in self.lists.items():
            lw.clear()
            for e in [x for x in self.entries if x["category"] == cat]:
                viable = True if e["generated"] else self._viable_for(e["key"], ref)
                item = QListWidgetItem()
                item.setData(Qt.UserRole, e["key"])
                w = self._card(e, e["key"] in done, viable)
                item.setSizeHint(w.sizeHint())
                lw.addItem(item)
                lw.setItemWidget(item, w)
            if lw.count():
                lw.setCurrentRow(0)

    def _viable_for(self, key: str, ref: dt.datetime) -> bool:
        if key not in self._viable:
            try:
                tour = self.main.get_tour(key, ref)
                run = T.TourRun(tour, self.main.engine, self.main.tour_resolver(), ref,
                                self.main.settings.location().latitude).prepare()
                self._viable[key] = run.viable_tonight
            except Exception:          # noqa: BLE001 — selo é só informativo
                self._viable[key] = False
        return self._viable[key]

    def _card(self, e: dict, done: bool, viable: bool) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(1)
        badges = []
        if done:
            badges.append("<span style='color:#7fd19b'>✓ feito</span>")
        if e["generated"]:
            badges.append("<span style='color:#9ac1ff'>montado para a data</span>")
        elif viable:
            badges.append("<span style='color:#f3d79a'>☾ para esta noite</span>")
        title = QLabel(f"<b style='font-size:11.5pt'>{e['title']}</b>  " + "  ".join(badges))
        sub = QLabel(e["subtitle"])
        sub.setWordWrap(True)
        meta = QLabel(f"<span style='color:#8a93a5'>{LEVELS.get(e['level'], '')} · cerca de "
                      f"{e['minutes']} min</span>")
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addWidget(meta)
        return w

    def current_key(self) -> str | None:
        lw = self.tabs.currentWidget()
        if lw is None or lw.currentItem() is None:
            return None
        return lw.currentItem().data(Qt.UserRole)

    def select(self, key: str) -> bool:
        for i, (cat, lw) in enumerate(self.lists.items()):
            for r in range(lw.count()):
                if lw.item(r).data(Qt.UserRole) == key:
                    self.tabs.setCurrentIndex(i)
                    lw.setCurrentRow(r)
                    return True
        return False

    def _start_current(self) -> None:
        key = self.current_key()
        if key:
            self._start(key)

    def _mark_welcome_seen(self) -> None:
        """Só depois de o usuário usar a galeria (fechar ou começar um tour)."""
        settings = getattr(self.main, "settings", None)
        if settings is not None and self._welcome_on:
            settings.set_value("tours/welcome_seen", True)

    def _close(self) -> None:
        self._mark_welcome_seen()
        self.reject()

    def _start(self, key: str) -> None:
        self._mark_welcome_seen()
        self.startRequested.emit(key, self.ref_utc())
        self.accept()
