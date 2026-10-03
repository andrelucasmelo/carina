"""Núcleo lunar (v0.17): orientação, iluminação, formações e eventos.

Responde às perguntas de quem aponta um telescópio para a Lua: que lado
ela mostra hoje (libração), onde está o terminador (colongitude), quais
formações estão com o Sol rasante — e por isso com relevo — e quando a
próxima boa noite para ver uma cratera vai acontecer.

Referenciais
------------
A orientação vem dos kernels da NAIF (``moon_pa_de421_1900-2050.bpc``,
``moon_080317.tf`` e ``pck00008.tpc``, embarcados em ``data/ephemeris``):
o referencial **MOON_ME** (*Mean Earth/polar axis*) é o mesmo das
coordenadas selenográficas do Gazetteer da IAU e dos mapas da LRO. Com ele,

- **libração** = latitude e longitude selenográficas do ponto sub-observador
  (topocêntrico por padrão: é o que o observador vê de fato);
- **ponto subsolar** = latitude e longitude do Sol visto da Lua;
- **colongitude** = 90° − longitude subsolar: 0° perto do quarto crescente,
  90° na cheia, 180° no minguante, 270° na nova. O terminador da manhã fica
  na longitude −colongitude.

Tudo é vetorizado: :func:`series` calcula de uma vez as grandezas de
centenas de instantes, base para as buscas de eventos e de datas boas.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

MOON_RADIUS_KM = 1737.4
SYNODIC_DAYS = 29.530588
FRAME_NAME = "MOON_ME_DE421"
KERNELS = ("moon_080317.tf", "pck00008.tpc", "moon_pa_de421_1900-2050.bpc")

# faixa de altura do Sol (graus) em que o relevo aparece bem
GOOD_SUN_MIN = 0.5
GOOD_SUN_MAX = 12.0

TYPE_PT = {
    "crater": "Cratera", "mare": "Mar", "lacus": "Lago", "sinus": "Baía",
    "palus": "Pântano", "mons": "Montanha", "rupes": "Escarpa",
    "vallis": "Vale", "rima": "Rima", "dorsum": "Crista",
    "promontorium": "Promontório", "catena": "Cadeia de crateras",
}
L100_TYPE_PT = {
    "global": "Visão geral", "crater": "Cratera", "basin": "Bacia",
    "mare": "Mar", "mountain": "Relevo", "rille": "Rima", "dome": "Domo",
    "ray": "Raios", "valley": "Vale", "other": "Outros",
}


# --------------------------------------------------------------------------
# dados embarcados
def data_dir() -> Path:
    from ..config import package_data_dir

    return package_data_dir() / "moon"


@dataclass
class MoonFeature:
    """Uma formação nomeada pela IAU (ou um item da Lunar 100)."""

    name: str
    type: str
    lat: float              # graus, +N
    lon: float              # graus, +L (leste)
    diam: float             # km
    pt: str = ""            # nome popular em português, se houver
    l100: int = 0           # número na Lunar 100 (0 = não está)
    desc: str = ""

    @property
    def label(self) -> str:
        return self.name

    @property
    def type_pt(self) -> str:
        return TYPE_PT.get(self.type, L100_TYPE_PT.get(self.type, self.type))

    @property
    def vector(self) -> np.ndarray:
        """Unitário no referencial MOON_ME."""
        la, lo = math.radians(self.lat), math.radians(self.lon)
        return np.array([math.cos(la) * math.cos(lo),
                         math.cos(la) * math.sin(lo), math.sin(la)])

    @property
    def ident(self) -> str:
        return f"L100 {self.l100}" if self.l100 else self.name

    def summary(self) -> str:
        bits = [self.type_pt]
        if self.diam:
            bits.append(f"{self.diam:.0f} km")
        bits.append(f"{abs(self.lat):.1f}°{'N' if self.lat >= 0 else 'S'}, "
                    f"{abs(self.lon):.1f}°{'L' if self.lon >= 0 else 'O'}")
        return " · ".join(bits)


@lru_cache(maxsize=1)
def features() -> tuple[MoonFeature, ...]:
    """Formações da face visível, das maiores para as menores."""
    path = data_dir() / "moon_features.json"
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    l100 = {item["n"]: item for item in lunar100()}
    out = []
    for f in data["features"]:
        n = int(f.get("l100", 0))
        out.append(MoonFeature(f["name"], f["type"], f["lat"], f["lon"],
                               f["diam"], f.get("pt", ""), n,
                               l100[n]["desc"] if n in l100 else ""))
    return tuple(out)


@lru_cache(maxsize=1)
def lunar100() -> tuple[dict, ...]:
    path = data_dir() / "lunar100.json"
    if not path.exists():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8"))["items"])


def lunar100_features() -> list[MoonFeature]:
    """A Lunar 100 como formações (as três primeiras não têm posição)."""
    out = []
    by_name = {f.name: f for f in features()}
    for item in lunar100():
        base = by_name.get(item["name"].split(" (")[0])
        out.append(MoonFeature(
            item["name"], item["type"],
            item["lat"] if item["lat"] is not None else float("nan"),
            item["lon"] if item["lon"] is not None else float("nan"),
            base.diam if base else 0.0, base.pt if base else "", item["n"],
            item["desc"]))
    return out


def find_feature(name: str) -> MoonFeature | None:
    key = name.strip().lower()
    for f in features():
        if f.name.lower() == key or (f.pt and f.pt.lower() == key):
            return f
    for f in lunar100_features():
        if f.name.lower() == key or f.ident.lower() == key:
            return f
    return None


# --------------------------------------------------------------------------
# kernels de orientação
@lru_cache(maxsize=4)
def _frame_for(ephem_dir: str):
    from skyfield.api import Loader
    from skyfield.planetarylib import PlanetaryConstants

    loader = Loader(ephem_dir, verbose=False)
    pc = PlanetaryConstants()
    pc.read_text(loader(KERNELS[0]))
    pc.read_text(loader(KERNELS[1]))
    pc.read_binary(loader(KERNELS[2]))
    return pc.build_frame_named(FRAME_NAME)


def kernels_dir() -> Path:
    from ..config import package_ephemeris_dir

    return package_ephemeris_dir()


def kernels_available() -> bool:
    d = kernels_dir()
    return all((d / k).exists() for k in KERNELS)


def frame():
    """Referencial MOON_ME do Skyfield (carregado uma vez)."""
    return _frame_for(str(kernels_dir()))


# --------------------------------------------------------------------------
# geometria
@dataclass
class MoonGeometry:
    """Fotografia da Lua num instante, vista pelo observador."""

    when_utc: dt.datetime
    lib_lat: float           # graus — latitude do ponto sub-observador
    lib_lon: float           # graus — longitude do ponto sub-observador
    sun_lat: float           # graus — ponto subsolar
    sun_lon: float
    colongitude: float       # graus 0..360
    illumination: float      # 0..1
    phase_angle: float       # graus (Sol–Lua–observador)
    elongation: float        # graus 0..360 (longitude eclíptica Lua − Sol)
    distance_km: float
    pa_axis: float           # graus — ângulo de posição do eixo norte
    pa_bright_limb: float    # graus — ângulo de posição do limbo iluminado
    rotation: np.ndarray = field(repr=False)   # ICRS -> MOON_ME
    obs_body: np.ndarray = field(repr=False)   # direção do observador (ME)
    sun_body: np.ndarray = field(repr=False)   # direção do Sol (ME)
    moon_icrs: np.ndarray = field(repr=False)  # observador -> Lua (unitário)

    @property
    def waxing(self) -> bool:
        return self.elongation < 180.0

    @property
    def age_days(self) -> float:
        """Idade aproximada desde a Lua nova (pela elongação)."""
        return self.elongation / 360.0 * SYNODIC_DAYS

    @property
    def angular_diameter_arcmin(self) -> float:
        return math.degrees(2.0 * math.asin(MOON_RADIUS_KM / self.distance_km)) * 60.0

    @property
    def phase_name(self) -> str:
        e = self.elongation
        if e < 7 or e > 353:
            return "Lua nova"
        if e < 83:
            return "Crescente"
        if e < 97:
            return "Quarto crescente"
        if e < 173:
            return "Crescente gibosa"
        if e < 187:
            return "Lua cheia"
        if e < 263:
            return "Minguante gibosa"
        if e < 277:
            return "Quarto minguante"
        return "Minguante"

    def sun_altitude_at(self, lat: float, lon: float) -> float:
        """Altura do Sol (graus) vista de um ponto da superfície."""
        la, lo = math.radians(lat), math.radians(lon)
        n = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                      math.sin(la)])
        return math.degrees(math.asin(max(-1.0, min(1.0, float(n @ self.sun_body)))))

    def view_cos(self, lat: float, lon: float) -> float:
        """Cosseno do ângulo entre a normal do ponto e o observador
        (> 0 = face visível; perto de 0 = na borda)."""
        la, lo = math.radians(lat), math.radians(lon)
        n = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                      math.sin(la)])
        return float(n @ self.obs_body)

    def is_morning(self, lon: float) -> bool:
        """Sol nascendo no ponto (lado do terminador da manhã)."""
        return 0.0 < (self.sun_lon - lon) % 360.0 < 180.0


def _times(engine, when):
    if isinstance(when, dt.datetime):
        return engine.ts.from_datetime(when)
    if isinstance(when, (list, tuple)):
        return engine.ts.from_datetimes(list(when))
    return when


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=0, keepdims=True)


def series(engine, when, topocentric: bool = True) -> dict:
    """Grandezas lunares para um ou vários instantes (vetorizado).

    ``when``: datetime, lista de datetimes ou Time do Skyfield. Devolve um
    dicionário de arrays (o último eixo é o tempo, quando vetorial).
    """
    t = _times(engine, when)
    origin = engine.site if (topocentric and engine.site is not None) else engine.earth
    obs = origin.at(t)
    moon = obs.observe(engine.eph["moon"])
    sun = obs.observe(engine.eph["sun"])
    m = np.asarray(moon.position.au, dtype=np.float64)        # (3,) ou (3,N)
    s = np.asarray(sun.position.au, dtype=np.float64)
    rot = np.asarray(frame().rotation_at(t), dtype=np.float64)
    if rot.ndim == 2:
        obs_b = rot @ _unit(-m)
        sun_b = rot @ _unit(s - m)
    else:
        obs_b = np.einsum("ijn,jn->in", rot, _unit(-m))
        sun_b = np.einsum("ijn,jn->in", rot, _unit(s - m))
    lib_lat = np.degrees(np.arcsin(np.clip(obs_b[2], -1, 1)))
    lib_lon = np.degrees(np.arctan2(obs_b[1], obs_b[0]))
    sun_lat = np.degrees(np.arcsin(np.clip(sun_b[2], -1, 1)))
    sun_lon = np.degrees(np.arctan2(sun_b[1], sun_b[0]))
    cos_i = np.sum(obs_b * sun_b, axis=0)
    phase = np.degrees(np.arccos(np.clip(cos_i, -1, 1)))
    # elongação orientada: longitude eclíptica da Lua menos a do Sol
    from skyfield.framelib import ecliptic_frame
    lm = moon.frame_latlon(ecliptic_frame)[1].degrees
    ls = sun.frame_latlon(ecliptic_frame)[1].degrees
    elong = np.mod(np.asarray(lm) - np.asarray(ls), 360.0)
    dist_km = np.linalg.norm(m, axis=0) * 149597870.7
    return {
        "t": t, "rot": rot, "obs_body": obs_b, "sun_body": sun_b,
        "moon_icrs": _unit(m), "sun_icrs": _unit(s),
        "lib_lat": lib_lat, "lib_lon": lib_lon,
        "sun_lat": sun_lat, "sun_lon": sun_lon,
        "colongitude": np.mod(90.0 - sun_lon, 360.0),
        "phase_angle": phase, "illumination": (1.0 + np.cos(np.radians(phase))) / 2.0,
        "elongation": elong, "distance_km": dist_km,
    }


def _position_angle(target: np.ndarray, center: np.ndarray) -> float:
    """Ângulo de posição (graus, do norte para leste) da direção
    ``target`` (ICRS) vista no ponto ``center`` do céu."""
    pole = np.array([0.0, 0.0, 1.0])
    n_t = pole - (pole @ center) * center
    n_t /= max(np.linalg.norm(n_t), 1e-12)
    e_t = np.cross(pole, center)
    e_t /= max(np.linalg.norm(e_t), 1e-12)
    return math.degrees(math.atan2(float(target @ e_t), float(target @ n_t))) % 360.0


def geometry(engine, when: dt.datetime | None = None,
             topocentric: bool = True) -> MoonGeometry:
    """:class:`MoonGeometry` num instante (padrão: o relógio do programa)."""
    if when is None:
        when = engine.time.current_datetime()
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    d = series(engine, when, topocentric)
    rot = d["rot"]
    center = d["moon_icrs"]
    pole_icrs = rot.T @ np.array([0.0, 0.0, 1.0])
    sun_dir = rot.T @ d["sun_body"]
    return MoonGeometry(
        when_utc=when.astimezone(dt.timezone.utc),
        lib_lat=float(d["lib_lat"]), lib_lon=float(d["lib_lon"]),
        sun_lat=float(d["sun_lat"]), sun_lon=float(d["sun_lon"]),
        colongitude=float(d["colongitude"]),
        illumination=float(d["illumination"]),
        phase_angle=float(d["phase_angle"]),
        elongation=float(d["elongation"]),
        distance_km=float(d["distance_km"]),
        pa_axis=_position_angle(pole_icrs, center),
        pa_bright_limb=_position_angle(sun_dir, center),
        rotation=rot, obs_body=np.asarray(d["obs_body"]),
        sun_body=np.asarray(d["sun_body"]), moon_icrs=np.asarray(center),
    )


# --------------------------------------------------------------------------
# formações e terminador
@dataclass
class TerminatorEntry:
    feature: MoonFeature
    sun_alt: float           # graus
    morning: bool            # Sol nascendo (True) ou se pondo


def terminator_features(geom: MoonGeometry, max_sun_alt: float = GOOD_SUN_MAX,
                        min_view: float = 0.15, min_diam: float = 0.0,
                        limit: int | None = None) -> list[TerminatorEntry]:
    """Formações com o Sol baixo (relevo realçado) e voltadas para nós,
    das maiores para as menores, com a Lunar 100 à frente."""
    feats = [f for f in features() if f.diam >= min_diam]
    if not feats:
        return []
    lat = np.radians([f.lat for f in feats])
    lon = np.radians([f.lon for f in feats])
    n = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    sun_alt = np.degrees(np.arcsin(np.clip(geom.sun_body @ n, -1, 1)))
    view = geom.obs_body @ n
    # mares e grandes formações aceitam o Sol um pouco mais alto
    ok = (sun_alt > -0.5) & (sun_alt < max_sun_alt) & (view > min_view)
    out = [TerminatorEntry(feats[i], float(sun_alt[i]), geom.is_morning(feats[i].lon))
           for i in np.nonzero(ok)[0]]
    out.sort(key=lambda e: (e.feature.l100 == 0, -e.feature.diam))
    return out[:limit] if limit else out


@dataclass
class GoodWindow:
    """Uma noite boa para uma formação."""

    start_utc: dt.datetime
    end_utc: dt.datetime
    sun_alt_min: float
    sun_alt_max: float
    morning: bool
    moon_alt_max: float

    @property
    def mid_utc(self) -> dt.datetime:
        return self.start_utc + (self.end_utc - self.start_utc) / 2


def good_dates(engine, lat: float, lon: float, start_utc: dt.datetime,
               days: int = 60, step_minutes: float = 30.0,
               sun_min: float = GOOD_SUN_MIN, sun_max: float = GOOD_SUN_MAX,
               min_moon_alt: float = 15.0, max_sky_sun: float = -6.0,
               min_view: float = 0.15) -> list[GoodWindow]:
    """Próximas noites em que a formação está com o Sol rasante **e** a Lua
    está no céu do observador, com o céu já escuro.

    Amostra o período a cada ``step_minutes`` (vetorizado) e agrupa as
    amostras boas consecutivas em janelas.
    """
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=dt.timezone.utc)
    n = int(days * 24 * 60 / step_minutes) + 1
    times = [start_utc + dt.timedelta(minutes=step_minutes * i) for i in range(n)]
    d = series(engine, times)
    la, lo = math.radians(lat), math.radians(lon)
    nvec = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                     math.sin(la)])
    sun_alt = np.degrees(np.arcsin(np.clip(nvec @ d["sun_body"], -1, 1)))
    view = nvec @ d["obs_body"]
    obs = engine.site.at(d["t"])
    moon_alt = obs.observe(engine.eph["moon"]).apparent().altaz()[0].degrees
    sky_sun = obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees
    good = ((sun_alt >= sun_min) & (sun_alt <= sun_max) & (view > min_view)
            & (moon_alt >= min_moon_alt) & (sky_sun <= max_sky_sun))
    out: list[GoodWindow] = []
    i = 0
    while i < n:
        if not good[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and good[j + 1]:
            j += 1
        sl = slice(i, j + 1)
        morning = 0.0 < (float(d["sun_lon"][i]) - lon) % 360.0 < 180.0
        out.append(GoodWindow(times[i], times[j], float(sun_alt[sl].min()),
                              float(sun_alt[sl].max()), morning,
                              float(moon_alt[sl].max())))
        i = j + 1
    return out


# --------------------------------------------------------------------------
# eventos lunares
@dataclass
class MoonEvent:
    when_utc: dt.datetime
    kind: str                # perigeu | apogeu | libracao | lunar_x | ...
    title: str
    detail: str = ""
    value: float = 0.0
    end_utc: dt.datetime | None = None


def _grid(start: dt.datetime, end: dt.datetime, hours: float) -> list[dt.datetime]:
    n = int((end - start).total_seconds() / 3600.0 / hours) + 1
    return [start + dt.timedelta(hours=hours * i) for i in range(n)]


def _refine_extreme(fn, t0: dt.datetime, half_hours: float, maximize: bool,
                    iters: int = 40) -> tuple[dt.datetime, float]:
    """Busca da razão áurea do extremo de ``fn`` em ``t0 ± half_hours``."""
    g = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = -half_hours * 3600.0, half_hours * 3600.0
    sign = -1.0 if maximize else 1.0
    f = lambda x: sign * fn(t0 + dt.timedelta(seconds=x))  # noqa: E731
    c, d_ = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d_)
    for _ in range(iters):
        if fc < fd:
            b, d_, fd = d_, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d_, fd
            d_ = a + g * (b - a)
            fd = f(d_)
        if b - a < 30.0:
            break
    x = (a + b) / 2.0
    return t0 + dt.timedelta(seconds=x), sign * f(x)


def _bisect(fn, t0: dt.datetime, t1: dt.datetime, iters: int = 30) -> dt.datetime:
    """Raiz de ``fn`` (troca de sinal) entre t0 e t1."""
    f0 = fn(t0)
    for _ in range(iters):
        mid = t0 + (t1 - t0) / 2
        fm = fn(mid)
        if (fm > 0) == (f0 > 0):
            t0, f0 = mid, fm
        else:
            t1 = mid
        if (t1 - t0).total_seconds() < 20:
            break
    return t0 + (t1 - t0) / 2


def perigees_apogees(engine, start: dt.datetime, end: dt.datetime) -> list[MoonEvent]:
    """Perigeus e apogeus (distância geocêntrica centro a centro)."""
    times = _grid(start, end, 3.0)
    d = series(engine, times, topocentric=False)["distance_km"]

    def dist(when):
        return float(series(engine, when, topocentric=False)["distance_km"])

    out = []
    for i in range(1, len(times) - 1):
        if d[i] < d[i - 1] and d[i] <= d[i + 1]:
            when, km = _refine_extreme(dist, times[i], 3.0, maximize=False)
            out.append(MoonEvent(when, "perigeu", "Lua no perigeu",
                                 f"{km:,.0f} km da Terra".replace(",", "."), km))
        elif d[i] > d[i - 1] and d[i] >= d[i + 1]:
            when, km = _refine_extreme(dist, times[i], 3.0, maximize=True)
            out.append(MoonEvent(when, "apogeu", "Lua no apogeu",
                                 f"{km:,.0f} km da Terra".replace(",", "."), km))
    return out


LIB_LABEL = {
    ("lon", 1): ("leste", "a borda leste (Mare Crisium, Mare Smythii, Mare Marginis)"),
    ("lon", -1): ("oeste", "a borda oeste (Grimaldi, bacia Orientale)"),
    ("lat", 1): ("norte", "a região do polo norte (Peary, Mare Humboldtianum)"),
    ("lat", -1): ("sul", "a região do polo sul (Bailly, montes Leibnitz)"),
}


def libration_extremes(engine, start: dt.datetime, end: dt.datetime,
                       min_deg: float = 6.0) -> list[MoonEvent]:
    """Extremos de libração em longitude e latitude (geocêntricos),
    só os maiores que ``min_deg`` — as boas noites para as bordas."""
    times = _grid(start, end, 6.0)
    d = series(engine, times, topocentric=False)
    out = []
    for axis in ("lon", "lat"):
        v = d["lib_" + axis]
        for i in range(1, len(times) - 1):
            for sgn in (1, -1):
                if sgn * v[i] > sgn * v[i - 1] and sgn * v[i] >= sgn * v[i + 1] \
                        and sgn * v[i] >= min_deg:
                    def fn(when, axis=axis):
                        return float(series(engine, when, topocentric=False)["lib_" + axis])
                    when, val = _refine_extreme(fn, times[i], 6.0, maximize=sgn > 0)
                    side, region = LIB_LABEL[(axis, sgn)]
                    out.append(MoonEvent(
                        when, "libracao", f"Libração favorável ao {side}",
                        f"{abs(val):.1f}° — boa ocasião para {region}.", val))
    out.sort(key=lambda e: e.when_utc)
    return out


def colongitude_crossings(engine, target: float, start: dt.datetime,
                          end: dt.datetime) -> list[dt.datetime]:
    """Instantes em que a colongitude passa por ``target`` (graus)."""
    times = _grid(start, end, 6.0)
    c = series(engine, times, topocentric=False)["colongitude"]
    diff = np.mod(c - target + 180.0, 360.0) - 180.0

    def fn(when):
        cc = float(series(engine, when, topocentric=False)["colongitude"])
        return (cc - target + 180.0) % 360.0 - 180.0

    out = []
    for i in range(1, len(times)):
        if diff[i - 1] < 0 <= diff[i] and abs(diff[i] - diff[i - 1]) < 90:
            out.append(_bisect(fn, times[i - 1], times[i]))
    return out


def sunrise_crossings(engine, lat: float, lon: float, alt: float,
                      start: dt.datetime, end: dt.datetime,
                      rising: bool = True) -> list[dt.datetime]:
    """Quando o Sol passa pela altura ``alt`` vista de (lat, lon) na Lua."""
    la, lo = math.radians(lat), math.radians(lon)
    nvec = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                     math.sin(la)])
    times = _grid(start, end, 6.0)
    h = np.degrees(np.arcsin(np.clip(
        nvec @ series(engine, times, topocentric=False)["sun_body"], -1, 1))) - alt

    def fn(when):
        sb = series(engine, when, topocentric=False)["sun_body"]
        return math.degrees(math.asin(max(-1.0, min(1.0, float(nvec @ sb))))) - alt

    out = []
    for i in range(1, len(times)):
        up = h[i - 1] < 0 <= h[i]
        down = h[i - 1] >= 0 > h[i]
        if (rising and up) or (not rising and down):
            out.append(_bisect(fn, times[i - 1], times[i]))
    return out


# eventos de "efeitos de luz" com a definição usada
LUNAR_X_COLONG = 358.0        # X de Werner–Blanchinus–La Caille e V de Ukert
JURA = (47.0, -37.0)          # Montes Jura, borda de Sinus Iridum
RUPES_RECTA = (-21.8, -7.8)


def light_events(engine, start: dt.datetime, end: dt.datetime) -> list[MoonEvent]:
    """Lunar X/V, Alça Dourada, Rupes Recta e luz cinérea no período."""
    out = []
    for when in colongitude_crossings(engine, LUNAR_X_COLONG, start, end):
        out.append(MoonEvent(
            when, "lunar_x", "Lunar X e Lunar V",
            "O X luminoso perto de Werner e o V perto de Ukert surgem no "
            "terminador por cerca de 4 h em torno deste instante (colongitude ≈ 358°)."))
    for when in sunrise_crossings(engine, *JURA, 0.0, start, end, rising=True):
        out.append(MoonEvent(
            when, "alca_dourada", "Alça Dourada (Sinus Iridum)",
            "O Sol nasce nos Montes Jura enquanto a baía ainda está no escuro: "
            "um arco luminoso além do terminador."))
    for when in sunrise_crossings(engine, *RUPES_RECTA, 2.0, start, end, rising=True):
        out.append(MoonEvent(
            when, "rupes_recta", "Rupes Recta como linha escura",
            "O Sol da manhã projeta a sombra da escarpa: uma linha escura "
            "nítida no Mare Nubium, visível por um a dois dias."))
    for when in sunrise_crossings(engine, *RUPES_RECTA, 3.0, start, end, rising=False):
        out.append(MoonEvent(
            when, "rupes_recta", "Rupes Recta como linha clara",
            "O Sol da tarde ilumina a face da escarpa: uma linha clara antes "
            "do quarto minguante."))
    out.extend(earthshine_windows(engine, start, end))
    out.sort(key=lambda e: e.when_utc)
    return out


def new_moons(engine, start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    from skyfield import almanac

    t, y = almanac.find_discrete(engine.ts.from_datetime(start),
                                 engine.ts.from_datetime(end),
                                 almanac.moon_phases(engine.eph))
    return [ti.utc_datetime() for ti, yi in zip(t, y) if int(yi) == 0]


def earthshine_windows(engine, start: dt.datetime, end: dt.datetime) -> list[MoonEvent]:
    """Melhores dias para a luz cinérea: Lua fina, 2 a 5 dias da nova."""
    out = []
    pad = dt.timedelta(days=6)
    for nm in new_moons(engine, start - pad, end + pad):
        evening = nm + dt.timedelta(days=2)
        morning = nm - dt.timedelta(days=5)
        if start <= evening <= end:
            out.append(MoonEvent(
                evening, "luz_cinerea", "Luz cinérea (crescente fina)",
                "Até três dias: procure a parte escura da Lua iluminada pela "
                "Terra, logo após o pôr do Sol, no oeste.",
                end_utc=evening + dt.timedelta(days=3)))
        if start <= morning <= end:
            out.append(MoonEvent(
                morning, "luz_cinerea", "Luz cinérea (minguante fina)",
                "Até três dias: a parte escura da Lua iluminada pela Terra, "
                "antes do amanhecer, no leste.",
                end_utc=morning + dt.timedelta(days=3)))
    return out


def all_events(engine, start: dt.datetime, end: dt.datetime) -> list[MoonEvent]:
    out = perigees_apogees(engine, start, end)
    out += libration_extremes(engine, start, end)
    out += light_events(engine, start, end)
    out.sort(key=lambda e: e.when_utc)
    return out


# --------------------------------------------------------------------------
# fotografia
def mosaic_panels(moon_diam_deg: float, fov_w_deg: float, fov_h_deg: float,
                  overlap: float = 0.2) -> tuple[int, int]:
    """Quantos quadros (colunas, linhas) cobrem o disco com sobreposição."""
    if fov_w_deg <= 0 or fov_h_deg <= 0:
        return (0, 0)
    step_w = fov_w_deg * (1.0 - overlap)
    step_h = fov_h_deg * (1.0 - overlap)
    cols = 1 if fov_w_deg >= moon_diam_deg else math.ceil((moon_diam_deg - fov_w_deg) / step_w) + 1
    rows = 1 if fov_h_deg >= moon_diam_deg else math.ceil((moon_diam_deg - fov_h_deg) / step_h) + 1
    return (cols, rows)


def photo_advice(illumination: float, waxing: bool) -> str:
    """Que tipo de foto a fase favorece."""
    if illumination < 0.03:
        return "Lua nova: sem foto da Lua; aproveite o céu escuro."
    if illumination < 0.25:
        return ("Crescente fina: luz cinérea e paisagem no crepúsculo; relevo "
                "forte perto do terminador." if waxing else
                "Minguante fina: luz cinérea antes do amanhecer.")
    if illumination < 0.85:
        return ("Fase ideal para relevo: crateras e montanhas com sombras "
                "longas ao longo do terminador.")
    if illumination < 0.97:
        return "Gibosa: muito disco iluminado, relevo só na borda do terminador."
    return ("Lua cheia: disco inteiro, raios de Tycho e Copernicus; quase sem "
            "relevo. Boa para o nascer da Lua sobre a paisagem.")
