"""Núcleo planetário (v0.18 T1, ADR-048): estado, orientação e aparições.

Para cada planeta, o que quem observa quer saber:

- **agora**: onde está, quão alto, brilho, tamanho aparente, fase (Mercúrio,
  Vênus e Marte), elongação (manhã ou tarde), se está retrógrado;
- **orientação do disco**: eixo de rotação (IAU, ``pck00008.tpc``), o
  meridiano central (Marte; Júpiter nos Sistemas II e III) e a inclinação
  dos anéis de Saturno;
- **melhor época**: oposições (externos) e maiores elongações (internos)
  nos próximos anos, com diâmetro, brilho e a altura no céu do observador,
  e a **temporada de visibilidade** (altura no céu escuro, dia a dia).

Posições pelo Skyfield/DE440s (caminho completo ``observe().apparent()``).
O DE440s só traz o **baricentro** dos sistemas de Júpiter e Saturno; o
centro do planeta é corrigido em :mod:`core.satellites` pelas massas das
luas (até ~300 km em Saturno, por causa de Titã).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from .formats import num

UTC = dt.timezone.utc
AU_KM = 149597870.7
C_KM_S = 299792.458

PLANETS = ("Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno")
INNER = ("Mercúrio", "Vênus")
NAIF_ID = {"Mercúrio": 199, "Vênus": 299, "Marte": 499, "Júpiter": 599,
           "Saturno": 699, "Urano": 799, "Netuno": 899}
TEXTURE = {"Mercúrio": "mercury.jpg", "Vênus": "venus.jpg", "Marte": "mars.jpg",
           "Júpiter": "jupiter.jpg", "Saturno": "saturn.jpg", "Urano": "uranus.jpg",
           "Netuno": "neptune.jpg"}
# Sistema II de Júpiter (IAU/Meeus): rotação média das faixas temperadas
JUPITER_SYS2 = (43.3, 870.270)

DESCRIPTION = {
    "Mercúrio": "O menor planeta e o mais próximo do Sol. Nunca se afasta mais de 28° "
                "dele: só aparece baixo, no crepúsculo, perto das maiores elongações. "
                "Ao telescópio mostra fases, como uma pequena Lua.",
    "Vênus": "O astro mais brilhante depois do Sol e da Lua, coberto de nuvens. "
             "Mostra fases bem visíveis ao telescópio — e fica maior quando é uma "
             "foice fina, por estar mais perto de nós.",
    "Marte": "O planeta vermelho. A cada 26 meses passa perto da Terra (oposição) e o "
             "disco cresce o bastante para mostrar calotas polares e manchas escuras "
             "como Syrtis Major. Longe da oposição, é só um ponto alaranjado.",
    "Júpiter": "O gigante: faixas de nuvens visíveis até em telescópios pequenos, a "
               "Grande Mancha Vermelha e as quatro luas galileanas, que mudam de "
               "posição de hora em hora.",
    "Saturno": "Os anéis aparecem em qualquer telescópio a partir de 30×. A inclinação "
               "deles muda ao longo dos anos: abertos, mostram a divisão de Cassini; "
               "de perfil (a cada ~15 anos), quase somem. Titã aparece até ao binóculo.",
    "Urano": "No limite do olho nu em céu escuro (magnitude 5,7). Ao telescópio, um "
             "pequeno disco azul-esverdeado sem detalhes.",
    "Netuno": "Só com binóculo ou telescópio (magnitude 7,8). Um disco azul minúsculo; "
              "o desafio é reconhecê-lo entre as estrelas — use a carta de busca.",
}


@lru_cache(maxsize=1)
def _pck() -> dict:
    from skyfield.api import Loader
    from skyfield.planetarylib import PlanetaryConstants

    from ..config import package_ephemeris_dir

    pc = PlanetaryConstants()
    pc.read_text(Loader(str(package_ephemeris_dir()), verbose=False)("pck00008.tpc"))
    return pc.variables


def radii_km(name: str) -> tuple[float, float]:
    """(equatorial, polar) em km."""
    r = _pck()[f"BODY{NAIF_ID[name]}_RADII"]
    return float(r[0]), float(r[2])


def pole_icrs(name: str, jd_tdb: float) -> np.ndarray:
    """Polo norte de rotação (unitário ICRS) pelo modelo IAU."""
    v = _pck()
    bid = NAIF_ID[name]
    T = (jd_tdb - 2451545.0) / 36525.0
    ra0, ra1, _ = v[f"BODY{bid}_POLE_RA"]
    de0, de1, _ = v[f"BODY{bid}_POLE_DEC"]
    ra, de = ra0 + ra1 * T, de0 + de1 * T
    if bid == 899:      # Netuno: termo de precessão N
        n = math.radians(357.85 + 52.316 * T)
        ra += 0.70 * math.sin(n)
        de -= 0.51 * math.cos(n)
    ra, de = math.radians(ra), math.radians(de)
    return np.array([math.cos(de) * math.cos(ra), math.cos(de) * math.sin(ra), math.sin(de)])


def prime_meridian(name: str, jd_tdb: float, system: str = "III") -> float:
    """Ângulo W (graus) do meridiano principal, medido no equador a partir
    do nó ascendente sobre o equador celeste (convenção IAU)."""
    d = jd_tdb - 2451545.0
    if name == "Júpiter" and system == "II":
        w0, w1 = JUPITER_SYS2
    else:
        w0, w1, _ = _pck()[f"BODY{NAIF_ID[name]}_PM"]
    if NAIF_ID[name] == 899:
        T = d / 36525.0
        w0 = w0 - 0.48 * math.sin(math.radians(357.85 + 52.316 * T))
    return (w0 + w1 * d) % 360.0


def body_frame(name: str, jd_tdb: float, system: str = "III") -> np.ndarray:
    """Matriz 3×3 cujas linhas são X (meridiano principal), Y e Z (polo)
    do referencial do planeta, em ICRS: ``v_corpo = M @ v_icrs``."""
    p = pole_icrs(name, jd_tdb)
    q = np.cross([0.0, 0.0, 1.0], p)
    q /= np.linalg.norm(q)
    w = math.radians(prime_meridian(name, jd_tdb, system))
    x = q * math.cos(w) + np.cross(p, q) * math.sin(w)
    y = np.cross(p, x)
    return np.stack([x, y, p])


def _pa(target: np.ndarray, center: np.ndarray) -> float:
    pole = np.array([0.0, 0.0, 1.0])
    n_t = pole - (pole @ center) * center
    n_t /= max(np.linalg.norm(n_t), 1e-12)
    e_t = np.cross(pole, center)
    e_t /= max(np.linalg.norm(e_t), 1e-12)
    return math.degrees(math.atan2(float(target @ e_t), float(target @ n_t))) % 360.0


@dataclass
class PlanetState:
    name: str
    when_utc: dt.datetime
    ra: float                 # graus, astrométrica J2000
    dec: float
    alt: float                # graus (local)
    az: float
    distance_au: float
    sun_distance_au: float
    magnitude: float
    diameter: float           # segundos de arco (equatorial)
    polar_diameter: float     # segundos de arco (aparente, com a inclinação)
    phase_angle: float        # graus (Sol–planeta–observador)
    illumination: float       # 0..1
    elongation: float         # graus do Sol
    evening: bool             # a leste do Sol: visível ao anoitecer
    rate: float               # graus/dia em longitude eclíptica (< 0 = retrógrado)
    pa_axis: float            # ângulo de posição do polo norte (graus)
    pa_bright_limb: float
    sub_obs_lat: float        # latitude do ponto sub-observador (graus)
    cm: float                 # meridiano central, longitude oeste (Sistema III)
    cm2: float | None = None  # Júpiter: Sistema II
    ring_tilt: float | None = None       # Saturno: B (graus; + = face norte)
    ring_tilt_sun: float | None = None   # Saturno: B' (anéis iluminados pelo Sol)
    constellation: str = ""
    u_icrs: np.ndarray = field(default=None, repr=False)     # observador → planeta
    sun_dir: np.ndarray = field(default=None, repr=False)    # planeta → Sol (ICRS)
    frame: np.ndarray = field(default=None, repr=False)      # body_frame (Sistema III)
    jd_tdb: float = 0.0       # instante de emissão da luz (já com o tempo-luz)

    @property
    def light_minutes(self) -> float:
        return self.distance_au * AU_KM / C_KM_S / 60.0

    @property
    def retrograde(self) -> bool:
        return self.rate < 0

    @property
    def phase_name(self) -> str:
        k = self.illumination
        if k > 0.97:
            return "disco cheio"
        if k > 0.6:
            return "gibosa"
        if k > 0.4:
            return "meia fase (dicotomia)"
        if k > 0.05:
            return "crescente (foice)"
        return "foice finíssima"

    @property
    def visibility(self) -> str:
        """Resumo de quando ele aparece no céu."""
        if self.elongation < 12:
            return "perdido no brilho do Sol"
        side = "ao anoitecer, no oeste" if self.evening else "antes do amanhecer, no leste"
        if self.name in INNER:
            return f"visível {side}"
        if self.elongation > 150:
            return "visível a noite toda (perto da oposição)"
        if self.evening:
            return "visível no início da noite" if self.elongation < 90 else \
                "visível desde o anoitecer até depois da meia-noite"
        return "visível na madrugada" if self.elongation < 90 else \
            "nasce à noite e fica até o amanhecer"


def _times(engine, when):
    if isinstance(when, dt.datetime):
        return engine.ts.from_datetime(when if when.tzinfo else when.replace(tzinfo=UTC))
    return engine.ts.from_datetimes(list(when))


def planet_state(engine, name: str, when: dt.datetime | None = None,
                 constellation_fn=None) -> PlanetState:
    """Estado do planeta visto do observador no instante dado."""
    from skyfield.framelib import ecliptic_frame
    from skyfield.magnitudelib import planetary_magnitude

    if when is None:
        when = engine.time.current_datetime()
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    t = engine.ts.from_datetime(when)
    obs = engine.site.at(t)
    body = engine.eph[engine.body_key(name)]
    astr = obs.observe(body)
    app = astr.apparent()
    sun = obs.observe(engine.eph["sun"]).apparent()
    pv = np.asarray(app.position.au, dtype=np.float64)
    sv = np.asarray(sun.position.au, dtype=np.float64)
    dist = float(np.linalg.norm(pv))
    u = pv / dist
    sun_from_planet = sv - pv
    sdist = float(np.linalg.norm(sun_from_planet))
    sdir = sun_from_planet / sdist
    cos_i = float(sdir @ (-u))
    phase = math.degrees(math.acos(max(-1.0, min(1.0, cos_i))))
    illum = (1.0 + math.cos(math.radians(phase))) / 2.0
    su = sv / np.linalg.norm(sv)
    elong = math.degrees(math.acos(max(-1.0, min(1.0, float(u @ su)))))
    lam_p = astr.frame_latlon(ecliptic_frame)[1].degrees
    lam_s = obs.observe(engine.eph["sun"]).frame_latlon(ecliptic_frame)[1].degrees
    evening = ((lam_p - lam_s) % 360.0) < 180.0
    # taxa em longitude: diferença de 1 dia
    t2 = engine.ts.from_datetime(when + dt.timedelta(days=1))
    lam2 = engine.site.at(t2).observe(body).frame_latlon(ecliptic_frame)[1].degrees
    rate = (lam2 - lam_p + 180.0) % 360.0 - 180.0
    try:
        mag = float(planetary_magnitude(app))
    except Exception:
        mag = float("nan")
    alt, az, _ = app.altaz()
    ra, dec, _ = astr.radec()
    req, rpol = radii_km(name)
    jd = t.tdb - dist * AU_KM / C_KM_S / 86400.0       # tempo-luz
    frame = body_frame(name, jd)
    pole = frame[2]
    v_obs = frame @ (-u)
    sub_lat = math.degrees(math.asin(max(-1.0, min(1.0, float(v_obs[2])))))
    lon_e = math.degrees(math.atan2(v_obs[1], v_obs[0]))
    cm = (-lon_e) % 360.0
    cm2 = None
    if name == "Júpiter":
        f2 = body_frame(name, jd, "II")
        v2 = f2 @ (-u)
        cm2 = (-math.degrees(math.atan2(v2[1], v2[0]))) % 360.0
    diam = 2.0 * math.degrees(math.atan(req / (dist * AU_KM))) * 3600.0
    b = math.radians(sub_lat)
    f = math.sqrt(math.cos(b) ** 2 * (rpol / req) ** 2 + math.sin(b) ** 2)
    ring = ring_sun = None
    if name == "Saturno":
        ring = sub_lat
        ring_sun = math.degrees(math.asin(max(-1.0, min(1.0, float(pole @ sdir)))))
    const = ""
    if constellation_fn is not None:
        try:
            const = constellation_fn(np.asarray(astr.position.au) / dist) or ""
        except Exception:
            const = ""
    return PlanetState(
        name=name, when_utc=when, ra=float(ra._degrees), dec=float(dec.degrees),
        alt=float(alt.degrees), az=float(az.degrees), distance_au=dist,
        sun_distance_au=sdist, magnitude=mag, diameter=diam, polar_diameter=diam * f,
        phase_angle=phase, illumination=illum, elongation=elong, evening=evening,
        rate=float(rate), pa_axis=_pa(pole, u), pa_bright_limb=_pa(sdir, u),
        sub_obs_lat=sub_lat, cm=cm, cm2=cm2, ring_tilt=ring, ring_tilt_sun=ring_sun,
        constellation=const, u_icrs=u, sun_dir=sdir, frame=frame, jd_tdb=jd,
    )


# --------------------------------------------------------------------------
# aparições: oposições, conjunções e maiores elongações
@dataclass
class Apparition:
    when_utc: dt.datetime
    kind: str                 # oposicao | conjuncao | conj_inferior | conj_superior
    #                           elong_leste | elong_oeste
    planet: str
    elongation: float
    diameter: float           # ″
    magnitude: float
    illumination: float
    dec: float
    altitude: float           # culminação (oposição) ou altura no crepúsculo (elongação)
    note: str = ""

    @property
    def title(self) -> str:
        return {
            "oposicao": "Oposição", "conjuncao": "Conjunção com o Sol",
            "conj_inferior": "Conjunção inferior", "conj_superior": "Conjunção superior",
            "elong_leste": "Maior elongação leste (tarde)",
            "elong_oeste": "Maior elongação oeste (manhã)",
        }[self.kind]


def series(engine, name: str, times: list[dt.datetime]) -> dict:
    """Grandezas vetorizadas para muitos instantes: direção do planeta
    (``u``, ICRS, observador → planeta), direção do Sol vista do planeta,
    distância (UA) e o polo IAU (lento: um só vetor no meio do intervalo)."""
    t = engine.ts.from_datetimes(times)
    obs = engine.site.at(t)
    p = np.asarray(obs.observe(engine.eph[engine.body_key(name)]).apparent().position.au,
                   np.float64)
    s = np.asarray(obs.observe(engine.eph["sun"]).apparent().position.au, np.float64)
    d = np.linalg.norm(p, axis=0)
    sun_from = s - p
    jd = np.asarray(t.tdb) - d * AU_KM / C_KM_S / 86400.0
    return {"t": t, "u": p / d, "dist": d, "jd": jd,
            "sun_dir": sun_from / np.linalg.norm(sun_from, axis=0),
            "pole": pole_icrs(name, float(jd[len(jd) // 2]))}


def cm_series(name: str, data: dict, system: str = "III") -> np.ndarray:
    """Meridiano central (longitude oeste, graus) vetorizado.

    Com X = Q·cos W + (p×Q)·sin W, a longitude leste do ponto sub-observador
    é λ_Q − W, onde λ_Q é o ângulo dele medido a partir do nó Q; a
    longitude oeste (meridiano central) é W − λ_Q.
    """
    p = data["pole"]
    q = np.cross([0.0, 0.0, 1.0], p)
    q /= np.linalg.norm(q)
    pq = np.cross(p, q)
    v = -data["u"]
    lam_q = np.degrees(np.arctan2(pq @ v, q @ v))
    w = np.array([prime_meridian(name, jd, system) for jd in data["jd"]])
    return (w - lam_q) % 360.0


def _elong_series(engine, name, start, days, step=1.0):
    n = int(days / step) + 1
    times = [start + dt.timedelta(days=step * i) for i in range(n)]
    t = engine.ts.from_datetimes(times)
    e = engine.earth.at(t)
    p = np.asarray(e.observe(engine.eph[engine.body_key(name)]).position.au, np.float64)
    s = np.asarray(e.observe(engine.eph["sun"]).position.au, np.float64)
    d = np.linalg.norm(p, axis=0)
    el = np.degrees(np.arccos(np.clip(np.sum(p * s, axis=0) / (d * np.linalg.norm(s, axis=0)),
                                      -1, 1)))
    return times, el, d


def _elong_at(engine, name, when) -> float:
    t = engine.ts.from_datetime(when)
    e = engine.earth.at(t)
    p = np.asarray(e.observe(engine.eph[engine.body_key(name)]).position.au, np.float64)
    s = np.asarray(e.observe(engine.eph["sun"]).position.au, np.float64)
    return math.degrees(math.acos(max(-1.0, min(1.0, float(p @ s / np.linalg.norm(p)
                                                          / np.linalg.norm(s))))))


def _refine(engine, name, t0, maximize, half_days=1.5):
    g = (math.sqrt(5) - 1) / 2
    a, b = -half_days * 86400.0, half_days * 86400.0
    sign = -1.0 if maximize else 1.0
    f = lambda x: sign * _elong_at(engine, name, t0 + dt.timedelta(seconds=x))  # noqa: E731
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    while b - a > 1800.0:                 # meia hora basta para a data do evento
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    x = (a + b) / 2
    return t0 + dt.timedelta(seconds=x), sign * f(x)


def _twilight_altitude(engine, name, when, evening: bool) -> float:
    """Altura do planeta no fim do crepúsculo civil (Sol a −6°) do dia."""
    from .twilight import night_info

    info = night_info(engine, when)
    ref = info.civil_dusk if evening else info.civil_dawn
    if ref is None:
        return float("nan")
    t = engine.ts.from_datetime(ref)
    alt = engine.site.at(t).observe(engine.eph[engine.body_key(name)]).apparent().altaz()[0]
    return float(alt.degrees)


def apparitions(engine, name: str, start: dt.datetime, years: float = 3.0) -> list[Apparition]:
    """Oposições/conjunções (externos) ou elongações/conjunções (internos)."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    days = int(years * 365.25) + 2
    # começa 3 dias antes: um extremo nas primeiras horas também precisa de
    # vizinhos dos dois lados para ser reconhecido
    times, el, dist = _elong_series(engine, name, start - dt.timedelta(days=3), days + 3)
    lat = engine.topos.latitude.degrees
    out = []
    for i in range(1, len(times) - 1):
        is_max = el[i] >= el[i - 1] and el[i] > el[i + 1]
        is_min = el[i] <= el[i - 1] and el[i] < el[i + 1]
        if not (is_max or is_min):
            continue
        when, e = _refine(engine, name, times[i], maximize=is_max)
        if when < start - dt.timedelta(hours=12):
            continue
        st = planet_state(engine, name, when)
        if name in INNER:
            if is_max:
                kind = "elong_leste" if st.evening else "elong_oeste"
                alt = _twilight_altitude(engine, name, when, st.evening)
                note = (f"{num(alt, 0)}° de altura no fim do crepúsculo "
                        f"{'vespertino' if st.evening else 'matutino'}")
            else:
                # na inferior o planeta passa entre a Terra e o Sol
                kind = "conj_inferior" if st.distance_au < 1.0 else "conj_superior"
                alt, note = float("nan"), "invisível, junto ao Sol"
        else:
            if is_max and e > 150:
                kind = "oposicao"
                alt = 90.0 - abs(lat - st.dec)
                note = f"culmina a {num(alt, 0)}° por volta da meia-noite"
            elif is_min and e < 30:
                kind, alt, note = "conjuncao", float("nan"), "invisível, junto ao Sol"
            else:
                continue
        out.append(Apparition(when, kind, name, e, st.diameter, st.magnitude,
                              st.illumination, st.dec, alt, note))
    return out


def visibility_season(engine, name: str, start: dt.datetime, days: int = 400,
                      step_days: int = 2, dark_sun: float = -12.0) -> tuple[list, np.ndarray]:
    """Altura máxima do planeta no céu escuro, dia a dia (graus).

    Amostra cada noite a cada 30 min; devolve (datas, alturas). É a curva
    de "melhor época" da janela de planetas.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    from .localtime import from_local_naive, to_local

    day0 = to_local(start).date()
    dates = [day0 + dt.timedelta(days=k) for k in range(0, days, step_days)]
    offsets = np.arange(0, 24 * 60, 30)                       # meio-dia a meio-dia
    times = []
    for d in dates:
        noon = from_local_naive(dt.datetime.combine(d, dt.time(12))).astimezone(UTC)
        times.extend(noon + dt.timedelta(minutes=int(m)) for m in offsets)
    t = engine.ts.from_datetimes(times)
    obs = engine.site.at(t)
    palt = obs.observe(engine.eph[engine.body_key(name)]).apparent().altaz()[0].degrees
    salt = obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees
    palt = np.asarray(palt).reshape(len(dates), len(offsets))
    salt = np.asarray(salt).reshape(len(dates), len(offsets))
    alts = np.where(salt < dark_sun, palt, -90.0).max(axis=1)
    return dates, alts


def best_period(dates, alts, threshold: float = 30.0) -> tuple | None:
    """Maior trecho contínuo com altura no escuro acima do limiar."""
    best, cur = None, None
    for d, a in zip(dates, alts):
        if a >= threshold:
            cur = (cur[0], d) if cur else (d, d)
            if best is None or (cur[1] - cur[0]) > (best[1] - best[0]):
                best = cur
        else:
            cur = None
    return best


def best_epoch_text(engine, name: str, start: dt.datetime, aps=None) -> str:
    """Frase de "melhor época" para a ficha e a janela de planetas.

    ``aps``: aparições já calculadas (evita refazer a busca)."""
    from .localtime import to_local

    if aps is None:
        aps = apparitions(engine, name, start, 2.2 if name not in ("Urano", "Netuno") else 1.2)
    if name in INNER:
        els = [a for a in aps if a.kind.startswith("elong")]
        if not els:
            return ""
        parts = []
        for a in els[:2]:
            parts.append(f"{a.title.lower()} em {to_local(a.when_utc):%d/%m/%Y} "
                         f"({num(a.elongation, 0)}° do Sol; {a.note})")
        good = max(els[:4], key=lambda a: a.altitude if a.altitude == a.altitude else -99)
        return ("Próximas: " + "; ".join(parts) + ". A melhor dos próximos meses para o "
                f"seu local é a de {to_local(good.when_utc):%m/%Y}, a {num(good.altitude, 0)}° "
                "no crepúsculo.")
    ops = [a for a in aps if a.kind == "oposicao"]
    if not ops:
        return ""
    a = ops[0]
    return (f"Próxima oposição em {to_local(a.when_utc):%d/%m/%Y}: diâmetro de "
            f"{num(a.diameter)}″, magnitude {num(a.magnitude)}, {a.note}. Os meses em torno "
            "dela são a melhor época para observar e fotografar.")
