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
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QPushButton, QSpinBox, QSplitter, QTextBrowser,
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
            if plan.meridian[i] is not None and not opt.altaz:
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
        self.img = None
        self.title = ""

    def set_data(self, img, title: str) -> None:
        self.img, self.title = img, title
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
        hmax = max(8.0, float(hours.max()) if n else 8.0)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(150, 160, 180))
        p.drawText(QRectF(4, 2, self.width() - 8, 14), Qt.AlignLeft, self.title)
        for k, hh in enumerate(hours):
            x = left + w * k / max(n, 1)
            bh = h * hh / hmax
            col = QColor(90, 170, 110) if hh >= 3 else QColor(200, 170, 80) if hh > 0.5 \
                else QColor(70, 70, 80)
            p.fillRect(QRectF(x, top + h - bh, max(1.0, w / n), bh), col)
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

    def __init__(self, engine, when_utc: dt.datetime, parent=None, *, equipment=None,
                 userdata=None, bortle=lambda: 5, horizon=lambda: None,
                 current_target=lambda: None, active_setup: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sessão de astrofotografia"))
        self.engine = engine
        self.when = when_utc
        self.equipment = equipment
        self.userdata = userdata
        self.bortle = bortle
        self.horizon = horizon
        self.current_target = current_target
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
        tl.addWidget(rem)
        tf = QFormLayout()
        tf.addRow(self.tr("Prioridade:"), self.sp_prio)
        tf.addRow(self.tr("Horas nesta noite:"), self.sp_hours)
        tl.addLayout(tf)

        # --- setup e regras -------------------------------------------------
        self.cb_setup = QComboBox()
        self.cb_setup.currentIndexChanged.connect(self._setup_changed)
        self.chk_altaz = QCheckBox(self.tr("Montagem altazimutal (evitar o zênite)"))
        self.chk_altaz.toggled.connect(self.recompute)
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
        sf.addRow(self.tr("Setup:"), self.cb_setup)
        sf.addRow(self.chk_altaz)
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
    def _fill_setups(self, active: str) -> None:
        from ..catalogs.equipment import setup_names

        self.cb_setup.blockSignals(True)
        self.cb_setup.clear()
        self.cb_setup.addItem(self.tr("(nenhum — sem estimativa de exposição)"), "")
        names = setup_names(self.userdata) if self.userdata is not None else []
        for n in names:
            self.cb_setup.addItem(n, n)
        self.cb_setup.setCurrentIndex(max(0, self.cb_setup.findData(active)))
        self.cb_setup.blockSignals(False)
        self._setup_changed()

    def setup(self):
        from ..catalogs.equipment import load_setup

        name = self.cb_setup.currentData()
        return load_setup(name, self.userdata) if name and self.userdata is not None else None

    def _setup_changed(self, *_a) -> None:
        s = self.setup()
        if s is not None and self.equipment is not None:
            self.chk_altaz.blockSignals(True)
            self.chk_altaz.setChecked(s.is_altaz(self.equipment))
            self.chk_altaz.blockSignals(False)
        self.recompute()

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
        return S.SessionOptions(min_alt=float(self.sp_minalt.value()),
                                dark_sun=float(self.cb_dark.currentData()),
                                altaz=self.chk_altaz.isChecked(),
                                zenith_limit=float(self.sp_zen.value()),
                                meridian_margin_min=float(self.sp_mer.value()))

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

    def _exposure_html(self) -> str:
        from ..core.exposure import BORTLE_SQM, suggest_sub

        s = self.setup()
        if s is None or self.equipment is None:
            return ("<p style='color:#9aa'>Escolha um setup salvo (com câmera) para ver a "
                    "sub-exposição sugerida. Os setups são criados em Planejar ▸ Campo de "
                    "visão.</p>")
        scope = self.equipment.find("telescopes", s.telescope)
        cam = self.equipment.find("cameras", s.camera)
        if scope is None or cam is None:
            return "<p style='color:#9aa'>O setup não tem telescópio e câmera.</p>"
        bortle = int(self.bortle())
        adv = suggest_sub(BORTLE_SQM.get(bortle, 20.0), scope, cam,
                          self.equipment.find("accessories", s.accessory),
                          altaz=self.chk_altaz.isChecked())
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
            if not plan.options.altaz:
                mers = [(plan.targets[i].name, m) for i, m in enumerate(plan.meridian) if m]
                if mers:
                    html.append("<p style='color:#9aa'>Meridiano: " + "; ".join(
                        f"{n} às {to_local(m):%H:%M}" for n, m in mers) + ".</p>")
        for note in plan.notes:
            if note:
                html.append(f"<p style='color:#d97'>{note}</p>")
        html.append(self._exposure_html())
        # noites para a meta
        if self.targets:
            from ..core.exposure import nights_for

            goal = self.sp_goal.value()
            html.append(f"<h4>Para juntar {num(goal, 0)} h por alvo</h4><ul>")
            for i, t in enumerate(self.targets):
                img = self._imageability(i)
                nights = img.next_nights(to_local(self.when).date(), 120)
                share = max(1, len(self.targets))
                # cada amostra do calendário vale por 2 noites (passo de 2 dias)
                k = nights_for(goal, [2.0 * h / share for h in nights])
                txt = (f"cerca de {k * 2} noites corridas" if k else "mais de 8 meses")
                html.append(f"<li><b>{t.name}</b>: {txt} (dividindo a noite entre "
                            f"{share} alvo{'s' if share > 1 else ''})</li>")
            html.append("</ul>")
        self.details.setHtml("".join(html) or "<p>Acrescente alvos.</p>")

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
