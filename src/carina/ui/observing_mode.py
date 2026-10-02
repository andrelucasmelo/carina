"""Modo observação (v0.16 T5) — Exibir ▸ Modo observação.

Para usar ao lado do telescópio: os painéis somem, os rótulos do céu
crescem e um cartão no canto mostra o **próximo alvo** do roteiro aberto
— nome, hora da parada com cronômetro regressivo, altura e direção,
instrumento — com botões para ir até ele, marcar como observado e andar
pelo roteiro.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

LABEL_SCALE = 1.45


def next_index(plan, now: dt.datetime) -> int:
    """Índice da parada atual (ainda dentro do tempo dela) ou da próxima."""
    if plan is None or not plan.entries:
        return -1
    step = dt.timedelta(minutes=plan.minutes_per_object)
    for i, e in enumerate(plan.entries):
        if e.when_utc + step > now:
            return i
    return len(plan.entries) - 1


def countdown(when: dt.datetime, now: dt.datetime, minutes: int) -> str:
    """"em 12 min" · "agora (restam 3 min)" · "há 40 min"."""
    delta = (when - now).total_seconds() / 60.0
    if delta > 0.5:
        h, m = divmod(int(round(delta)), 60)
        return f"em {h} h {m:02d} min" if h else f"em {m} min"
    if delta > -minutes:
        left = max(0, int(round(minutes + delta)))
        return f"agora (restam {left} min)"
    ago = int(round(-delta))
    h, m = divmod(ago, 60)
    return f"há {h} h {m:02d} min" if h else f"há {m} min"


class NextTargetCard(QFrame):
    """Cartão flutuante sobre o céu com o próximo alvo do roteiro."""

    gotoRequested = Signal(str, str, object)       # (kind, ident, horário)
    observedRequested = Signal(str, str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.plan = None
        self.index = -1
        self._manual = False
        self.setObjectName("nextTarget")
        self.setStyleSheet(
            "#nextTarget { background: rgba(12, 16, 28, 225); border: 1px solid "
            "rgba(120, 140, 180, 160); border-radius: 10px; }"
            "#nextTarget QLabel { color: rgb(225, 230, 242); }")
        self.head = QLabel()
        self.head.setStyleSheet("font-size: 11pt; color: rgb(150, 165, 195);")
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 17pt; font-weight: 600;")
        self.name.setWordWrap(True)
        self.when = QLabel()
        self.when.setStyleSheet("font-size: 14pt;")
        self.where = QLabel()
        self.where.setStyleSheet("font-size: 12pt;")
        self.where.setWordWrap(True)
        b_prev, b_go, b_obs, b_next = (QPushButton(t) for t in
                                       ("◀", self.tr("Ir para"), self.tr("✓ Observado"), "▶"))
        for b in (b_prev, b_go, b_obs, b_next):
            b.setMinimumHeight(34)
            b.setStyleSheet("font-size: 11pt;")
        b_prev.clicked.connect(lambda: self.step(-1))
        b_next.clicked.connect(lambda: self.step(+1))
        b_go.clicked.connect(lambda: self._emit(self.gotoRequested))
        b_obs.clicked.connect(lambda: self._emit(self.observedRequested))
        row = QHBoxLayout()
        for b in (b_prev, b_go, b_obs, b_next):
            row.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        for w in (self.head, self.name, self.when, self.where):
            lay.addWidget(w)
        lay.addLayout(row)
        self.setFixedWidth(430)

    def set_plan(self, plan) -> None:
        self.plan = plan
        self.index = -1
        self._manual = False

    def step(self, delta: int) -> None:
        if self.plan is None or not self.plan.entries:
            return
        self.index = max(0, min(len(self.plan.entries) - 1, self.index + delta))
        self._manual = True
        self.tick(self._last_now)

    def current(self):
        if self.plan is None or not (0 <= self.index < len(self.plan.entries)):
            return None
        return self.plan.entries[self.index]

    def _emit(self, signal) -> None:
        e = self.current()
        if e is not None:
            signal.emit(e.kind, e.ident, e.when_utc)

    _last_now = None

    def tick(self, now: dt.datetime) -> None:
        """Atualiza o cartão (chamado a cada segundo pela janela principal)."""
        from ..core.localtime import to_local
        from ..core.observing import INSTRUMENT_LABEL

        self._last_now = now
        if self.plan is None or not self.plan.entries:
            self.head.setText(self.tr("Modo observação"))
            self.name.setText(self.tr("Nenhum roteiro aberto"))
            self.when.setText(self.tr("Abra um em Planejar ▸ Roteiros ou Hoje à noite (T)."))
            self.where.setText("")
            return
        if not self._manual or self.index < 0:
            self.index = next_index(self.plan, now)
        e = self.plan.entries[self.index]
        self.head.setText(self.tr("Parada {i} de {n} · {t}").format(
            i=self.index + 1, n=len(self.plan.entries), t=self.plan.title))
        self.name.setText(e.label)
        if self.plan.timed:
            self.when.setText(f"{to_local(e.when_utc):%H:%M} — "
                              f"{countdown(e.when_utc, now, self.plan.minutes_per_object)}")
        else:
            self.when.setText(self.tr("Sem horário (lista do período)"))
        where = (f"alt {e.altitude:.0f}° · az {e.azimuth:.0f}° · "
                 f"{INSTRUMENT_LABEL.get(e.instrument, e.instrument)}")
        if e.constellation:
            where += f" · {e.constellation}"
        self.where.setText(where)
