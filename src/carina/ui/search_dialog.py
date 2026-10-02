"""Busca de objetos (Ctrl+F) — v2 (v0.15 T6).

A lógica fica em :mod:`carina.core.search` (nomes, designações, Bayer,
constelações). Este diálogo mostra os resultados com o tipo, a altitude
agora e a pontuação da noite; Enter ou duplo clique leva ao objeto
(constelação: centro + destaque) e **Ctrl+Enter** acrescenta à lista do ★
sem fechar a busca.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QHeaderView, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

from ..core.search import search


class SearchDialog(QDialog):
    """Busca unificada com resultados ao digitar."""

    goto_requested = Signal(object)        # ("star"|"dso"|"body"|"const", chave)
    addToListRequested = Signal(object)

    def __init__(self, stars, dso, parent=None, ctx=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Buscar objeto"))
        self.resize(640, 460)
        self.stars, self.dso, self.ctx = stars, dso, ctx

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(self.tr(
            "Nome, designação (M 42, NGC 7000), Bayer (alfa ori), constelação ou corpo"))
        self.edit.textChanged.connect(self._schedule)
        self.edit.returnPressed.connect(self._go_first)
        self.list = QTreeWidget()
        self.list.setColumnCount(4)
        self.list.setHeaderLabels([self.tr("Objeto"), self.tr("Tipo"),
                                   self.tr("Agora"), self.tr("Hoje")])
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        hdr = self.list.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.list.itemActivated.connect(self._go_item)
        self.hint = QLabel(self.tr(
            "Enter vai ao objeto · Ctrl+Enter acrescenta à minha lista · Esc fecha"))
        self.hint.setStyleSheet("color: #8a93a5; font-size: 8pt")

        layout = QVBoxLayout(self)
        layout.addWidget(self.edit)
        layout.addWidget(self.list)
        layout.addWidget(self.hint)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(lambda: self._update(self.edit.text()))
        self.edit.installEventFilter(self)
        self.list.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        """Ctrl+Enter no campo ou na lista acrescenta à lista do ★."""
        from PySide6.QtCore import QEvent

        if (event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and event.modifiers() & Qt.ControlModifier):
            self.add_current_to_list()
            return True
        return super().eventFilter(obj, event)

    def _flush(self) -> None:
        """Aplica uma busca ainda pendente no temporizador."""
        if self._timer.isActive() or not self.list.topLevelItemCount():
            self._timer.stop()
            self._update(self.edit.text())

    def add_current_to_list(self) -> None:
        self._flush()
        sel = self._current_selection()
        if sel is not None and sel[0] != "const":
            self.addToListRequested.emit(sel)
            self.hint.setText(self.tr("Acrescentado à minha lista ✓"))

    # -- resultados ------------------------------------------------------
    def _schedule(self, _text: str) -> None:
        self._timer.start()

    def _update(self, text: str) -> None:
        self.list.clear()
        results = search(text, self.stars, self.dso)
        for i, res in enumerate(results):
            item = QTreeWidgetItem([res.label, res.detail, "", ""])
            item.setData(0, Qt.UserRole, res.selection)
            if self.ctx is not None and i < 15:
                self._annotate(item, res)
            self.list.addTopLevelItem(item)
        if self.list.topLevelItemCount():
            self.list.setCurrentItem(self.list.topLevelItem(0))

    def _annotate(self, item: QTreeWidgetItem, res) -> None:
        """Altitude agora e pontuação da noite (só os primeiros resultados)."""
        import math

        from ..core.objects import ObjectRef
        from ..core.score import score_visibility
        from ..core.visibility import Target, compute_visibility, night_grid

        c = self.ctx
        if res.kind == "const":
            return
        try:
            ref = ObjectRef.resolve(res.selection, c.stars, c.dso)
            if ref is None:
                return
            eng = c.engine
            now = eng.time.current_datetime()
            t = eng.time.current()
            if ref.icrs is not None:
                h = eng.horizontal_matrix(t) @ ref.icrs
            else:
                st = next((b for b in eng.bodies(t) if b.name == ref.key), None)
                h = st.vec if st is not None else None
            if h is not None:
                alt = math.degrees(math.asin(max(-1.0, min(1.0, float(h[2])))))
                item.setText(2, f"{alt:+.0f}°")
                item.setForeground(2, QColor(120, 210, 140) if alt > 0
                                   else QColor(150, 150, 160))
            vis = compute_visibility(eng, Target.from_ref(ref), now, c.min_alt(),
                                     c.horizon(), grid=night_grid(eng, now),
                                     refine=False)
            if ref.kind == "dso":
                d = ref.data
                props = (d.get("mag"), d.get("maj"), d.get("min"), d.get("klass", ""))
            elif ref.kind == "star":
                props = (float(c.stars.mag[ref.key]), None, None, "STAR")
            else:
                props = (-1.0, None, None, "MOON" if ref.key == "Lua" else "PLANET")
            sc = score_visibility(vis, *props, bortle=c.bortle(),
                                  instrument=c.instrument())
            item.setText(3, str(sc.total) if sc.total else "—")
            item.setToolTip(3, sc.explain())
        except Exception:  # noqa: BLE001 — a anotação é um extra
            return

    # -- ações -------------------------------------------------------------
    def _current_selection(self):
        item = self.list.currentItem() or self.list.topLevelItem(0)
        return item.data(0, Qt.UserRole) if item is not None else None

    def _go_item(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        self.goto_requested.emit(item.data(0, Qt.UserRole))
        self.accept()

    def _go_first(self) -> None:
        self._flush()
        item = self.list.currentItem() or self.list.topLevelItem(0)
        if item is not None:
            self._go_item(item)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Down, Qt.Key_Up) and self.edit.hasFocus():
            self.list.setFocus()
            self.list.keyPressEvent(event)
            return
        super().keyPressEvent(event)
