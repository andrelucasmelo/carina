"""Minhas listas de observação (v0.15 T7).

Várias listas nomeadas, guardadas no ``carina.sqlite``. Para cada item a
janela mostra como ele está **nesta noite** — pontuação, janela útil e
melhor hora, já com o horizonte do quintal — e se já foi observado. Daqui
se vai ao objeto no mapa, se reordena, se anota e se monta o roteiro da
noite com os itens da lista.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.userdata import DEFAULT_LIST

COLUMNS = ["Objeto", "Tipo", "Nota hoje", "Janela útil", "Melhor hora",
           "Observado", "Anotação"]


class ListsWindow(QMainWindow):
    """Janela Objetos ▸ Minhas listas…"""

    gotoRequested = Signal(object)        # seleção ("dso", id) etc.
    planRequested = Signal(str)           # nome da lista
    currentListChanged = Signal(str)

    def __init__(self, ctx, settings_store, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx                    # CardContext (engine, catálogos, banco)
        self.store = settings_store
        self.ud = ctx.userdata
        self.setWindowTitle(self.tr("Minhas listas"))
        self.resize(980, 560)
        self._rows: list[dict] = []

        self.combo = QComboBox()
        btn_new = QPushButton(self.tr("Nova…"))
        btn_rename = QPushButton(self.tr("Renomear…"))
        btn_delete = QPushButton(self.tr("Excluir lista"))
        self.lbl_current = QLabel()
        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Lista:")))
        top.addWidget(self.combo, 1)
        for b in (btn_new, btn_rename, btn_delete):
            top.addWidget(b)
        top.addWidget(self.lbl_current)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([self.tr(c) for c in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)

        self.btn_goto = QPushButton(self.tr("Ir para"))
        self.btn_up = QPushButton(self.tr("Subir"))
        self.btn_down = QPushButton(self.tr("Descer"))
        self.btn_remove = QPushButton(self.tr("Remover"))
        self.btn_note = QPushButton(self.tr("Anotar…"))
        self.btn_current = QPushButton(self.tr("Usar como lista do ★"))
        self.btn_csv = QPushButton(self.tr("Exportar…"))
        self.btn_import = QPushButton(self.tr("Importar…"))
        self.btn_plan = QPushButton(self.tr("Montar roteiro desta noite"))
        self.btn_plan.setDefault(True)
        bottom = QHBoxLayout()
        for b in (self.btn_goto, self.btn_up, self.btn_down, self.btn_remove,
                  self.btn_note, self.btn_current, self.btn_import, self.btn_csv):
            bottom.addWidget(b)
        bottom.addStretch(1)
        bottom.addWidget(self.btn_plan)

        self.info = QLabel()
        self.info.setWordWrap(True)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.info)
        lay.addLayout(bottom)
        self.setCentralWidget(central)

        self.combo.currentIndexChanged.connect(self._load_items)
        btn_new.clicked.connect(self._new_list)
        btn_rename.clicked.connect(self._rename_list)
        btn_delete.clicked.connect(self._delete_list)
        self.btn_goto.clicked.connect(self._goto)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(+1))
        self.btn_remove.clicked.connect(self._remove)
        self.btn_note.clicked.connect(self._edit_note)
        self.btn_current.clicked.connect(self._set_current)
        self.btn_csv.clicked.connect(self._export)
        self.btn_import.clicked.connect(self._import)
        self.btn_plan.clicked.connect(
            lambda: self.planRequested.emit(self.current_name()))
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.btn_remove.setShortcut(QKeySequence.Delete)

        self.refresh_lists()

    # -- listas ------------------------------------------------------------
    def current_name(self) -> str:
        return self.combo.currentData() or DEFAULT_LIST

    def refresh_lists(self, select: str | None = None) -> None:
        current = self.store.value("lists/current", DEFAULT_LIST, str)
        lists = self.ud.lists()
        if not lists:
            self.ud.ensure_list(DEFAULT_LIST)
            lists = self.ud.lists()
        target = select or self.combo.currentData() or current
        self.combo.blockSignals(True)
        self.combo.clear()
        for item in lists:
            mark = " ★" if item["name"] == current else ""
            self.combo.addItem(f"{item['name']} ({item['count']}){mark}", item["name"])
        idx = self.combo.findData(target)
        self.combo.setCurrentIndex(max(0, idx))
        self.combo.blockSignals(False)
        self.lbl_current.setText(self.tr("★ = destino de \"Acrescentar à minha lista\""))
        self._load_items()

    def _new_list(self) -> None:
        name, ok = QInputDialog.getText(self, self.tr("Nova lista"), self.tr("Nome:"))
        if ok and name.strip():
            try:
                self.ud.create_list(name.strip())
            except Exception:  # noqa: BLE001 — nome repetido
                QMessageBox.warning(self, self.tr("Listas"),
                                    self.tr("Já existe uma lista com esse nome."))
                return
            self.refresh_lists(name.strip())

    def _rename_list(self) -> None:
        old = self.current_name()
        name, ok = QInputDialog.getText(self, self.tr("Renomear lista"),
                                        self.tr("Novo nome:"), text=old)
        if ok and name.strip() and name.strip() != old:
            lid = self.ud.list_id(old)
            try:
                self.ud.rename_list(lid, name.strip())
            except Exception:  # noqa: BLE001
                QMessageBox.warning(self, self.tr("Listas"),
                                    self.tr("Já existe uma lista com esse nome."))
                return
            if self.store.value("lists/current", DEFAULT_LIST, str) == old:
                self.store.set_value("lists/current", name.strip())
            self.refresh_lists(name.strip())

    def _delete_list(self) -> None:
        name = self.current_name()
        answer = QMessageBox.question(self, self.tr("Listas"), self.tr(
            "Excluir a lista \"{n}\" e seus itens?").format(n=name))
        if answer != QMessageBox.Yes:
            return
        self.ud.delete_list(self.ud.list_id(name))
        if self.store.value("lists/current", DEFAULT_LIST, str) == name:
            self.store.set_value("lists/current", DEFAULT_LIST)
        self.refresh_lists()

    def _set_current(self) -> None:
        self.store.set_value("lists/current", self.current_name())
        self.currentListChanged.emit(self.current_name())
        self.refresh_lists(self.current_name())

    # -- itens ---------------------------------------------------------------
    def _evaluate(self, item: dict):
        """(seleção, visibilidade, pontuação) do item nesta noite."""
        from ..core.objects import ObjectRef
        from ..core.score import score_visibility
        from ..core.visibility import Target, compute_visibility, night_grid

        c = self.ctx
        ref = ObjectRef.from_ident(item["kind"], item["ident"], c.stars, c.dso)
        if ref is None:
            return None, None, None
        now = c.engine.time.current_datetime()
        grid = night_grid(c.engine, now)
        vis = compute_visibility(c.engine, Target.from_ref(ref), now, c.min_alt(),
                                 c.horizon(), grid=grid, refine=False)
        if ref.kind == "dso":
            d = ref.data
            props = (d.get("mag"), d.get("maj"), d.get("min"), d.get("klass", ""))
        elif ref.kind == "star":
            props = (float(c.stars.mag[ref.key]), None, None, "STAR")
        else:
            props = (-1.0, None, None, "MOON" if ref.key == "Lua" else "PLANET")
        score = score_visibility(vis, *props, bortle=c.bortle(),
                                 instrument=c.instrument())
        return ref.selection, vis, score

    def _load_items(self) -> None:
        from ..core.localtime import to_local

        lid = self.ud.list_id(self.current_name())
        items = self.ud.items(lid) if lid is not None else []
        observed = self.ud.observed_idents()
        self._rows = []
        self.table.setRowCount(len(items))
        for r, item in enumerate(items):
            sel, vis, score = self._evaluate(item)
            self._rows.append({"item": item, "selection": sel})
            kind_txt = {"dso": self.tr("Céu profundo"), "star": self.tr("Estrela"),
                        "body": self.tr("Sistema Solar")}.get(item["kind"], "")
            if score is None:
                cells = [item["name"], kind_txt, self.tr("não encontrado"), "", "",
                         "", item["note"]]
            else:
                win = best = "—"
                if vis.observable:
                    win = (f"{to_local(vis.window_start):%H:%M}–"
                           f"{to_local(vis.window_end):%H:%M}")
                    best = f"{to_local(vis.best_utc):%H:%M} · {vis.best_alt:.0f}°"
                seen = "✓" if (item["kind"], item["ident"]) in observed else ""
                grade = (f"{score.total} · {score.verdict}" if score.total
                         else score.verdict)
                cells = [item["name"], kind_txt, grade, win, best, seen, item["note"]]
            for c, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if c == 2 and score is not None:
                    cell.setToolTip(score.explain())
                    cell.setData(Qt.UserRole, score.total)
                    if score.total == 0:
                        cell.setForeground(QColor(150, 150, 160))
                self.table.setItem(r, c, cell)
        n_obs = sum(1 for row in self._rows
                    if (row["item"]["kind"], row["item"]["ident"]) in observed)
        visible = sum(1 for r in range(self.table.rowCount())
                      if (self.table.item(r, 2).data(Qt.UserRole) or 0) > 0)
        self.info.setText(self.tr(
            "{n} itens · {v} com janela útil nesta noite · {o} já observados. "
            "Duplo clique leva ao objeto; a nota considera seu horizonte e o "
            "Bortle atual.").format(n=len(items), v=visible, o=n_obs))
        self._update_buttons()

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _update_buttons(self) -> None:
        r = self._selected_row()
        has = r >= 0
        for b in (self.btn_goto, self.btn_remove, self.btn_note):
            b.setEnabled(has)
        self.btn_up.setEnabled(has and r > 0)
        self.btn_down.setEnabled(has and r < self.table.rowCount() - 1)
        self.btn_plan.setEnabled(self.table.rowCount() > 0)

    def _goto(self) -> None:
        r = self._selected_row()
        if r >= 0 and self._rows[r]["selection"] is not None:
            self.gotoRequested.emit(self._rows[r]["selection"])

    def _on_double_click(self, row: int, col: int) -> None:
        if col == 6:
            self._edit_note()
        else:
            self._goto()

    def _move(self, delta: int) -> None:
        r = self._selected_row()
        if r < 0:
            return
        self.ud.move_item(self._rows[r]["item"]["id"], r + delta)
        self._load_items()
        self.table.selectRow(max(0, min(self.table.rowCount() - 1, r + delta)))

    def _remove(self) -> None:
        r = self._selected_row()
        if r < 0:
            return
        self.ud.remove_item(self._rows[r]["item"]["id"])
        self.refresh_lists(self.current_name())

    def _edit_note(self) -> None:
        r = self._selected_row()
        if r < 0:
            return
        item = self._rows[r]["item"]
        text, ok = QInputDialog.getText(self, self.tr("Anotação"), item["name"],
                                        text=item["note"])
        if ok:
            self.ud.set_item_note(item["id"], text)
            self._load_items()
            self.table.selectRow(r)

    def _export(self) -> None:
        """Exportar a lista: CSV do Carina, Telescopius ou SkySafari (v0.22)."""
        from ..core.listformats import FORMATS, export

        lid = self.ud.list_id(self.current_name()) if self.current_name() else None
        if lid is None:
            return
        filters = ";;".join(FORMATS.values())
        path, chosen = QFileDialog.getSaveFileName(
            self, self.tr("Exportar lista"), f"{self.current_name()}.csv", filters)
        if not path:
            return
        fmt = next(k for k, v in FORMATS.items() if v == chosen) if chosen else "csv"
        if path.lower().endswith(".skylist"):
            fmt = "skylist"
        text = export(fmt, self.ud.items(lid))
        Path(path).write_text(text, encoding="utf-8-sig" if fmt == "csv" else "utf-8")

    def _import(self) -> None:
        """Importar de CSV (Carina/Telescopius) ou .skylist para a lista atual."""
        from PySide6.QtWidgets import QMessageBox

        from ..core.listformats import import_names, resolve

        path, _f = QFileDialog.getOpenFileName(
            self, self.tr("Importar lista"), "",
            self.tr("Listas (*.csv *.skylist *.txt);;Todos os arquivos (*)"))
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        fmt = "skylist" if path.lower().endswith(".skylist") or "SkyObject=" in text else (
            "telescopius" if "catalogue entry" in text.lower() else "csv")
        names = import_names(fmt, text)
        found, missing = resolve(names, self.ctx.stars, self.ctx.dso)
        name = self.current_name() or Path(path).stem
        lid = self.ud.ensure_list(name)
        added = sum(1 for it in found if self.ud.add_item(lid, it["kind"], it["ident"],
                                                          it["name"], it["ra"], it["dec"])
                    is not None)
        self.refresh_lists(select=name)
        msg = self.tr("{a} objeto(s) importado(s) para “{l}”.").format(a=added, l=name)
        if missing:
            msg += "\n" + self.tr("Não encontrados: {m}").format(m=", ".join(missing[:15]))
        QMessageBox.information(self, "Carina", msg)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar lista"), f"{self.current_name()}.csv",
            "CSV (*.csv)")
        if not path:
            return
        lines = [";".join(self.tr(c) for c in COLUMNS)]
        for r in range(self.table.rowCount()):
            cells = [self.table.item(r, c) for c in range(len(COLUMNS))]
            lines.append(";".join(c.text() if c else "" for c in cells))
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
