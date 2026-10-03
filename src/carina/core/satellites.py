"""Luas de Júpiter e Saturno, Grande Mancha Vermelha e anéis (v0.18 T2).

Posições
--------
As órbitas vêm das efemérides de satélites do JPL (``jup365``, ``sat441``),
reajustadas no build em polinômios de Chebyshev de um período orbital
(``scripts/build_planets.py``): erro máximo de 10–300 km conforme a lua,
de 2000 a 2060. Fora desse intervalo as luas não são mostradas.

As coordenadas são **planetocêntricas** (ICRS, km). Como o DE440s só tem
o baricentro do sistema, o centro do planeta é obtido descontando o
deslocamento causado pelas luas (Σ μᵢ rᵢ / μ_total).

Vista do observador
-------------------
Cada lua é projetada no plano do céu em raios equatoriais do planeta:
``x`` para **leste**, ``y`` para **norte**, ``z`` para o observador
(> 0 = na frente do planeta). Com o Sol, saem os quatro fenômenos:
trânsito (lua na frente do disco), sombra no disco, ocultação (atrás do
disco) e eclipse (na sombra do planeta).
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .planets import AU_KM, C_KM_S, UTC, radii_km

SYSTEM_FILE = {"Júpiter": "jupiter", "Saturno": "saturn"}
# GM (km³/s²): planetas e luas — para achar o centro do planeta no baricentro
GM_PLANET = {"Júpiter": 126686531.9, "Saturno": 37931206.2}
GM_MOON = {501: 5959.92, 502: 3202.72, 503: 9887.83, 504: 7179.29,
           601: 2.50, 602: 7.21, 603: 41.21, 604: 73.11, 605: 153.94,
           606: 8978.14, 607: 0.37, 608: 120.52}
MOON_MAG = {501: 5.0, 502: 5.3, 503: 4.6, 504: 5.7, 601: 12.9, 602: 11.7,
            603: 10.2, 604: 10.4, 605: 9.7, 606: 8.3, 607: 14.2, 608: 11.0}


def data_dir():
    from ..config import package_data_dir

    return package_data_dir() / "planets"


@lru_cache(maxsize=2)
def _system(name: str):
    path = data_dir() / f"moons_{SYSTEM_FILE[name]}.npz"
    if not path.exists():
        return None
    d = np.load(path)
    ids = [int(i) for i in d["ids"]]
    return {
        "t_start": float(d["t_start"]), "t_end": float(d["t_end"]),
        "ids": ids, "names": [str(n) for n in d["names"]],
        "coef": {i: d[f"coef_{i}"] for i in ids},
        "len": {i: float(d[f"len_{i}"]) for i in ids},
    }


def available(planet: str) -> bool:
    return planet in SYSTEM_FILE and _system(planet) is not None


def moon_names(planet: str) -> list[tuple[int, str]]:
    s = _system(planet)
    return list(zip(s["ids"], s["names"])) if s else []


def covers(planet: str, jd_tdb: float) -> bool:
    s = _system(planet)
    return bool(s) and s["t_start"] <= jd_tdb <= s["t_end"] - 1.0


def moon_positions(planet: str, jd_tdb) -> dict[int, np.ndarray]:
    """{id: vetor (3,) ou (3, N) em km}, relativo ao **centro** do planeta."""
    from numpy.polynomial import chebyshev as C

    s = _system(planet)
    jd = np.atleast_1d(np.asarray(jd_tdb, dtype=np.float64))
    out = {}
    for mid in s["ids"]:
        coef, L = s["coef"][mid], s["len"][mid]
        x = (jd - s["t_start"]) / L
        i = np.clip(x.astype(np.int64), 0, len(coef) - 1)
        tau = 2.0 * (x - i) - 1.0
        T = C.chebvander(tau, coef.shape[2] - 1)                  # (N, deg+1)
        pos = np.einsum("nk,nik->in", T, coef[i].astype(np.float64))
        out[mid] = pos[:, 0] if np.ndim(jd_tdb) == 0 else pos
    return out


def center_offset_km(planet: str, positions: dict) -> np.ndarray:
    """Centro do planeta − baricentro do sistema (km)."""
    total = GM_PLANET[planet] + sum(GM_MOON[m] for m in positions)
    acc = sum(GM_MOON[m] * positions[m] for m in positions)
    return -acc / total


@dataclass
class MoonView:
    id: int
    name: str
    x: float              # raios equatoriais, + = leste
    y: float              # + = norte
    z: float              # + = na frente do planeta
    magnitude: float
    status: str           # visivel | transito | ocultada | eclipsada
    shadow: tuple | None  # (x, y) da sombra sobre o disco, se houver

    @property
    def status_pt(self) -> str:
        return {"visivel": "visível", "transito": "em trânsito sobre o disco",
                "ocultada": "atrás do planeta", "eclipsada": "na sombra do planeta"}[self.status]


def _inside_disc(x, y, pa_axis_deg, flat):
    """Ponto (x leste, y norte) dentro da elipse do disco?"""
    a = math.radians(pa_axis_deg)
    # componentes ao longo do eixo projetado (polo) e do equador
    q_pole = x * math.sin(a) + y * math.cos(a)
    q_eq = x * math.cos(a) - y * math.sin(a)
    return q_eq * q_eq + (q_pole / flat) ** 2 < 1.0


def system_view(engine, state) -> list[MoonView]:
    """Luas vistas do observador (``state`` = :class:`PlanetState`)."""
    planet = state.name
    if not covers(planet, state.jd_tdb):
        return []
    s = _system(planet)
    pos = moon_positions(planet, state.jd_tdb)
    req, rpol = radii_km(planet)
    u = state.u_icrs
    pole = np.array([0.0, 0.0, 1.0])
    n_t = pole - (pole @ u) * u
    n_t /= np.linalg.norm(n_t)
    e_t = np.cross(pole, u)
    e_t /= np.linalg.norm(e_t)
    flat = state.polar_diameter / state.diameter
    sun = state.sun_dir
    frame = state.frame
    out = []
    for mid, name in zip(s["ids"], s["names"]):
        r = pos[mid]
        # perspectiva: a lua na frente do planeta (mais perto de nós) parece
        # mais afastada dele — 0,1% em Calisto, 0,3″ a 13 raios na frente
        dist_km = state.distance_au * AU_KM
        depth = float(r @ -u)
        persp = dist_km / (dist_km - depth)
        x, y, z = (r @ e_t) / req * persp, (r @ n_t) / req * persp, depth / req
        inside = _inside_disc(x, y, state.pa_axis, flat)
        status = "visivel"
        if inside and z > 0:
            status = "transito"
        elif inside and z < 0:
            status = "ocultada"
        # eclipse: dentro do cilindro de sombra do planeta (lado oposto ao Sol)
        along = float(r @ sun)
        perp = r - along * sun
        rb = frame @ perp
        if along < 0 and (rb[0] ** 2 + rb[1] ** 2) / req ** 2 + (rb[2] / rpol) ** 2 < 1.0 \
                and status != "transito":
            status = "eclipsada" if status == "visivel" else status
        # sombra sobre o disco: reta r − k·sol cruzando o elipsoide
        shadow = None
        if along > 0:
            rb0 = frame @ r / req
            db = frame @ (-sun)
            f2 = (rpol / req) ** 2
            A = db[0] ** 2 + db[1] ** 2 + db[2] ** 2 / f2
            B = 2 * (rb0[0] * db[0] + rb0[1] * db[1] + rb0[2] * db[2] / f2)
            Cc = rb0[0] ** 2 + rb0[1] ** 2 + rb0[2] ** 2 / f2 - 1.0
            disc = B * B - 4 * A * Cc
            if disc > 0:
                k = (-B - math.sqrt(disc)) / (2 * A)
                if k > 0:
                    p_body = rb0 + k * db
                    p = frame.T @ p_body                     # ICRS, em raios
                    if p @ -u > 0:
                        shadow = (float(p @ e_t), float(p @ n_t))
        out.append(MoonView(mid, name, float(x), float(y), float(z),
                            MOON_MAG.get(mid, 10.0), status, shadow))
    return out


def moon_states(engine, planet: str, times: list[dt.datetime]) -> dict:
    """Estado de cada lua em muitos instantes, vetorizado.

    Devolve {nome: {"transito", "ocultacao", "eclipse", "sombra": arrays
    booleanos}}. Os testes de disco e sombra só dependem da orientação do
    polo (o giro do planeta não importa para um elipsoide), então um único
    polo serve para a noite inteira.
    """
    from .planets import series

    data = series(engine, planet, times)
    if not covers(planet, float(data["jd"][0])) or not covers(planet, float(data["jd"][-1])):
        return {}
    s = _system(planet)
    req, rpol = radii_km(planet)
    f2 = (rpol / req) ** 2
    u = data["u"]                                  # (3, N)
    sun = data["sun_dir"]
    pole = data["pole"]
    # base do plano do céu em cada instante
    zhat = np.array([0.0, 0.0, 1.0])
    e_t = np.cross(zhat[:, None], u, axis=0)
    e_t /= np.linalg.norm(e_t, axis=0)
    n_t = np.cross(u, e_t, axis=0)
    # base do corpo (sem o giro): x no nó, z no polo
    q = np.cross(zhat, pole)
    q /= np.linalg.norm(q)
    B = np.stack([q, np.cross(pole, q), pole])     # corpo <- ICRS
    pos = moon_positions(planet, data["jd"])
    out = {}
    for mid, name in zip(s["ids"], s["names"]):
        r = pos[mid] / req                         # (3, N) em raios
        depth = np.sum(r * -u, axis=0)
        dist = data["dist"] * AU_KM / req
        persp = dist / (dist - depth)
        x = np.sum(r * e_t, axis=0) * persp
        y = np.sum(r * n_t, axis=0) * persp
        # dentro do disco projetado: raio pela direção de visada × elipsoide
        rb = B @ r
        vb = B @ (-u)
        # projeção no plano do céu, em coordenadas do corpo
        perp = rb - np.sum(rb * vb, axis=0) * vb
        cosb = np.sqrt(np.clip(1 - vb[2] ** 2, 0, 1))
        flat = np.sqrt(cosb ** 2 * f2 + vb[2] ** 2)
        # componentes no plano do céu: ao longo do polo projetado e do equador
        pz = perp[2] / np.maximum(cosb, 1e-6)
        pe2 = np.maximum(np.sum(perp ** 2, axis=0) - pz ** 2, 0.0)
        inside = (pe2 + (pz / flat) ** 2) < 1.0
        transit = inside & (depth > 0)
        occult = inside & (depth < 0)
        along = np.sum(r * sun, axis=0)
        sperp = r - along * sun
        sb = B @ sperp
        eclipse = (along < 0) & ((sb[0] ** 2 + sb[1] ** 2 + sb[2] ** 2 / f2) < 1.0) & ~transit & ~occult
        # sombra: reta r − k·sol cruza o elipsoide do lado visível
        db = B @ (-sun)
        A = db[0] ** 2 + db[1] ** 2 + db[2] ** 2 / f2
        Bq = 2 * (rb[0] * db[0] + rb[1] * db[1] + rb[2] * db[2] / f2)
        Cq = rb[0] ** 2 + rb[1] ** 2 + rb[2] ** 2 / f2 - 1.0
        disc = Bq * Bq - 4 * A * Cq
        k = (-Bq - np.sqrt(np.maximum(disc, 0))) / (2 * A)
        hitp = rb + k * db
        facing = np.sum(hitp * vb, axis=0) > 0
        shadow = (along > 0) & (disc > 0) & (k > 0) & facing
        out[name] = {"transito": transit, "ocultacao": occult, "eclipse": eclipse,
                     "sombra": shadow, "x": x, "y": y}
    return out


@dataclass
class MoonEvent:
    when_utc: dt.datetime
    moon: str
    kind: str      # transito | sombra | ocultacao | eclipse
    start: bool

    @property
    def text(self) -> str:
        if self.kind == "sombra":
            return f"{self.moon}: sombra {'entra no' if self.start else 'sai do'} disco"
        what = {"transito": "do trânsito", "ocultacao": "da ocultação",
                "eclipse": "do eclipse"}[self.kind]
        return f"{self.moon}: {'início' if self.start else 'fim'} {what}"


def moon_events(engine, planet: str, start: dt.datetime, end: dt.datetime,
                step_minutes: float = 2.0) -> list[MoonEvent]:
    """Inícios e fins de trânsitos, sombras, ocultações e eclipses
    (amostragem vetorizada; precisão de ``step_minutes``)."""
    n = int((end - start).total_seconds() / 60 / step_minutes) + 1
    times = [start + dt.timedelta(minutes=step_minutes * k) for k in range(n)]
    states = moon_states(engine, planet, times)
    out = []
    for name, st in states.items():
        for kind in ("transito", "ocultacao", "eclipse", "sombra"):
            arr = st[kind]
            for k in np.nonzero(arr[1:] != arr[:-1])[0]:
                out.append(MoonEvent(times[k + 1], name, kind, bool(arr[k + 1])))
    out.sort(key=lambda e: e.when_utc)
    return out


# --------------------------------------------------------------------------
# Grande Mancha Vermelha
@lru_cache(maxsize=1)
def _grs_data() -> dict:
    path = data_dir() / "grs.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def grs_longitude(when: dt.datetime, override: tuple | None = None) -> float:
    """Longitude da GMV no Sistema II (graus), interpolada da tabela JUPOS
    e extrapolada pela deriva média depois do último valor.

    ``override`` = (longitude, data) informado pelo usuário: vale como novo
    ponto de partida, com a mesma deriva.
    """
    d = _grs_data()
    drift = float(d.get("drift_deg_per_year", 16.0))
    day = when.date() if isinstance(when, dt.datetime) else when
    if override is not None:
        lon0, date0 = override
        years = (day - date0).days / 365.25
        return (lon0 + drift * years) % 360.0
    table = [(dt.date.fromisoformat(s), float(v)) for s, v in d.get("table", [])]
    if not table:
        return 0.0
    if day <= table[0][0]:
        return table[0][1] % 360.0
    for (d0, v0), (d1, v1) in zip(table, table[1:]):
        if d0 <= day <= d1:
            f = (day - d0).days / max((d1 - d0).days, 1)
            return (v0 + f * (v1 - v0)) % 360.0
    d_last, v_last = table[-1]
    return (v_last + drift * (day - d_last).days / 365.25) % 360.0


def grs_transits(engine, start: dt.datetime, end: dt.datetime,
                 longitude: float) -> list[dt.datetime]:
    """Instantes em que a GMV cruza o meridiano central (CM II = longitude)."""
    from .planets import cm_series, series

    # CM II avança ~36°/h: amostras de 2 min dão ±1 min, interpoladas
    n = int((end - start).total_seconds() / 120) + 1
    times = [start + dt.timedelta(minutes=2 * k) for k in range(n)]
    cm2 = cm_series("Júpiter", series(engine, "Júpiter", times), "II")
    diff = (cm2 - longitude + 180.0) % 360.0 - 180.0
    out = []
    for k in np.nonzero((diff[:-1] < 0) & (diff[1:] >= 0) & (diff[1:] - diff[:-1] < 90))[0]:
        f = -diff[k] / (diff[k + 1] - diff[k])
        out.append(times[k] + (times[k + 1] - times[k]) * float(f))
    return out


def grs_texture_u() -> float:
    return float(_grs_data().get("texture_u", 0.3635))


def ring_radii_km() -> tuple[float, float]:
    d = _grs_data()
    return float(d.get("ring_inner_km", 70517.0)), float(d.get("ring_outer_km", 139536.0))


RING_FEATURES = [  # raios em km (para legendas)
    ("Anel C", 74658, 92000), ("Anel B", 92000, 117580),
    ("Divisão de Cassini", 117580, 122170), ("Anel A", 122170, 136775),
]


def next_ring_crossing(engine, start: dt.datetime, years: int = 20) -> dt.datetime | None:
    """Próxima passagem da Terra pelo plano dos anéis (B muda de sinal)."""
    from .planets import pole_icrs, series

    key = (start.date(), years, round(engine.topos.latitude.degrees, 1))
    if key in _CROSS_CACHE:
        return _CROSS_CACHE[key]
    n = int(365.25 * years / 10) + 1
    times = [start + dt.timedelta(days=10 * k) for k in range(n)]
    data = series(engine, "Saturno", times)
    poles = np.stack([pole_icrs("Saturno", jd) for jd in data["jd"]], axis=1)
    b = np.sum(poles * -data["u"], axis=0)                # seno de B
    hits = np.nonzero(np.sign(b[:-1]) != np.sign(b[1:]))[0]
    result = None
    if len(hits):
        k = int(hits[0])
        f = b[k] / (b[k] - b[k + 1])
        result = times[k] + (times[k + 1] - times[k]) * float(f)
    _CROSS_CACHE[key] = result
    return result


_CROSS_CACHE: dict = {}
