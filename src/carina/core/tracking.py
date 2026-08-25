"""Trajetória de um objeto ao longo da noite (rastreamento noturno).

Amostra o caminho aparente entre o pôr e o nascer do Sol, classificando cada
ponto por: banda de crepúsculo (civil/náutica/astronômica), altitude e
proximidade da Lua. Só pontos acima do horizonte entram no resultado.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np

from .eclipses import moon_influence_radii
from .twilight import NightInfo, night_info, sun_altitude_band


@dataclass
class TrackPoint:
    """Uma amostra da trajetória noturna: posição horizontal, faixa de
    crepúsculo em vigor e situação em relação à Lua."""

    when_utc: dt.datetime
    az: float          # radianos
    alt: float         # radianos
    band: str          # 'day' | 'civil' | 'nautical' | 'astro'
    moon_sep: float    # radianos (π se a Lua está abaixo do horizonte)
    moon_affected: bool


@dataclass
class TrackResult:
    """Trajetória completa de um objeto ao longo de uma noite, com os
    momentos-chave (nascer, culminação, ocaso) já destacados."""

    label: str
    points: list[TrackPoint] = field(default_factory=list)
    night: NightInfo | None = None
    rise_utc: dt.datetime | None = None   # instante em que sobe ao horizonte
    set_utc: dt.datetime | None = None    # instante em que desce
    max_alt: float = 0.0
    max_alt_utc: dt.datetime | None = None
    moon_illum: float = 0.0

    def visible(self) -> bool:
        """O objeto sobe do horizonte em algum momento da noite?"""
        return bool(self.points)


def _object_vector(engine, selection, t):
    """Vetor unitário horizontal do objeto no instante t."""
    kind, key = selection
    if kind == "body":
        state = next((b for b in engine.bodies(t) if b.name == key), None)
        return state.vec if state else None
    m = engine.horizontal_matrix(t)
    if kind == "star":
        return engine.star_xyz_cache[int(key)] @ m.T
    return engine.dso_xyz_cache[int(key)] @ m.T


def compute_track(engine, selection, label: str, icrs_vec,
                  ref_utc: dt.datetime, step_minutes: float = 10.0,
                  low_alt_thresholds=(20.0, 30.0, 45.0)) -> TrackResult:
    """Calcula a trajetória do objeto na noite que contém ``ref_utc``.

    ``icrs_vec`` é o vetor unitário J2000 para estrelas/DSO; para corpos do
    Sistema Solar pode ser None (a posição é recalculada em cada instante).
    """
    info = night_info(engine, ref_utc)
    result = TrackResult(label=label, night=info)

    start = info.sunset
    end = info.sunrise
    if start is None or end is None:
        from .localtime import to_local

        local = to_local(ref_utc)
        base = local.replace(hour=18, minute=0, second=0, microsecond=0)
        start = base.astimezone(dt.timezone.utc)
        end = start + dt.timedelta(hours=12)
    if end <= start:
        end = start + dt.timedelta(hours=12)

    n = max(2, int((end - start).total_seconds() / (step_minutes * 60.0)) + 1)
    times_utc = [start + dt.timedelta(minutes=step_minutes * i) for i in range(n)]
    ts = engine.ts.from_datetimes(times_utc)

    obs = engine.site.at(ts)
    sun_alt = obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees
    moon_app = obs.observe(engine.eph["moon"]).apparent()
    moon_alt, moon_az, _ = moon_app.altaz()
    moon_illum = float(engine.moon_illumination(engine.ts.from_datetime(ref_utc)))
    r_crit, _ = moon_influence_radii(moon_illum)

    kind = selection[0]
    if kind == "body":
        app = obs.observe(engine.eph[engine.body_key(selection[1])]).apparent()
        alt_arr, az_arr, _ = app.altaz()
        alts = np.radians(alt_arr.degrees)
        azs = np.radians(az_arr.degrees)
    else:
        alts = np.empty(n)
        azs = np.empty(n)
        for i, ti in enumerate(ts):
            m = engine.horizontal_matrix(ti)
            v = np.asarray(icrs_vec) @ m.T
            alts[i] = math.asin(max(-1.0, min(1.0, float(v[2]))))
            azs[i] = math.atan2(float(v[1]), float(v[0])) % (2 * math.pi)

    moon_alt_rad = np.radians(moon_alt.degrees)
    moon_az_rad = np.radians(moon_az.degrees)
    cos_sep = (
        np.sin(alts) * np.sin(moon_alt_rad)
        + np.cos(alts) * np.cos(moon_alt_rad) * np.cos(azs - moon_az_rad)
    )
    seps = np.arccos(np.clip(cos_sep, -1.0, 1.0))

    prev_up = False
    for i, when in enumerate(times_utc):
        up = alts[i] > 0.0
        if up and not prev_up and result.rise_utc is None and i > 0:
            result.rise_utc = when
        if not up and prev_up and result.set_utc is None:
            result.set_utc = when
        prev_up = up
        if not up:
            continue
        moon_up = moon_alt_rad[i] > 0.0
        sep = float(seps[i]) if moon_up else math.pi
        result.points.append(
            TrackPoint(
                when_utc=when,
                az=float(azs[i]),
                alt=float(alts[i]),
                band=sun_altitude_band(float(sun_alt[i])),
                moon_sep=sep,
                moon_affected=bool(moon_up and sep < r_crit),
            )
        )
        if alts[i] > result.max_alt:
            result.max_alt = float(alts[i])
            result.max_alt_utc = when

    if result.points:
        if result.rise_utc is None and alts[0] > 0:
            result.rise_utc = times_utc[0]
        if result.set_utc is None and alts[-1] > 0:
            result.set_utc = times_utc[-1]
    result.moon_illum = moon_illum
    return result
