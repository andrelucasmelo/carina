"""Satélites artificiais: ISS e companhia (v0.19 T7).

Passagens visíveis a partir de **elementos orbitais (TLE)** com o modelo
SGP4 (via ``skyfield.EarthSatellite``). Uma passagem é **visível** quando o
satélite está iluminado pelo Sol e o observador está no escuro (Sol abaixo
de −6°) — é o que faz a ISS aparecer como um ponto brilhante cruzando o céu.

Os TLE envelhecem: a posição prevista perde precisão em dias (a ISS faz
manobras). Enquanto a política de recursos online não é decidida (decisão
1 do plano), o arquivo é **importado pelo usuário** (por exemplo o
``stations.txt`` da CelesTrak) e guardado na pasta de dados; o programa
avisa a idade dos elementos.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

UTC = dt.timezone.utc
TLE_FILE = "satelites.tle"
MAX_AGE_DAYS = 14


@dataclass
class Tle:
    name: str
    line1: str
    line2: str

    @property
    def norad(self) -> int:
        return int(self.line1[2:7])

    @property
    def epoch(self) -> dt.datetime:
        yy = int(self.line1[18:20])
        doy = float(self.line1[20:32])
        year = 2000 + yy if yy < 57 else 1900 + yy
        return dt.datetime(year, 1, 1, tzinfo=UTC) + dt.timedelta(days=doy - 1)

    def age_days(self, when: dt.datetime) -> float:
        return (when - self.epoch).total_seconds() / 86400.0


def _checksum_ok(line: str) -> bool:
    if len(line) < 69:
        return False
    total = sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68])
    return total % 10 == int(line[68])


def parse_tle(text: str) -> list[Tle]:
    """Lê um arquivo TLE (formato de 3 linhas com nome, ou de 2 linhas)."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name, l1, l2 = f"NORAD {lines[i][2:7].strip()}", lines[i], lines[i + 1]
            i += 2
        elif (i + 2 < len(lines) and lines[i + 1].startswith("1 ")
              and lines[i + 2].startswith("2 ")):
            name, l1, l2 = lines[i].strip().lstrip("0 ").strip() or lines[i].strip(), \
                lines[i + 1], lines[i + 2]
            i += 3
        else:
            i += 1
            continue
        if _checksum_ok(l1) and _checksum_ok(l2):
            out.append(Tle(name, l1, l2))
    return out


def tle_path() -> Path:
    from ..config import user_data_path

    return user_data_path() / TLE_FILE


def load_saved(path: Path | None = None) -> list[Tle]:
    p = path or tle_path()
    if not p.exists():
        return []
    return parse_tle(p.read_text(encoding="utf-8", errors="replace"))


def save(text: str, path: Path | None = None) -> list[Tle]:
    """Guarda o texto importado (só se tiver TLE válidos)."""
    tles = parse_tle(text)
    if tles:
        p = path or tle_path()
        p.write_text("\n".join(f"{t.name}\n{t.line1}\n{t.line2}" for t in tles) + "\n",
                     encoding="utf-8")
    return tles


def find(tles: list[Tle], query: str) -> Tle | None:
    q = query.strip().lower()
    for t in tles:
        if q in t.name.lower() or q == str(t.norad):
            return t
    return None


def iss(tles: list[Tle]) -> Tle | None:
    return next((t for t in tles if t.norad == 25544), None) or find(tles, "ISS")


@dataclass
class Pass:
    rise: dt.datetime
    culminate: dt.datetime
    set: dt.datetime
    max_alt: float
    rise_az: float
    set_az: float
    visible: bool             # iluminado e observador no escuro em algum trecho
    visible_from: dt.datetime | None = None
    visible_to: dt.datetime | None = None

    @property
    def minutes(self) -> float:
        return (self.set - self.rise).total_seconds() / 60.0


def _sat(engine, tle: Tle):
    from skyfield.api import EarthSatellite

    return EarthSatellite(tle.line1, tle.line2, tle.name, engine.ts)


def passes(engine, tle: Tle, start: dt.datetime, days: float = 3.0,
           min_alt: float = 10.0) -> list[Pass]:
    """Passagens acima de ``min_alt`` no período."""
    sat = _sat(engine, tle)
    t0 = engine.ts.from_datetime(start)
    t1 = engine.ts.from_datetime(start + dt.timedelta(days=days))
    times, kinds = sat.find_events(engine.topos, t0, t1, altitude_degrees=min_alt)
    out = []
    cur: dict = {}
    for t, k in zip(times, kinds):
        if k == 0:
            cur = {"rise": t}
        elif k == 1 and "rise" in cur:
            cur["culm"] = t
        elif k == 2 and "culm" in cur:
            cur["set"] = t
            out.append(_make_pass(engine, sat, cur))
            cur = {}
    return out


def _make_pass(engine, sat, ev) -> Pass:
    rise, culm, sett = ev["rise"], ev["culm"], ev["set"]
    diff = sat - engine.topos
    alt_c = diff.at(culm).altaz()[0].degrees
    az_r = diff.at(rise).altaz()[1].degrees
    az_s = diff.at(sett).altaz()[1].degrees
    # visibilidade ao longo da passagem (amostras de 10 s)
    a, b = rise.utc_datetime(), sett.utc_datetime()
    n = max(2, int((b - a).total_seconds() / 10) + 1)
    ts = engine.ts.from_datetimes([a + (b - a) * k / (n - 1) for k in range(n)])
    sunlit = np.asarray(sat.at(ts).is_sunlit(engine.eph))
    sun_alt = np.asarray(engine.site.at(ts).observe(engine.eph["sun"]).apparent()
                         .altaz()[0].degrees)
    vis = sunlit & (sun_alt < -6.0)
    idx = np.nonzero(vis)[0]
    vf = vt = None
    if len(idx):
        vf = a + (b - a) * float(idx[0]) / (n - 1)
        vt = a + (b - a) * float(idx[-1]) / (n - 1)
    return Pass(a, culm.utc_datetime(), b, float(alt_c), float(az_r), float(az_s),
                bool(len(idx)), vf, vt)


def track(engine, tle: Tle, start: dt.datetime, end: dt.datetime,
          step_s: float = 10.0) -> list[tuple[dt.datetime, np.ndarray]]:
    """Trilha no céu do observador: (instante, vetor horizontal unitário)."""
    sat = _sat(engine, tle)
    n = max(2, int((end - start).total_seconds() / step_s) + 1)
    times = [start + dt.timedelta(seconds=step_s * k) for k in range(n)]
    alt, az, _ = (sat - engine.topos).at(engine.ts.from_datetimes(times)).altaz()
    a, z = np.radians(alt.degrees), np.radians(az.degrees)
    vecs = np.stack([np.cos(a) * np.cos(z), np.cos(a) * np.sin(z), np.sin(a)], axis=1)
    return list(zip(times, vecs))


def position(engine, tle: Tle, when: dt.datetime) -> tuple[float, float]:
    """(altitude, azimute) em graus agora."""
    sat = _sat(engine, tle)
    alt, az, _ = (sat - engine.topos).at(engine.ts.from_datetime(when)).altaz()
    return float(alt.degrees), float(az.degrees)


def direction_name(az: float) -> str:
    names = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"]
    return names[int((az % 360) / 45 + 0.5) % 8]
