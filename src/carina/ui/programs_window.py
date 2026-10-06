"""Programas de observação (v0.22 T1) — Objetos ▸ Programas de observação.

À esquerda, os programas com um **anel de progresso**; à direita, os itens
do programa escolhido (feitos e que faltam), com **Ir para**, **Marcar como
observado**, **Faltantes numa lista** e o **Certificado** em PDF quando o
programa é concluído. O progresso sai do diário: observar um objeto pelo
caminho que for (ficha, botão direito, companheiro no celular) conta.
"""

from __future__ import annotations

import datetime as dt
import math

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core import programs as P
from ..core.localtime import to_local

GROUP_PT = {"GAL": "galáxia", "NEB": "nebulosa", "PN": "nebulosa planetária",
            "OC": "aglomerado aberto", "GC": "aglomerado globular", "DARK": "nebulosa escura",
            "OTHER": "outro", "Planeta": "planeta"}


class ProgressRing(QWidget):
    """Anel de progresso com a porcentagem no meio."""

    def __init__(self, size: int = 54, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.value = 0.0

    def set_value(self, v: float) -> None:
        self.value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(4, 4, self.width() - 8, self.height() - 8)
        p.setPen(QPen(QColor(55, 62, 80), 5))
        p.drawArc(r, 0, 360 * 16)
        col = QColor(222, 190, 120) if self.value >= 1 else QColor(110, 200, 140)
        p.setPen(QPen(col, 5, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 90 * 16, -int(self.value * 360 * 16))
        p.setPen(QColor(220, 226, 240))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter,
                   "✓" if self.value >= 1 else f"{self.value * 100:.0f}%")
        p.end()


class ProgramsWindow(QMainWindow):
    gotoRequested = Signal(str, str)                # kind, ident

    def __init__(self, main, parent=None) -> None:
        super().__init__(parent or main)
        self.main = main
        self.userdata = main.userdata
        self.setWindowTitle(self.tr("Programas de observação"))
        self.resize(1000, 640)
        self.programs = [P.get(k) for k in P.PROGRAMS]
        self.current: P.Program | None = None
        self.observed: set = set()

        self.list = QListWidget()
        self.list.setSpacing(2)
        self.list.currentRowChanged.connect(self._select)
        self.list.setMinimumWidth(270)

        self.title = QLabel()
        self.title.setStyleSheet("font-size:15pt; font-weight:600;")
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color:#aab3c5;")
        self.status = QLabel()
        self.filter = QComboBox()
        for key, label in (("all", self.tr("Todos")), ("todo", self.tr("Faltam")),
                           ("done", self.tr("Feitos"))):
            self.filter.addItem(label, key)
        self.filter.currentIndexChanged.connect(self._fill_items)
        self.items = QTreeWidget()
        self.items.setHeaderLabels([self.tr("Nº"), self.tr("Objeto"), self.tr("Tipo"),
                                    self.tr("Observado em")])
        self.items.setRootIsDecorated(False)
        self.items.setUniformRowHeights(True)
        hdr = self.items.header()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.items.itemDoubleClicked.connect(lambda *_: self._goto())

        self.btn_goto = QPushButton(self.tr("Ir para"))
        self.btn_goto.clicked.connect(self._goto)
        self.btn_obs = QPushButton(self.tr("✓ Marcar como observado…"))
        self.btn_obs.clicked.connect(self._mark)
        self.btn_list = QPushButton(self.tr("★ Faltantes numa lista"))
        self.btn_list.clicked.connect(self._todo_list)
        self.btn_cert = QPushButton(self.tr("🏆 Certificado…"))
        self.btn_cert.clicked.connect(self._certificate)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(self.title)
        rl.addWidget(self.desc)
        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(QLabel(self.tr("Mostrar:")))
        row.addWidget(self.filter)
        rl.addLayout(row)
        rl.addWidget(self.items, 1)
        brow = QHBoxLayout()
        for b in (self.btn_goto, self.btn_obs, self.btn_list):
            brow.addWidget(b)
        brow.addStretch(1)
        brow.addWidget(self.btn_cert)
        rl.addLayout(brow)

        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.reload()
        self.list.setCurrentRow(0)

    # ------------------------------------------------------------------
    def reload(self, *_a) -> None:
        """Relê o diário e atualiza anéis e itens (chamado quando ele muda)."""
        row = max(0, self.list.currentRow())
        self.list.blockSignals(True)
        self.list.clear()
        for prog in self.programs:
            obs = P.observed_for(prog, self.userdata)
            done, total = prog.progress(obs)
            item = QListWidgetItem()
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(6, 4, 6, 4)
            ring = ProgressRing()
            ring.set_value(done / total if total else 0)
            lay.addWidget(ring)
            txt = QLabel(f"<b>{prog.title}</b><br><span style='color:#9aa4b8'>"
                         f"{done} de {total}" + (" · este ano" if prog.period == "year" else "")
                         + "</span>")
            lay.addWidget(txt, 1)
            item.setSizeHint(QSize(240, 64))
            self.list.addItem(item)
            self.list.setItemWidget(item, w)
        self.list.blockSignals(False)
        self.list.setCurrentRow(min(row, self.list.count() - 1))
        self._select(self.list.currentRow())

    def _select(self, row: int) -> None:
        if not 0 <= row < len(self.programs):
            return
        self.current = self.programs[row]
        self.observed = P.observed_for(self.current, self.userdata)
        done, total = self.current.progress(self.observed)
        self.title.setText(self.current.title)
        src = f"<br><i>Fonte: {self.current.source}</i>" if self.current.source else ""
        self.desc.setText((self.current.description or "") + src)
        nxt = self.current.next_item(self.observed)
        self.status.setText(self.tr("{d} de {t} observados").format(d=done, t=total)
                            + (self.tr(" · próximo: {n}").format(n=nxt.label) if nxt else
                               self.tr(" · programa concluído! 🎉")))
        self.btn_cert.setEnabled(done == total and total > 0)
        self._fill_items()

    def _when_map(self) -> dict:
        out: dict = {}
        year = to_local(dt.datetime.now(dt.timezone.utc)).year
        for o in self.userdata.observations() if self.userdata is not None else []:
            when = to_local(o["when_utc"])
            if self.current.period == "year" and when.year != year:
                continue
            key = (o["kind"], o["ident"])
            if key not in out or when < out[key]:
                out[key] = when
        return out

    def _fill_items(self, *_a) -> None:
        if self.current is None:
            return
        mode = self.filter.currentData()
        whens = self._when_map()
        self.items.clear()
        for it in self.current.items:
            done = (it.kind, it.ident) in self.observed
            if (mode == "todo" and done) or (mode == "done" and not done):
                continue
            when = whens.get((it.kind, it.ident))
            row = QTreeWidgetItem([str(it.number), it.label,
                                   GROUP_PT.get(it.group, it.group.lower()),
                                   f"✓ {when:%d/%m/%Y}" if when else ""])
            if done:
                for c in range(4):
                    row.setForeground(c, QColor(120, 200, 140))
            row.setData(0, Qt.UserRole, it)
            self.items.addTopLevelItem(row)

    def _current_item(self) -> P.ProgramItem | None:
        cur = self.items.currentItem()
        return cur.data(0, Qt.UserRole) if cur is not None else None

    def _goto(self) -> None:
        it = self._current_item()
        if it is None:
            return
        if it.kind == P.LUNAR_KIND:
            self.main._open_lunar100()
            return
        self.gotoRequested.emit(it.kind, it.ident)

    def _mark(self) -> None:
        it = self._current_item()
        if it is None:
            return
        if it.kind == P.LUNAR_KIND:
            ok = self.main._mark_observed_ident(it.kind, it.ident, it.name)
        else:
            from ..core.objects import ObjectRef

            ref = ObjectRef.from_ident(it.kind, it.ident, self.main.star_catalog,
                                       self.main.dso_catalog)
            ok = ref is not None and self.main._mark_observed(ref.selection)
        if ok:
            self.reload()

    def _todo_list(self) -> None:
        if self.current is None or self.userdata is None:
            return
        from ..core.objects import ObjectRef

        name = self.tr("Faltam: {p}").format(p=self.current.title)
        lid = self.userdata.ensure_list(name)
        added = 0
        for it in self.current.items:
            if (it.kind, it.ident) in self.observed or it.kind == P.LUNAR_KIND:
                continue
            ref = ObjectRef.from_ident(it.kind, it.ident, self.main.star_catalog,
                                       self.main.dso_catalog)
            if ref is None:
                continue
            rd = ref.ra_dec or (None, None)
            if self.userdata.add_item(lid, ref.kind, ref.ident, it.label, *rd) is not None:
                added += 1
        self.statusBar().showMessage(
            self.tr("{n} objeto(s) na lista “{l}”").format(n=added, l=name), 6000)

    def _certificate(self) -> None:
        if self.current is None:
            return
        from ..core.certificate import make_certificate

        settings = getattr(self.main, "settings", None)
        default = settings.value("profile/name", "", str) if settings else ""
        name, ok = QInputDialog.getText(self, self.tr("Certificado"),
                                        self.tr("Nome no certificado:"), text=default)
        if not ok:
            return
        if settings is not None:
            settings.set_value("profile/name", name.strip())
        fn, _f = QFileDialog.getSaveFileName(
            self, self.tr("Salvar certificado"),
            f"Certificado - {self.current.title}.pdf", "PDF (*.pdf)")
        if not fn:
            return
        year = to_local(dt.datetime.now(dt.timezone.utc)).year
        date = P.completion_date(self.current, self.userdata,
                                 year if self.current.period == "year" else None) \
            or dt.date.today()
        place = self.main.settings.location().name if settings else ""
        make_certificate(fn, self.current.title, len(self.current.items), name.strip(),
                         date, place, self.current.source)
        QMessageBox.information(self, "Carina", self.tr("Certificado salvo em\n{f}").format(f=fn))
