"""Caminho do Sol e analema (v0.22 T7).

- **Caminho do Sol no dia**: a posição do Sol a cada 10 minutos, do nascer
  ao ocaso (e abaixo do horizonte, se a camada mostrar);
- **Analema**: o Sol à mesma hora local (do relógio, sem horário de verão)
  a cada 5 dias do ano — o "8" que ele desenha no céu, com cerca de 47° de
  altura (a inclinação do eixo da Terra, duas vezes) e uns 8° de largura
  (a equação do tempo);
- **Tabela do ano**: nascer e ocaso com o azimute, e a duração do dia,
  semana a semana.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

UTC = dt.timezone.utc


def _sun_vectors(engine, times: list[dt.datetime]) -> np.ndarray:
    """Vetores horizontais unitários do Sol (sem refração), (N, 3)."""
    t = engine.ts.from_datetimes(times)
    app = engine.site.at(t).observe(engine.eph["sun"]).apparent()
    alt, az, _d = app.altaz()
    a, z = np.radians(alt.degrees), np.radians(az.degrees)
    return np.stack([np.cos(a) * np.cos(z), np.cos(a) * np.sin(z), np.sin(a)], axis=1)


def sun_path_day(engine, day: dt.date, step_min: int = 10) -> np.ndarray:
    """Sol de 0h a 24h locais da data (vetores horizontais)."""
    from .localtime import from_local_naive

    t0 = from_local_naive(dt.datetime(day.year, day.month, day.day)).astimezone(UTC)
    times = [t0 + dt.timedelta(minutes=step_min * k) for k in range(24 * 60 // step_min + 1)]
    return _sun_vectors(engine, times)


def analemma(engine, year: int, local_hour: float = 12.0, step_days: int = 5) -> np.ndarray:
    """Sol à mesma hora local (offset padrão do fuso, sem horário de verão)."""
    from .localtime import from_local_naive

    jan = from_local_naive(dt.datetime(year, 1, 15, 12))
    offset = jan.utcoffset() or dt.timedelta(0)              # fuso padrão (sem verão)
    h, m = int(local_hour), int(round((local_hour % 1) * 60))
    times = []
    d = dt.datetime(year, 1, 1, h, m)
    while d.year == year:
        times.append((d - offset).replace(tzinfo=UTC))
        d += dt.timedelta(days=step_days)
    return _sun_vectors(engine, times)


@dataclass
class SunDay:
    date: dt.date
    sunrise: dt.datetime | None
    sunrise_az: float | None
    sunset: dt.datetime | None
    sunset_az: float | None

    @property
    def day_length_h(self) -> float | None:
        if self.sunrise is None or self.sunset is None:
            return None
        return (self.sunset - self.sunrise).total_seconds() / 3600.0


def year_table(engine, year: int, step_days: int = 7) -> list[SunDay]:
    """Nascer e ocaso (com azimute) ao longo do ano."""
    from skyfield import almanac

    from .localtime import from_local_naive

    out = []
    d = dt.date(year, 1, 1)
    f = almanac.sunrise_sunset(engine.eph, engine.topos)
    while d.year == year:
        t0 = from_local_naive(dt.datetime(d.year, d.month, d.day)).astimezone(UTC)
        times, states = almanac.find_discrete(engine.ts.from_datetime(t0),
                                              engine.ts.from_datetime(t0 + dt.timedelta(days=1)), f)
        rise = sett = None
        for ti, si in zip(times, states):
            if int(si) == 1 and rise is None:
                rise = ti.utc_datetime()
            elif int(si) == 0 and sett is None:
                sett = ti.utc_datetime()
        az = {}
        for key, when in (("r", rise), ("s", sett)):
            if when is not None:
                v = _sun_vectors(engine, [when])[0]
                az[key] = math.degrees(math.atan2(v[1], v[0])) % 360.0
        out.append(SunDay(d, rise, az.get("r"), sett, az.get("s")))
        d += dt.timedelta(days=step_days)
    return out


def analemma_extent(vecs: np.ndarray) -> tuple[float, float]:
    """(comprimento, largura) do "8" em graus de céu — para conferir o analema.

    Comprimento: a maior separação entre dois pontos (≈ 2 × 23,44°); largura:
    o dobro do maior afastamento dos pontos ao grande círculo que liga esses
    dois extremos (a equação do tempo). Medido em ângulo, não em azimute,
    porque perto do zênite o azimute não significa nada.
    """
    v = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    dots = np.clip(v @ v.T, -1.0, 1.0)
    i, j = np.unravel_index(np.argmin(dots), dots.shape)
    length = math.degrees(math.acos(dots[i, j]))
    axis = np.cross(v[i], v[j])
    axis /= np.linalg.norm(axis)
    dev = np.degrees(np.arcsin(np.clip(v @ axis, -1.0, 1.0)))
    return length, float(2 * np.abs(dev).max())
