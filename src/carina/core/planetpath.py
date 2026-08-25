"""Trajetória dos planetas no céu ao longo de um ano (item 8).

Calcula o caminho aparente entre as constelações em coordenadas equatoriais
(fixas), marca datas ao longo do percurso e localiza os eventos notáveis:
oposições e conjunções (planetas exteriores) ou elongações máximas
(Mercúrio e Vênus).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np

INNER = {"Mercúrio", "Vênus"}


@dataclass
class PathPoint:
    when_utc: dt.datetime
    vec: np.ndarray      # unitário ICRS (equatorial, fixo no céu)
    elongation: float    # separação angular ao Sol (rad)
    retrograde: bool


@dataclass
class PathEvent:
    when_utc: dt.datetime
    kind: str            # 'oposicao' | 'conjuncao' | 'elong_leste' | 'elong_oeste'
    value: float         # elongação (graus)
    vec: np.ndarray


@dataclass
class PlanetPath:
    name: str
    points: list[PathPoint] = field(default_factory=list)
    events: list[PathEvent] = field(default_factory=list)
    marks: list[int] = field(default_factory=list)   # índices marcados


def _icrs_from_apparent(engine, t, name: str) -> np.ndarray:
    """Direção aparente do corpo em ICRS (independe do observador local)."""
    app = engine.site.at(t).observe(engine.eph[engine.body_key(name)]).apparent()
    v = np.asarray(app.position.au, dtype=np.float64)
    return v / np.linalg.norm(v)


def compute_path(engine, name: str, start: dt.datetime, days: int = 365,
                 step_days: float = 1.0,
                 mark_degrees: float = 1.0) -> PlanetPath:
    """Caminho do planeta e eventos no período.

    ``mark_degrees``: distância angular percorrida entre marcas de data (o
    início de cada mês também é sempre marcado).
    """
    n = int(days / step_days) + 1
    times = [start + dt.timedelta(days=step_days * i) for i in range(n)]
    ts = engine.ts.from_datetimes(times)

    obs = engine.site.at(ts)
    body = obs.observe(engine.eph[engine.body_key(name)]).apparent()
    sun = obs.observe(engine.eph["sun"]).apparent()
    pos = np.asarray(body.position.au, dtype=np.float64).T   # (n,3)
    pos /= np.linalg.norm(pos, axis=1, keepdims=True)
    sun_pos = np.asarray(sun.position.au, dtype=np.float64).T
    sun_pos /= np.linalg.norm(sun_pos, axis=1, keepdims=True)
    elong = np.arccos(np.clip(np.sum(pos * sun_pos, axis=1), -1.0, 1.0))

    # ascensão reta para detectar movimento retrógrado
    ra = np.arctan2(pos[:, 1], pos[:, 0])
    dra = np.diff(np.unwrap(ra))
    retro = np.concatenate([[False], dra < 0])

    path = PlanetPath(name=name)
    for i, when in enumerate(times):
        path.points.append(
            PathPoint(when, pos[i], float(elong[i]), bool(retro[i]))
        )

    # --- marcas: a cada mark_degrees de deslocamento ou início de mês ---
    acc = 0.0
    last_month = None
    from .localtime import to_local

    for i in range(len(times)):
        local_month = to_local(times[i]).month
        month_changed = local_month != last_month
        if i > 0:
            acc += math.degrees(
                math.acos(max(-1.0, min(1.0, float(np.dot(pos[i], pos[i - 1])))))
            )
        if i == 0 or month_changed or acc >= mark_degrees:
            path.marks.append(i)
            if month_changed:
                last_month = local_month
            if acc >= mark_degrees:
                acc = 0.0

    # --- eventos ---
    if name in INNER:
        # elongações máximas: picos locais da elongação
        for i in range(1, len(elong) - 1):
            if elong[i] > elong[i - 1] and elong[i] >= elong[i + 1]:
                # leste = planeta a leste do Sol (visível ao anoitecer)
                dra_sun = math.atan2(
                    float(np.cross(sun_pos[i], pos[i])[2]),
                    float(np.dot(sun_pos[i], pos[i])),
                )
                kind = "elong_leste" if dra_sun > 0 else "elong_oeste"
                path.events.append(
                    PathEvent(times[i], kind, math.degrees(elong[i]), pos[i])
                )
    else:
        for i in range(1, len(elong) - 1):
            if elong[i] > elong[i - 1] and elong[i] >= elong[i + 1] and \
                    math.degrees(elong[i]) > 150:
                path.events.append(
                    PathEvent(times[i], "oposicao", math.degrees(elong[i]),
                              pos[i])
                )
            if elong[i] < elong[i - 1] and elong[i] <= elong[i + 1] and \
                    math.degrees(elong[i]) < 30:
                path.events.append(
                    PathEvent(times[i], "conjuncao", math.degrees(elong[i]),
                              pos[i])
                )
    return path


EVENT_LABEL = {
    "oposicao": "oposição", "conjuncao": "conjunção",
    "elong_leste": "elongação máx. leste", "elong_oeste": "elongação máx. oeste",
    "nova": "Lua nova", "crescente": "Quarto crescente",
    "cheia": "Lua cheia", "minguante": "Quarto minguante",
}


@dataclass
class MoonMark:
    when_utc: dt.datetime
    vec: np.ndarray          # unitário ICRS
    illumination: float      # 0..1
    phase_angle: float       # rad (ângulo Sol-Lua-Terra)
    bright_limb: float       # ângulo de posição do limbo iluminado (rad)
    phase_name: str = ""     # preenchido nas fases principais


def compute_moon_forecast(engine, start: dt.datetime, days: int = 28,
                          step_hours: float = 24.0) -> list[MoonMark]:
    """Posição e fase da Lua ao longo dos próximos dias (item 6).

    Uma marca por passo (padrão: uma por dia) com a fase desenhada, mais a
    identificação das quatro fases principais pelo instante mais próximo.
    """
    n = int(days * 24 / step_hours) + 1
    times = [start + dt.timedelta(hours=step_hours * i) for i in range(n)]
    ts = engine.ts.from_datetimes(times)

    obs = engine.site.at(ts)
    moon = obs.observe(engine.eph["moon"]).apparent()
    sun = obs.observe(engine.eph["sun"]).apparent()
    mpos = np.asarray(moon.position.au, dtype=np.float64).T
    spos = np.asarray(sun.position.au, dtype=np.float64).T
    mu = mpos / np.linalg.norm(mpos, axis=1, keepdims=True)
    su = spos / np.linalg.norm(spos, axis=1, keepdims=True)

    # ângulo de fase: Sol visto da Lua × Terra vista da Lua
    to_sun = spos - mpos
    to_earth = -mpos
    cos_i = np.sum(to_sun * to_earth, axis=1) / (
        np.linalg.norm(to_sun, axis=1) * np.linalg.norm(to_earth, axis=1)
    )
    phase = np.arccos(np.clip(cos_i, -1.0, 1.0))
    illum = (1.0 + np.cos(phase)) / 2.0

    # elongação com sinal para nomear as fases (crescente/minguante)
    dec_m = np.arcsin(np.clip(mu[:, 2], -1, 1))
    ra_m = np.arctan2(mu[:, 1], mu[:, 0])
    dec_s = np.arcsin(np.clip(su[:, 2], -1, 1))
    ra_s = np.arctan2(su[:, 1], su[:, 0])
    dra = ra_s - ra_m
    chi = np.arctan2(
        np.cos(dec_s) * np.sin(dra),
        np.sin(dec_s) * np.cos(dec_m) - np.cos(dec_s) * np.sin(dec_m) * np.cos(dra),
    )
    # ângulo de fase orientado: 0 = nova, π = cheia, crescendo para leste
    elong_signed = np.arctan2(
        np.cos(dec_m) * np.sin(-dra),
        np.sin(dec_m) * np.cos(dec_s) - np.cos(dec_m) * np.sin(dec_s) * np.cos(dra),
    )
    lon_diff = np.mod(np.degrees(-dra), 360.0)   # longitude Lua − Sol

    marks = [
        MoonMark(times[i], mu[i], float(illum[i]), float(phase[i]),
                 float(chi[i]))
        for i in range(n)
    ]

    # fases principais: instante em que lon_diff cruza 0, 90, 180 e 270
    targets = {0.0: "nova", 90.0: "crescente", 180.0: "cheia",
               270.0: "minguante"}
    for target, label in targets.items():
        diff = np.mod(lon_diff - target + 180.0, 360.0) - 180.0
        for i in range(1, n):
            if diff[i - 1] <= 0 <= diff[i] or diff[i - 1] >= 0 >= diff[i]:
                if abs(diff[i] - diff[i - 1]) > 180:
                    continue
                k = i if abs(diff[i]) < abs(diff[i - 1]) else i - 1
                if not marks[k].phase_name:
                    marks[k].phase_name = label
                break
    return marks
