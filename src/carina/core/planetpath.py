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
    for i in range(len(times)):
        local_month = times[i].astimezone().month
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
}
