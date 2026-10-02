"""Calendário de noites escuras (v0.15 T12).

Para cada noite de um mês: quantas horas de noite astronômica (Sol abaixo
de −18°) e quantas delas **sem a Lua** acima do horizonte, além da fase.
É a pergunta de quem vai viajar para um céu escuro: "qual fim de semana
vale a pena?".

O mês inteiro é calculado numa passada só, vetorizada: amostras a cada
10 min da tarde do primeiro dia à manhã seguinte ao último, altitude do
Sol e da Lua por ``observe`` com tempo vetorial. Cada amostra pertence à
noite cuja data local é a da tarde (hora local − 12 h).
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

import numpy as np

STEP_MIN = 10.0


@dataclass
class DarkNight:
    date: dt.date                 # data local do início da noite
    astro_minutes: float
    moonless_minutes: float
    moon_illum: float             # na meia-noite local
    phase_deg: float              # 0 nova, 90 quarto crescente, 180 cheia
    phase_name: str

    @property
    def moonless_hours(self) -> float:
        return self.moonless_minutes / 60.0


def month_nights(engine, year: int, month: int) -> list[DarkNight]:
    """Uma :class:`DarkNight` por dia do mês (horário local do observador)."""
    from skyfield import almanac

    from .localtime import from_local_naive
    from .tonight import PHASES

    days = calendar.monthrange(year, month)[1]
    start_local = dt.datetime(year, month, 1, 12, 0)
    start = from_local_naive(start_local).astimezone(dt.timezone.utc)
    n = int(days * 24 * 60 / STEP_MIN) + 1
    times = [start + dt.timedelta(minutes=STEP_MIN * i) for i in range(n)]
    ts = engine.ts.from_datetimes(times)
    obs = engine.site.at(ts)
    sun = obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees
    moon = obs.observe(engine.eph["moon"]).apparent().altaz()[0].degrees
    astro = np.asarray(sun) < -18.0
    moonless = astro & (np.asarray(moon) < 0.0)
    # índice da noite: dias desde o meio-dia local do dia 1
    night_idx = (np.arange(n) * STEP_MIN // (24 * 60)).astype(int)

    mids = [from_local_naive(dt.datetime(year, month, d, 12, 0) + dt.timedelta(hours=12))
            .astimezone(dt.timezone.utc) for d in range(1, days + 1)]
    t_mid = engine.ts.from_datetimes(mids)
    illum = np.asarray(almanac.fraction_illuminated(engine.eph, "moon", t_mid))
    phase = np.asarray(almanac.moon_phase(engine.eph, t_mid).degrees) % 360.0

    out = []
    for d in range(days):
        sel = night_idx == d
        name = next(label for limit, label in PHASES if phase[d] < limit)
        out.append(DarkNight(
            date=dt.date(year, month, d + 1),
            astro_minutes=float(astro[sel].sum() * STEP_MIN),
            moonless_minutes=float(moonless[sel].sum() * STEP_MIN),
            moon_illum=float(illum[d]), phase_deg=float(phase[d]), phase_name=name,
        ))
    return out


BEST_MIN_HOURS = 8.0     # "melhor noite": mais de 8 h de noite astronômica sem Lua


def best_nights(nights: list[DarkNight], min_hours: float = BEST_MIN_HOURS) -> list[DarkNight]:
    """Noites com mais de ``min_hours`` horas escuras sem Lua, em ordem de data.

    Critério absoluto (pedido do usuário, pré-0.17): num mês sem nenhuma noite
    assim — verão em latitudes médias, quando a noite astronômica é curta —
    a lista fica vazia, em vez de promover noites medianas.
    """
    return [n for n in nights if n.moonless_minutes > min_hours * 60.0]


def darkest_night(nights: list[DarkNight]) -> DarkNight | None:
    """A noite com mais horas sem Lua (empate: a mais cedo)."""
    return min(nights, key=lambda n: (-round(n.moonless_minutes), n.date), default=None)
