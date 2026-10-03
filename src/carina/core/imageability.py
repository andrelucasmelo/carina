"""Calendário de imageabilidade (v0.19 T3): horas úteis por noite no ano.

Para um alvo, quantas horas por noite ele fica **acima da altitude mínima,
com o céu escuro e longe da Lua** — a pergunta de quem planeja juntar
horas de integração ao longo de semanas. Vetorizado: uma passada para o
ano inteiro, amostrando cada noite a cada 15 min.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

UTC = dt.timezone.utc


@dataclass
class Imageability:
    dates: list            # datas locais (início da noite)
    hours: np.ndarray      # horas úteis por noite
    dark_hours: np.ndarray  # horas de céu escuro (para referência)

    def best_months(self, top: int = 3) -> list[int]:
        months = {}
        for d, h in zip(self.dates, self.hours):
            months.setdefault(d.month, []).append(h)
        ranked = sorted(months, key=lambda m: -float(np.mean(months[m])))
        return ranked[:top]

    def next_nights(self, start: dt.date, n: int = 60) -> list[float]:
        return [float(h) for d, h in zip(self.dates, self.hours) if d >= start][:n]


def compute(engine, icrs: np.ndarray, start: dt.datetime, days: int = 366,
            step_days: int = 1, min_alt: float = 30.0, dark_sun: float = -18.0,
            moon_sep_min: float = 40.0, horizon=None, zenith_limit: float | None = None,
            minutes: float = 15.0) -> Imageability:
    """Horas úteis por noite para a direção ICRS ``icrs`` (unitário)."""
    from .localtime import from_local_naive, to_local

    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    day0 = to_local(start).date()
    dates = [day0 + dt.timedelta(days=k) for k in range(0, days, step_days)]
    offsets = np.arange(0, 24 * 60, minutes)                  # meio-dia a meio-dia
    times = []
    for d in dates:
        noon = from_local_naive(dt.datetime.combine(d, dt.time(12))).astimezone(UTC)
        times.extend(noon + dt.timedelta(minutes=float(m)) for m in offsets)
    t = engine.ts.from_datetimes(times)
    obs = engine.site.at(t)
    sun_alt = np.asarray(obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees)
    moon = obs.observe(engine.eph["moon"]).apparent()
    malt = np.asarray(moon.altaz()[0].degrees)
    mvec = np.asarray(moon.position.au, np.float64)
    mvec /= np.linalg.norm(mvec, axis=0)
    # altitude do alvo: matrizes ICRS→horizontal vetorizadas
    rows = []
    for alt_deg, az_deg in ((0.0, 0.0), (0.0, 90.0), (90.0, 0.0)):
        p = obs.from_altaz(alt_degrees=alt_deg, az_degrees=az_deg).position.au
        rows.append(np.asarray(p) / np.linalg.norm(p, axis=0))
    v = np.stack([r.T @ icrs for r in rows])                  # (3, N) horizontal
    alt = np.degrees(np.arcsin(np.clip(v[2], -1, 1)))
    az = np.degrees(np.arctan2(v[1], v[0])) % 360.0
    from skyfield import almanac

    illum = np.asarray(almanac.fraction_illuminated(engine.eph, "moon", t))
    sep = np.degrees(np.arccos(np.clip(icrs @ mvec, -1, 1)))
    # a Lua só atrapalha se estiver acima do horizonte e razoavelmente cheia
    moon_bad = (malt > 0) & (illum > 0.35) & (sep < moon_sep_min + 40 * (illum - 0.35))
    ok = (alt >= min_alt) & (sun_alt <= dark_sun) & ~moon_bad
    if zenith_limit is not None:
        ok &= alt <= zenith_limit
    if horizon is not None:
        ok &= alt > np.asarray(horizon.altitude_at(az))
    shape = (len(dates), len(offsets))
    hours = ok.reshape(shape).sum(axis=1) * minutes / 60.0
    dark = (sun_alt <= dark_sun).reshape(shape).sum(axis=1) * minutes / 60.0
    return Imageability(dates, hours, dark)
