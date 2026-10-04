"""Janela da sessão de astrofotografia (v0.19 T1–T3).

Monta a noite de quem fotografa: os alvos, o setup (telescópio, câmera,
montagem), as regras da montagem (meridiano na equatorial, zona do zênite
na altazimutal) e o resultado — blocos de integração na linha do tempo,
a sub-exposição sugerida para o céu do local, quantas noites para juntar
as horas desejadas e o calendário de imageabilidade de cada alvo no ano.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QListView, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QToolTip,
                               QVBoxLayout, QWidget)

from ..core import session as S
from ..core.formats import num
from ..core.localtime import to_local

UTC = dt.timezone.utc
COLORS = [QColor(90, 170, 255), QColor(255, 170, 80), QColor(120, 210, 120),
          QColor(220, 120, 220), QColor(240, 220, 90), QColor(110, 220, 220),
          QColor(255, 120, 120), QColor(180, 160, 255)]
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


class SessionTimeline(QWidget):
    """A noite: altura de cada alvo, os blocos agendados, o meridiano e a
    zona do zênite."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.plan: S.SessionPlan | None = None

    def set_plan(self, plan) -> None:
        self.plan = plan
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(12, 15, 26))
        plan = self.plan
        if plan is None or not plan.times:
            p.setPen(QColor(150, 155, 170))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Acrescente alvos para montar a sessão." if plan is None or not plan.targets
                       else "Sem noite escura nesta data.")
            p.end()
            return
        left, right, top, bottom = 40, 10, 12, 52
        w = self.width() - left - right
        h = self.height() - top - bottom
        n = len(plan.times)

        def x_of(k):
            return left + w * k / max(n - 1, 1)

        def y_of(alt):
            return top + h * (1 - max(0.0, min(90.0, alt)) / 90.0)

        p.setFont(QFont("Segoe UI", 8))
        opt = plan.options
        # faixa útil e zona do zênite
        p.fillRect(QRectF(left, y_of(90), w, y_of(opt.min_alt) - y_of(90)), QColor(22, 28, 44))
        if opt.altaz:
            p.fillRect(QRectF(left, y_of(90), w, y_of(opt.zenith_limit) - y_of(90)),
                       QColor(90, 40, 40, 110))
            p.setPen(QColor(220, 140, 140))
            p.drawText(QRectF(left + 4, y_of(90), 300, 14), Qt.AlignLeft,
                       f"zona do zênite (acima de {opt.zenith_limit:.0f}°)")
        for a in (0, 30, 60, 90):
            y = y_of(a)
            p.setPen(QPen(QColor(60, 70, 90), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.setPen(QColor(140, 150, 165))
            p.drawText(QRectF(0, y - 7, left - 4, 14), Qt.AlignRight | Qt.AlignVCenter, f"{a}°")
        # curvas de altura
        for i in range(len(plan.targets)):
            col = QColor(COLORS[i % len(COLORS)])
            col.setAlpha(110)
            p.setPen(QPen(col, 1.2))
            pts = [QPointF(x_of(k), y_of(plan.alts[i, k])) for k in range(n)]
            for a_, b_ in zip(pts, pts[1:]):
                p.drawLine(a_, b_)
            if plan.meridian[i] is not None and opt.gem:
                k = plan.times.index(plan.meridian[i]) if plan.meridian[i] in plan.times else None
                if k is not None:
                    p.setPen(QPen(QColor(255, 255, 255, 140), 1, Qt.DashLine))
                    p.drawLine(QPointF(x_of(k), y_of(plan.alts[i, k]) - 8),
                               QPointF(x_of(k), y_of(plan.alts[i, k]) + 8))
        # blocos: trechos grossos sobre as curvas e barra embaixo
        bar_y = top + h + 8
        for b in plan.blocks:
            col = COLORS[b.target % len(COLORS)]
            k0 = plan.times.index(b.start) if b.start in plan.times else 0
            k1 = min(n - 1, k0 + int(round(b.minutes / S.STEP_MIN)) - 1)
            p.setPen(QPen(col, 4.0, Qt.SolidLine, Qt.RoundCap))
            for k in range(k0, k1):
                p.drawLine(QPointF(x_of(k), y_of(plan.alts[b.target, k])),
                           QPointF(x_of(k + 1), y_of(plan.alts[b.target, k + 1])))
            p.fillRect(QRectF(x_of(k0), bar_y, x_of(k1 + 1) - x_of(k0), 12), col)
            if b.flip_after:
                p.setPen(QColor(255, 230, 150))
                p.drawText(QPointF(x_of(k1) - 4, bar_y + 26), "↺")
        p.setPen(QColor(150, 160, 180))
        for k, t in enumerate(plan.times):
            lt = to_local(t)
            if lt.minute == 0:
                p.drawText(QRectF(x_of(k) - 14, bar_y + 14, 28, 14), Qt.AlignCenter, f"{lt:%H}h")
        p.end()


class YearChart(QWidget):
    """Calendário de imageabilidade: horas úteis por noite no ano."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMouseTracking(True)
        self.img = None
        self.title = ""
        self._hover = -1
        self._geom = None             # (left, top, w, h, hmax)

    def set_data(self, img, title: str) -> None:
        self.img, self.title = img, title
        self._hover = -1
        self.update()

    def bar_at(self, x: float) -> int:
        """Índice da barra sob a coordenada x (ou −1)."""
        if self.img is None or self._geom is None:
            return -1
        left, _top, w, _h, _hm = self._geom
        n = len(self.img.hours)
        k = int((x - left) / max(w, 1) * n)
        return k if 0 <= k < n else -1

    def tooltip_text(self, k: int) -> str:
        d = self.img.dates[k]
        hh = float(self.img.hours[k])
        dark = float(self.img.dark_hours[k]) if getattr(self.img, "dark_hours", None) is not None \
            else None
        txt = f"{d:%d/%m/%Y}: {num(hh, 1)} h úteis"
        if dark is not None:
            txt += f" de {num(dark, 1)} h de noite escura"
        return txt

    def mouseMoveEvent(self, e) -> None:
        k = self.bar_at(e.position().x())
        if k != self._hover:
            self._hover = k
            self.update()
        if k >= 0:
            QToolTip.showText(e.globalPosition().toPoint(), self.tooltip_text(k), self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        QToolTip.hideText()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(14, 18, 28))
        if self.img is None:
            p.end()
            return
        left, right, top, bottom = 30, 6, 18, 18
        w = self.width() - left - right
        h = self.height() - top - bottom
        hours = self.img.hours
        n = len(hours)
        hmax = float(math.ceil(max(8.0, float(hours.max()) if n else 8.0)))
        self._geom = (left, top, w, h, hmax)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(150, 160, 180))
        p.drawText(QRectF(4, 2, self.width() - 8, 14), Qt.AlignLeft, self.title)
        for k, hh in enumerate(hours):
            x = left + w * k / max(n, 1)
            bh = h * hh / hmax
            col = QColor(90, 170, 110) if hh >= 3 else QColor(200, 170, 80) if hh > 0.5 \
                else QColor(70, 70, 80)
            if k == self._hover:
                col = col.lighter(150)
            p.fillRect(QRectF(x, top + h - bh, max(1.0, w / n), bh), col)
        # uma linha por hora (por cima das barras, discreta); rótulo a cada 2 h
        for hr in range(1, int(hmax) + 1):
            y = top + h - h * hr / hmax
            p.setPen(QPen(QColor(255, 255, 255, 60 if hr % 2 == 0 else 32), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            if hr % 2 == 0 and hr < hmax:
                p.setPen(QColor(120, 130, 150))
                p.drawText(QRectF(0, y - 7, left - 3, 14), Qt.AlignRight | Qt.AlignVCenter,
                           f"{hr}h")
        p.setPen(QColor(150, 160, 180))
        last = None
        for k, d in enumerate(self.img.dates):
            if d.month != last and d.day <= 7:
                x = left + w * k / max(n, 1)
                p.drawText(QRectF(x - 10, top + h + 2, 24, 14), Qt.AlignCenter, MONTHS[d.month - 1])
                last = d.month
        p.drawText(QRectF(0, top - 6, left - 3, 14), Qt.AlignRight, f"{hmax:.0f}h")
        p.end()


class SessionWindow(QMainWindow):
    """Planejar ▸ Sessão de astrofoto."""

    gotoTarget = Signal(str, str)          # kind, ident
    fovRequested = Signal()                # abrir o Campo de visão (criar setups)

    def __init__(self, engine, when_utc: dt.datetime, parent=None, *, equipment=None,
                 userdata=None, bortle=lambda: 5, horizon=lambda: None,
                 current_target=lambda: None, active_setup: str = "",
                 settings=None, candidates=lambda: [], resolve=lambda kind, ident: None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sessão de astrofotografia"))
        self.engine = engine
        self.when = when_utc
        self.equipment = equipment
        self.userdata = userdata
        self.bortle = bortle
        self.horizon = horizon
        self.current_target = current_target
        self.settings = settings
        self.candidates = candidates       # () → [dict] para as sugestões
        self.resolve = resolve             # (kind, ident) → (nome, icrs, ident, kind, tam.)
        self._sub_user = False             # o usuário mexeu na sub (não sobrescrever)
        self.targets: list[S.SessionTarget] = []
        self.plan: S.SessionPlan | None = None
        self._img_cache: dict = {}

        # --- alvos -------------------------------------------------------
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._target_selected)
        add = QPushButton(self.tr("+ Objeto selecionado"))
        add.clicked.connect(self.add_current)
        add_list = QPushButton(self.tr("+ Da minha lista ▾"))
        add_list.clicked.connect(self._menu_lists)
        rem = QPushButton(self.tr("Remover"))
        rem.clicked.connect(self._remove)
        sug = QPushButton(self.tr("✨ Sugestões de alvos…"))
        sug.setToolTip(self.tr("Os alvos mais bem posicionados nesta noite, com fotos"))
        sug.clicked.connect(self._open_suggestions)
        self.sp_prio = QDoubleSpinBox()
        self.sp_prio.setRange(0.5, 2.0)
        self.sp_prio.setSingleStep(0.25)
        self.sp_prio.setValue(1.0)
        self.sp_prio.valueChanged.connect(self._target_params)
        self.sp_hours = QDoubleSpinBox()
        self.sp_hours.setRange(0.0, 12.0)
        self.sp_hours.setSingleStep(0.5)
        self.sp_hours.setSpecialValueText(self.tr("parte igual"))
        self.sp_hours.valueChanged.connect(self._target_params)
        tbox = QGroupBox(self.tr("Alvos"))
        tl = QVBoxLayout(tbox)
        tl.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(add_list)
        tl.addLayout(row)
        tl.addWidget(sug)
        tl.addWidget(rem)
        tf = QFormLayout()
        tf.addRow(self.tr("Prioridade:"), self.sp_prio)
        tf.addRow(self.tr("Horas nesta noite:"), self.sp_hours)
        tl.addLayout(tf)

        # --- setup e regras -------------------------------------------------
        from ..catalogs.equipment import MOUNT_KINDS

        self.cb_setup = QComboBox()
        self.cb_setup.currentIndexChanged.connect(self._setup_changed)
        btn_fov = QPushButton(self.tr("Campo de visão…"))
        btn_fov.setToolTip(self.tr("Criar ou editar setups (Planejar ▸ Campo de visão)"))
        btn_fov.clicked.connect(self.fovRequested.emit)
        setup_row = QHBoxLayout()
        setup_row.addWidget(self.cb_setup, 1)
        setup_row.addWidget(btn_fov)
        self.cb_mount = QComboBox()
        for key, label in MOUNT_KINDS.items():
            self.cb_mount.addItem(label, key)
        self.cb_mount.currentIndexChanged.connect(self.recompute)
        self.sp_sub = QSpinBox()
        self.sp_sub.setRange(1, 1800)
        self.sp_sub.setValue(int(self._setting("session/sub_s", 120)))
        self.sp_sub.setSuffix(" s")
        self.sp_sub.valueChanged.connect(self._sub_edited)
        btn_sug = QPushButton(self.tr("Sugerida"))
        btn_sug.setToolTip(self.tr("Usa a sub-exposição sugerida para o setup e o céu"))
        btn_sug.clicked.connect(self._use_suggested_sub)
        btn_margin = QPushButton(self.tr("Margens…"))
        btn_margin.setToolTip(self.tr("Margem de subs perdidas (vento, nuvens, satélites) "
                                      "por faixa de duração"))
        btn_margin.clicked.connect(self._edit_margins)
        sub_row = QHBoxLayout()
        sub_row.addWidget(self.sp_sub)
        sub_row.addWidget(btn_sug)
        sub_row.addWidget(btn_margin)
        self.lbl_margin = QLabel()
        self.lbl_margin.setStyleSheet("color:#9aa")
        self.sp_minalt = QSpinBox()
        self.sp_minalt.setRange(10, 70)
        self.sp_minalt.setValue(30)
        self.sp_minalt.setSuffix("°")
        self.sp_zen = QSpinBox()
        self.sp_zen.setRange(60, 89)
        self.sp_zen.setValue(80)
        self.sp_zen.setSuffix("°")
        self.sp_mer = QSpinBox()
        self.sp_mer.setRange(0, 60)
        self.sp_mer.setValue(10)
        self.sp_mer.setSuffix(" min")
        self.cb_dark = QComboBox()
        self.cb_dark.addItem(self.tr("Noite astronômica (Sol < −18°)"), -18.0)
        self.cb_dark.addItem(self.tr("Noite náutica (Sol < −12°)"), -12.0)
        for w in (self.sp_minalt, self.sp_zen, self.sp_mer):
            w.valueChanged.connect(self.recompute)
        self.cb_dark.currentIndexChanged.connect(self.recompute)
        sbox = QGroupBox(self.tr("Setup e regras"))
        sf = QFormLayout(sbox)
        sf.addRow(self.tr("Setup:"), setup_row)
        sf.addRow(self.tr("Montagem:"), self.cb_mount)
        sf.addRow(self.tr("Sub-exposição:"), sub_row)
        sf.addRow("", self.lbl_margin)
        sf.addRow(self.tr("Altura mínima:"), self.sp_minalt)
        sf.addRow(self.tr("Limite do zênite (alt-az):"), self.sp_zen)
        sf.addRow(self.tr("Folga do meridiano (equatorial):"), self.sp_mer)
        sf.addRow(self.tr("Escuridão:"), self.cb_dark)

        left_box = QWidget()
        ll = QVBoxLayout(left_box)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(tbox, 1)
        ll.addWidget(sbox)

        # --- data ------------------------------------------------------------
        bar = QHBoxLayout()
        prev = QPushButton("◀")
        prev.clicked.connect(lambda: self._shift(-1))
        nxt = QPushButton("▶")
        nxt.clicked.connect(lambda: self._shift(1))
        self.lbl_night = QLabel()
        self.lbl_night.setMinimumWidth(220)
        bar.addWidget(prev)
        bar.addWidget(self.lbl_night)
        bar.addWidget(nxt)
        bar.addStretch(1)
        copy = QPushButton(self.tr("Copiar agenda"))
        copy.clicked.connect(self._copy)
        bar.addWidget(copy)
        go = QPushButton(self.tr("Ir para o alvo"))
        go.clicked.connect(self._goto)
        bar.addWidget(go)

        self.timeline = SessionTimeline()
        self.year = YearChart()
        self.details = QTextBrowser()
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addLayout(bar)
        cl.addWidget(self.timeline, 3)
        cl.addWidget(self.year, 1)

        # --- metas ----------------------------------------------------------
        self.sp_goal = QDoubleSpinBox()
        self.sp_goal.setRange(1, 100)
        self.sp_goal.setValue(10)
        self.sp_goal.setSuffix(" h")
        self.sp_goal.valueChanged.connect(self._fill_details)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        grow = QHBoxLayout()
        grow.addWidget(QLabel(self.tr("Meta de integração por alvo:")))
        grow.addWidget(self.sp_goal)
        grow.addStretch(1)
        rl.addLayout(grow)
        rl.addWidget(self.details, 1)

        split = QSplitter()
        split.addWidget(left_box)
        split.addWidget(center)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        split.setSizes([300, 700, 420])
        self.setCentralWidget(split)
        self.resize(1450, 800)
        self._fill_setups(active_setup)
        self.recompute()

    # -- setup -------------------------------------------------------------
    def _setting(self, key: str, default):
        if self.settings is None:
            return default
        return self.settings.value(key, default, type(default))

    def _setup_names(self) -> list[str]:
        from ..catalogs.equipment import setup_names

        return setup_names(self.userdata) if self.userdata is not None else []

    def _fill_setups(self, active: str) -> None:
        self.cb_setup.blockSignals(True)
        self.cb_setup.clear()
        self.cb_setup.addItem(self.tr("(nenhum — sem estimativa de exposição)"), "")
        for n in self._setup_names():
            self.cb_setup.addItem(n, n)
        self.cb_setup.setCurrentIndex(max(0, self.cb_setup.findData(active)))
        self.cb_setup.blockSignals(False)
        self._setup_changed()

    def refresh_setups(self, active: str | None = None) -> None:
        """Relê os setups salvos (criados no Campo de visão depois de abrir a
        sessão); mantém o escolhido, ou passa para ``active``."""
        names = self._setup_names()
        have = [self.cb_setup.itemData(i) for i in range(1, self.cb_setup.count())]
        want = active if active else (self.cb_setup.currentData() or "")
        if names == have and want == (self.cb_setup.currentData() or ""):
            return
        self._fill_setups(want)

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == QEvent.ActivationChange and self.isActiveWindow() \
                and hasattr(self, "timeline"):
            self.refresh_setups()

    def setup(self):
        from ..catalogs.equipment import load_setup

        name = self.cb_setup.currentData()
        return load_setup(name, self.userdata) if name and self.userdata is not None else None

    def _setup_changed(self, *_a) -> None:
        s = self.setup()
        if s is not None and self.equipment is not None:
            self.cb_mount.blockSignals(True)
            self.cb_mount.setCurrentIndex(max(0, self.cb_mount.findData(
                s.mount_kind(self.equipment))))
            self.cb_mount.blockSignals(False)
            if not self._sub_user:
                adv = self._advice()
                if adv is not None:
                    self.sp_sub.blockSignals(True)
                    self.sp_sub.setValue(adv.sub_s)
                    self.sp_sub.blockSignals(False)
        self.recompute()

    def mount_kind(self) -> str:
        return self.cb_mount.currentData() or "equatorial"

    # -- sub-exposição e margens ------------------------------------------
    def _sub_edited(self, value: int) -> None:
        self._sub_user = True
        if self.settings is not None:
            self.settings.set_value("session/sub_s", int(value))
        self._fill_details()

    def _use_suggested_sub(self) -> None:
        adv = self._advice()
        if adv is None:
            QMessageBox.information(self, "Carina", self.tr(
                "Escolha um setup com telescópio e câmera para ter a sub sugerida."))
            return
        self.sp_sub.setValue(adv.sub_s)
        self._sub_user = False

    def margins(self) -> list:
        import json

        from ..core.exposure import DEFAULT_MARGINS, normalize_margins

        raw = self._setting("session/sub_margins", "")
        try:
            table = [(None if a is None else float(a), float(b)) for a, b in json.loads(raw)]
            return normalize_margins(table) if table else list(DEFAULT_MARGINS)
        except (ValueError, TypeError):
            return list(DEFAULT_MARGINS)

    def _edit_margins(self) -> None:
        import json

        dlg = MarginsDialog(self.margins(), self)
        if dlg.exec() and self.settings is not None:
            self.settings.set_value("session/sub_margins", json.dumps(dlg.table()))
            self._fill_details()

    # -- alvos -------------------------------------------------------------
    def add_target(self, name, icrs, ident="", kind="dso", size=0.0) -> None:
        if any(t.ident == ident and ident for t in self.targets):
            return
        self.targets.append(S.SessionTarget(name, np.asarray(icrs, np.float64), ident or name,
                                            kind, 1.0, float(size or 0.0)))
        self.list.addItem(QListWidgetItem(name))
        self.list.setCurrentRow(self.list.count() - 1)
        self.recompute()

    def add_current(self) -> None:
        got = self.current_target()
        if got is not None:
            self.add_target(*got)

    def _menu_lists(self) -> None:
        if self.userdata is None:
            return
        menu = QMenu(self)
        for lst in self.userdata.lists():
            act = menu.addAction(lst["name"])
            act.triggered.connect(lambda _c=False, lid=lst["id"]: self._add_list(lid))
        if menu.isEmpty():
            menu.addAction(self.tr("(nenhuma lista)")).setEnabled(False)
        menu.exec(self.cursor().pos())

    def _add_list(self, list_id: int) -> None:
        for it in self.userdata.items(list_id):
            if it.get("ra") is None or it["kind"] == "body":
                continue
            ra, dec = float(it["ra"]), float(it["dec"])
            icrs = (math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec))
            self.targets.append(S.SessionTarget(it["name"], np.asarray(icrs), it["ident"], it["kind"]))
            self.list.addItem(QListWidgetItem(it["name"]))
        self.recompute()

    def _remove(self) -> None:
        r = self.list.currentRow()
        if 0 <= r < len(self.targets):
            self.targets.pop(r)
            self.list.takeItem(r)
            self.recompute()

    def _target_selected(self, row: int) -> None:
        if 0 <= row < len(self.targets):
            t = self.targets[row]
            for w, v in ((self.sp_prio, t.priority), (self.sp_hours, t.hours or 0.0)):
                w.blockSignals(True)
                w.setValue(v)
                w.blockSignals(False)
            self._fill_year(row)
            self._fill_details()

    def _target_params(self, *_a) -> None:
        r = self.list.currentRow()
        if 0 <= r < len(self.targets):
            self.targets[r].priority = self.sp_prio.value()
            self.targets[r].hours = self.sp_hours.value() or None
            self.recompute()

    # -- cálculo -----------------------------------------------------------
    def options(self) -> S.SessionOptions:
        from ..catalogs.equipment import mount_flips, mount_is_altaz

        kind = self.mount_kind()
        return S.SessionOptions(min_alt=float(self.sp_minalt.value()),
                                dark_sun=float(self.cb_dark.currentData()),
                                altaz=mount_is_altaz(kind),
                                zenith_limit=float(self.sp_zen.value()),
                                meridian_margin_min=float(self.sp_mer.value()),
                                meridian_flip=mount_flips(kind))

    def recompute(self, *_a) -> None:
        if not hasattr(self, "timeline"):
            return
        self.lbl_night.setText(self.tr("Noite de {d:%d/%m/%Y}").format(d=to_local(self.when).date()))
        self.plan = S.plan_session(self.engine, self.targets, self.when, self.options(),
                                   self.horizon())
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setForeground(COLORS[i % len(COLORS)])
            item.setText(f"{self.targets[i].name} — {num(self.plan.hours_for(i), 1)} h"
                         if self.plan.blocks or self.plan.times else self.targets[i].name)
        self.timeline.set_plan(self.plan)
        self._fill_year(self.list.currentRow())
        self._fill_details()

    def _shift(self, days: int) -> None:
        self.when = self.when + dt.timedelta(days=days)
        self.recompute()

    def _imageability(self, row: int):
        from ..core.imageability import compute

        t = self.targets[row]
        opt = self.options()
        key = (t.ident, to_local(self.when).date(), opt.min_alt, opt.dark_sun, opt.altaz,
               opt.zenith_limit)
        if key not in self._img_cache:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self._img_cache[key] = compute(
                    self.engine, t.icrs, self.when, days=366, step_days=2, min_alt=opt.min_alt,
                    dark_sun=opt.dark_sun, horizon=self.horizon(),
                    zenith_limit=opt.zenith_limit if opt.altaz else None)
            finally:
                QApplication.restoreOverrideCursor()
        return self._img_cache[key]

    def _fill_year(self, row: int) -> None:
        if not (0 <= row < len(self.targets)):
            self.year.set_data(None, "")
            return
        img = self._imageability(row)
        best = ", ".join(MONTHS[m - 1] for m in img.best_months(3))
        self.year.set_data(img, self.tr("Horas úteis por noite no ano — {n} (melhores: {b})")
                           .format(n=self.targets[row].name, b=best))

    def _advice(self):
        """Sugestão de sub para o setup escolhido (ou None)."""
        from ..core.exposure import BORTLE_SQM, suggest_sub

        s = self.setup()
        if s is None or self.equipment is None:
            return None
        scope = self.equipment.find("telescopes", s.telescope)
        cam = self.equipment.find("cameras", s.camera)
        if scope is None or cam is None:
            return None
        bortle = int(self.bortle())
        return suggest_sub(BORTLE_SQM.get(bortle, 20.0), scope, cam,
                           self.equipment.find("accessories", s.accessory),
                           mount=self.mount_kind())

    def _exposure_html(self) -> str:
        s = self.setup()
        if s is None or self.equipment is None:
            return ("<p style='color:#9aa'>Escolha um setup salvo (com câmera) para ver a "
                    "sub-exposição sugerida. Os setups são criados em Planejar ▸ Campo de "
                    "visão (botão <b>Campo de visão…</b> ao lado da lista).</p>")
        adv = self._advice()
        if adv is None:
            return "<p style='color:#9aa'>O setup não tem telescópio e câmera.</p>"
        bortle = int(self.bortle())
        return (f"<h4>Exposição ({s.name}, céu Bortle {bortle})</h4><p>{adv.text()}</p>"
                f"<p style='color:#9aa'>Escala de placa {num(adv.plate_scale, 2)}″/pixel. "
                "Faça uma sub de teste e confira o histograma: o pico do fundo deve sair "
                "da borda esquerda.</p>")

    def _fill_details(self, *_a) -> None:
        plan = self.plan
        if plan is None:
            return
        html = []
        if plan.blocks:
            html.append("<h4>Agenda</h4><table cellspacing=3>")
            for b in plan.blocks:
                tg = plan.targets[b.target]
                col = COLORS[b.target % len(COLORS)].name()
                flip = " <span style='color:#fd8'>↺ virar a montagem</span>" if b.flip_after else ""
                html.append(f"<tr><td style='color:{col}'><b>{tg.name}</b></td>"
                            f"<td>{to_local(b.start):%H:%M}–{to_local(b.end):%H:%M}</td>"
                            f"<td>{num(b.minutes / 60, 1)} h</td>"
                            f"<td style='color:#9aa'>{b.alt_min:.0f}–{b.alt_max:.0f}°</td>"
                            f"<td>{flip}</td></tr>")
            html.append("</table>")
            if plan.options.gem:
                mers = [(plan.targets[i].name, m) for i, m in enumerate(plan.meridian) if m]
                if mers:
                    html.append("<p style='color:#9aa'>Meridiano: " + "; ".join(
                        f"{n} às {to_local(m):%H:%M}" for n, m in mers) + ".</p>")
        for note in plan.notes:
            if note:
                html.append(f"<p style='color:#d97'>{note}</p>")
        html.append(self._exposure_html())
        html.append(self._subs_html())
        # noites para a meta
        if self.targets:
            from ..core.exposure import margin_for, nights_for

            goal = self.sp_goal.value()
            loss = 1.0 + margin_for(self.sp_sub.value(), self.margins()) / 100.0
            html.append(f"<h4>Para juntar {num(goal, 0)} h por alvo</h4><ul>")
            for i, t in enumerate(self.targets):
                img = self._imageability(i)
                nights = img.next_nights(to_local(self.when).date(), 120)
                share = max(1, len(self.targets))
                # cada amostra do calendário vale por 2 noites (passo de 2 dias);
                # só a parte aproveitável das subs conta para a meta
                k = nights_for(goal, [2.0 * h / share / loss for h in nights])
                txt = (f"cerca de {k * 2} noites corridas" if k else "mais de 8 meses")
                html.append(f"<li><b>{t.name}</b>: {txt} (dividindo a noite entre "
                            f"{share} alvo{'s' if share > 1 else ''})</li>")
            html.append("</ul>")
        self.details.setHtml("".join(html) or "<p>Acrescente alvos.</p>")

    def _subs_html(self) -> str:
        """Quantas subs: nesta noite (pelos blocos) e para a meta."""
        from ..core.exposure import margin_for, normalize_margins, subs_for, subs_in

        if self.lbl_margin is None:
            return ""
        sub = self.sp_sub.value()
        table = self.margins()
        pct = margin_for(sub, table)
        band = next((lim for lim, p in normalize_margins(table) if lim is None or sub <= lim),
                    None)
        band_txt = (f"subs até {band:.0f} s" if band is not None
                    else "subs mais longas que a última faixa")
        self.lbl_margin.setText(self.tr("margem de perda: {p}% ({b})").format(
            p=num(pct, 0), b=band_txt))
        goal = self.sp_goal.value()
        sp = subs_for(goal, sub, table)
        out = [f"<h4>Subs de {sub} s · margem {num(pct, 0)}%</h4>"]
        if self.plan is not None and self.plan.blocks:
            out.append("<p>Nesta noite:</p><ul>")
            for i, t in enumerate(self.targets):
                h = self.plan.hours_for(i)
                if h <= 0:
                    continue
                shot, good = subs_in(h, sub, table)
                out.append(f"<li><b>{t.name}</b>: {num(h, 1)} h → {shot} subs "
                           f"(≈ {good} aproveitáveis, {num(good * sub / 3600, 1)} h)</li>")
            out.append("</ul>")
        out.append(f"<p>Para <b>{num(goal, 0)} h</b> úteis por alvo: {sp.good} subs "
                   f"aproveitáveis; fotografe <b>{sp.total}</b> (+{num(pct, 0)}% para as "
                   f"perdidas por vento, nuvens e satélites) ≈ {num(sp.shoot_hours, 1)} h de "
                   "captura.</p>")
        return "".join(out)

    # -- sugestões ----------------------------------------------------------
    def _open_suggestions(self) -> None:
        dlg = SuggestionsDialog(self)
        if dlg.exec():
            added = 0
            for kind, ident in dlg.chosen():
                got = self.resolve(kind, ident)
                if got is not None:
                    before = len(self.targets)
                    self.add_target(*got)
                    added += len(self.targets) - before
            if added:
                self.statusBar().showMessage(
                    self.tr("{n} alvo(s) acrescentado(s) à sessão").format(n=added), 5000)

    def agenda_text(self) -> str:
        plan = self.plan
        if plan is None:
            return ""
        lines = [f"Sessão de astrofoto — noite de {to_local(self.when):%d/%m/%Y}"]
        for b in plan.blocks:
            lines.append(f"{to_local(b.start):%H:%M}–{to_local(b.end):%H:%M}  "
                         f"{plan.targets[b.target].name}  ({b.alt_min:.0f}–{b.alt_max:.0f}°)"
                         + ("  → virar a montagem" if b.flip_after else ""))
        return "\n".join(lines)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.agenda_text())

    def _goto(self) -> None:
        r = self.list.currentRow()
        if 0 <= r < len(self.targets):
            self.gotoTarget.emit(self.targets[r].kind, self.targets[r].ident)


class MarginsDialog(QDialog):
    """Margem de subs perdidas por faixa de duração da sub (editável)."""

    def __init__(self, table, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Margem para subs perdidas"))
        self.resize(420, 360)
        lay = QVBoxLayout(self)
        intro = QLabel(self.tr(
            "Quanto a mais fotografar para compensar as subs estragadas por vento, "
            "nuvens, satélites ou falhas de guiagem. Subs longas perdem mais: uma "
            "rajada estraga a sub inteira. A última faixa vale para tudo acima."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels([self.tr("Sub até (s)"), self.tr("Margem (%)")])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        lay.addWidget(self.tbl, 1)
        for lim, pct in table:
            self._add_row(lim, pct)
        row = QHBoxLayout()
        add = QPushButton(self.tr("+ Faixa"))
        add.clicked.connect(self._add_new)
        rem = QPushButton(self.tr("Remover faixa"))
        rem.clicked.connect(self._remove)
        reset = QPushButton(self.tr("Padrão"))
        reset.clicked.connect(self._reset)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        row.addWidget(reset)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add_row(self, lim, pct) -> None:
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        sp_lim = QSpinBox()
        sp_lim.setRange(0, 3600)
        sp_lim.setSpecialValueText(self.tr("acima (resto)"))
        sp_lim.setSuffix(" s")
        sp_lim.setValue(0 if lim is None else int(lim))
        sp_pct = QDoubleSpinBox()
        sp_pct.setRange(0.0, 90.0)
        sp_pct.setDecimals(0)
        sp_pct.setSuffix(" %")
        sp_pct.setValue(float(pct))
        self.tbl.setCellWidget(r, 0, sp_lim)
        self.tbl.setCellWidget(r, 1, sp_pct)

    def _add_new(self) -> None:
        tb = self.table()
        closed = [lim for lim, _p in tb if lim is not None]
        nxt = (max(closed) + 60) if closed else 60
        pct = tb[-1][1] if tb else 10.0
        self._add_row(nxt, pct)

    def _remove(self) -> None:
        r = self.tbl.currentRow()
        if r < 0:
            r = self.tbl.rowCount() - 1
        if self.tbl.rowCount() > 1 and r >= 0:
            self.tbl.removeRow(r)

    def _reset(self) -> None:
        from ..core.exposure import DEFAULT_MARGINS

        self.tbl.setRowCount(0)
        for lim, pct in DEFAULT_MARGINS:
            self._add_row(lim, pct)

    def table(self) -> list:
        """[(limite s ou None, %)], em ordem, com a faixa aberta no fim."""
        from ..core.exposure import normalize_margins

        rows = []
        for r in range(self.tbl.rowCount()):
            lim = self.tbl.cellWidget(r, 0).value()
            rows.append((None if lim == 0 else float(lim), float(self.tbl.cellWidget(r, 1).value())))
        return normalize_margins(rows)

    def _accept(self) -> None:
        self.accept()


KLASS_GROUPS = {"GAL": ("GAL",), "NEB": ("NEB", "PN", "DARK"), "CLUSTER": ("OC", "GC")}


class SuggestionsDialog(QDialog):
    """Os alvos mais bem posicionados na noite da sessão, com as fotos do
    catálogo: o usuário marca um ou mais e eles entram na sessão."""

    def __init__(self, session: "SessionWindow") -> None:
        super().__init__(session)
        self.session = session
        self.setWindowTitle(self.tr("Sugestões de alvos para a noite"))
        self.resize(1000, 700)
        lay = QVBoxLayout(self)
        self.header = QLabel()
        self.header.setWordWrap(True)
        lay.addWidget(self.header)
        frow = QHBoxLayout()
        frow.addWidget(QLabel(self.tr("Mostrar:")))
        self.cb_kind = QComboBox()
        for key, label in (("", self.tr("todos os tipos")), ("GAL", self.tr("galáxias")),
                           ("NEB", self.tr("nebulosas")), ("CLUSTER", self.tr("aglomerados"))):
            self.cb_kind.addItem(label, key)
        self.cb_kind.currentIndexChanged.connect(self._fill)
        frow.addWidget(self.cb_kind)
        self.cb_fit = QComboBox()
        self.cb_fit.addItem(self.tr("qualquer tamanho"), "")
        self.cb_fit.addItem(self.tr("só os que cabem no campo do setup"), "fit")
        self.cb_fit.currentIndexChanged.connect(self._fill)
        frow.addWidget(self.cb_fit)
        frow.addStretch(1)
        lay.addLayout(frow)
        self.view = QListWidget()
        self.view.setViewMode(QListView.IconMode)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Static)
        self.view.setIconSize(QSize(170, 170))
        self.view.setGridSize(QSize(200, 262))
        self.view.setWordWrap(True)
        self.view.setSpacing(4)
        self.view.setSelectionMode(QAbstractItemView.NoSelection)
        self.view.itemClicked.connect(self._toggle)
        self.view.itemChanged.connect(self._update_button)
        lay.addWidget(self.view, 1)
        bb = QDialogButtonBox()
        self.btn_add = bb.addButton(self.tr("Adicionar à sessão"), QDialogButtonBox.AcceptRole)
        bb.addButton(self.tr("Fechar"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._rank()
        self._fill()

    # ------------------------------------------------------------------
    def _rank(self) -> None:
        from ..catalogs.equipment import fit_in_field

        sess = self.session
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            cands = [c for c in sess.candidates()
                     if not any(t.ident == c["ident"] for t in sess.targets)]
            opt = sess.options()
            hours, altmax, qmean, _times = S.rank_candidates(
                sess.engine, [c["icrs"] for c in cands], sess.when, opt, sess.horizon())
        finally:
            QApplication.restoreOverrideCursor()
        shape = None
        s = sess.setup()
        if s is not None and sess.equipment is not None:
            shape = s.camera_shape(sess.equipment)
        rows = []
        for c, h, am, q in zip(cands, hours, altmax, qmean):
            if h < 1.0:
                continue
            fit = None
            if shape is not None and c.get("maj"):
                fit = fit_in_field(float(c["maj"]), c.get("min"), shape)
            # horas × qualidade média, com peso para o que rende foto: tamanho
            # (15′ ou mais vale inteiro), brilho e um bônus aos famosos
            maj = float(c.get("maj") or 0.0)
            mag = float(c.get("mag") if c.get("mag") is not None else 12.0)
            w_size = 0.4 + 0.6 * min(1.0, maj / 15.0)
            w_mag = 1.0 if mag <= 10.0 else max(0.6, 1.0 - 0.1 * (mag - 10.0))
            score = (float(h) * float(q) * w_size * w_mag
                     * (1.15 if c.get("common") else 1.0))
            rows.append((score, c, float(h), float(am), fit))
        rows.sort(key=lambda r: r[0], reverse=True)
        self.rows = rows
        night = to_local(sess.when).date()
        kind = sess.cb_mount.currentText()
        self.header.setText(self.tr(
            "<b>Noite de {d:%d/%m/%Y}</b> — os alvos com mais horas boas no céu escuro "
            "(acima de {a}°, {k}), considerando a Lua e o horizonte. Clique nas fotos para "
            "marcar.").format(d=night, a=int(opt.min_alt), k=kind))

    def _fill(self, *_a) -> None:
        from ..catalogs.images import image_path_for

        want = self.cb_kind.currentData()
        only_fit = self.cb_fit.currentData() == "fit"
        self.view.blockSignals(True)
        self.view.clear()
        shown = 0
        for _score, c, h, am, fit in self.rows:
            klass = (c.get("klass") or "").upper()
            if want and klass not in KLASS_GROUPS[want]:
                continue
            if only_fit and (fit is None or not fit["fits"]):
                continue
            path = image_path_for(c["name"])
            if path is None:
                continue
            pm = QPixmap(str(path))
            if pm.isNull():
                continue
            lines = [c["label"], f"{c.get('type_label', '')}".strip(),
                     f"{num(h, 1)} h boas · máx. {am:.0f}°"]
            if fit is not None:
                cols, rws = fit["mosaic"]
                lines.append("cabe no campo" if fit["fits"]
                             else f"mosaico {cols}×{rws}")
            item = QListWidgetItem(QIcon(pm.scaled(170, 170, Qt.KeepAspectRatio,
                                                   Qt.SmoothTransformation)),
                                   "\n".join(x for x in lines if x))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, (c["kind"], c["ident"]))
            item.setToolTip(c["label"])
            self.view.addItem(item)
            shown += 1
            if shown >= 40:
                break
        if not shown:
            item = QListWidgetItem(self.tr("Nenhum alvo com pelo menos 1 h boa nesta noite."))
            item.setFlags(Qt.NoItemFlags)
            self.view.addItem(item)
        self.view.blockSignals(False)
        self._update_button()

    def _toggle(self, item) -> None:
        if item.flags() & Qt.ItemIsUserCheckable:
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def _update_button(self, *_a) -> None:
        n = len(self.chosen())
        self.btn_add.setEnabled(n > 0)
        self.btn_add.setText(self.tr("Adicionar à sessão ({n})").format(n=n) if n
                             else self.tr("Adicionar à sessão"))

    def chosen(self) -> list[tuple[str, str]]:
        out = []
        for i in range(self.view.count()):
            it = self.view.item(i)
            if it.checkState() == Qt.Checked and it.data(Qt.UserRole):
                out.append(tuple(it.data(Qt.UserRole)))
        return out

