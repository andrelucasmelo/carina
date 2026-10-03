"""Ocultações pela Lua (v0.17 T3): estrelas até 6,5 e planetas.

Uma ocultação é a passagem da Lua na frente de um astro: ele some de uma
vez no limbo (imersão) e reaparece do outro lado (emersão). Como a Lua
está perto, a paralaxe desloca o disco em até 1° conforme o lugar — por
isso tudo é **topocêntrico**: os horários valem para o local escolhido.

Método
------
1. A posição astrométrica topocêntrica da Lua é amostrada a cada 5 min
   (vetorizado) e as estrelas a até 7,5° da eclíptica são pré-filtradas.
2. Para cada estrela, ``f(t) = separação − raio da Lua`` é avaliada na
   grade; onde o mínimo fica perto de zero, o mínimo é refinado (razão
   áurea) e, se negativo, as duas raízes são achadas por bisseção.
3. Estrelas recebem o movimento próprio até a data (HYG, J2000); a
   Lua vem do ``observe()`` do Skyfield (tempo de luz incluído). As duas
   posições ficam sem aberração — ela desloca ambas igualmente.

A precisão fica em poucos segundos frente às previsões publicadas; o
perfil do limbo (montanhas) não é modelado, e rasantes ficam como aviso.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .moon import MOON_RADIUS_KM, data_dir

AU_KM = 149597870.7
MAS = math.radians(1.0 / 3.6e6)
STEP_MIN = 5.0
PLANETS = ("Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno")


@dataclass
class Occultation:
    target: str
    kind: str                       # 'star' | 'planet'
    mag: float
    immersion_utc: dt.datetime | None
    emersion_utc: dt.datetime | None
    pa_immersion: float = 0.0       # ângulo de posição no limbo (graus)
    pa_emersion: float = 0.0
    dark_immersion: bool = True     # imersão no limbo escuro
    dark_emersion: bool = True
    moon_alt: float = 0.0           # altura da Lua no meio do evento (graus)
    sun_alt: float = 0.0            # altura do Sol no meio do evento
    illumination: float = 0.0
    min_sep_arcmin: float = 0.0     # distância mínima ao centro da Lua
    hip: int = 0

    @property
    def mid_utc(self) -> dt.datetime:
        a = self.immersion_utc or self.emersion_utc
        b = self.emersion_utc or self.immersion_utc
        return a + (b - a) / 2

    @property
    def duration_min(self) -> float:
        if self.immersion_utc and self.emersion_utc:
            return (self.emersion_utc - self.immersion_utc).total_seconds() / 60.0
        return 0.0

    @property
    def visible(self) -> bool:
        """Lua acima do horizonte e céu ao menos no crepúsculo."""
        return self.moon_alt > 2.0 and (self.sun_alt < -6.0 or
                                        (self.kind == "planet" or self.mag < 2.0)
                                        and self.sun_alt < 0.0)

    @property
    def graze(self) -> bool:
        """Passagem muito perto da borda: horários incertos."""
        return self.duration_min < 8.0

    @property
    def ident(self) -> str:
        return f"HIP {self.hip}" if self.hip else self.target

    def describe(self) -> str:
        from .localtime import to_local

        parts = []
        if self.immersion_utc:
            parts.append(f"some às {to_local(self.immersion_utc):%H:%M:%S} "
                         f"(limbo {'escuro' if self.dark_immersion else 'iluminado'})")
        if self.emersion_utc:
            parts.append(f"reaparece às {to_local(self.emersion_utc):%H:%M:%S} "
                         f"(limbo {'escuro' if self.dark_emersion else 'iluminado'})")
        text = "; ".join(parts)
        if self.graze:
            text += " — passagem rasante, horários incertos"
        return text


@lru_cache(maxsize=1)
def _stars():
    path = data_dir() / "occult_stars.npz"
    if not path.exists():
        return None
    d = np.load(path)
    return {k: d[k] for k in d.files}


def _star_vectors(stars, idx: np.ndarray, epoch_year: float) -> np.ndarray:
    dt_years = epoch_year - 2000.0
    dec = stars["dec"][idx] + stars["pmdec"][idx].astype(np.float64) * MAS * dt_years
    cosd = np.maximum(np.cos(stars["dec"][idx]), 1e-9)
    ra = stars["ra"][idx] + stars["pmra"][idx].astype(np.float64) * MAS * dt_years / cosd
    cd = np.cos(dec)
    return np.stack([cd * np.cos(ra), cd * np.sin(ra), np.sin(dec)], axis=1)


def _moon_state(engine, t):
    """(unitários (3,N) observador→Lua, raio angular (N,) em rad)."""
    pos = np.asarray(engine.site.at(t).observe(engine.eph["moon"]).position.au,
                     dtype=np.float64)
    dist = np.linalg.norm(pos, axis=0)
    return pos / dist, np.arcsin(MOON_RADIUS_KM / (dist * AU_KM))


def _pa(target: np.ndarray, center: np.ndarray) -> float:
    pole = np.array([0.0, 0.0, 1.0])
    n_t = pole - (pole @ center) * center
    n_t /= max(np.linalg.norm(n_t), 1e-12)
    e_t = np.cross(pole, center)
    e_t /= max(np.linalg.norm(e_t), 1e-12)
    return math.degrees(math.atan2(float(target @ e_t), float(target @ n_t))) % 360.0


def find_occultations(engine, start_utc: dt.datetime, end_utc: dt.datetime,
                      mag_limit: float = 6.5, planets: bool = True,
                      only_visible: bool = False) -> list[Occultation]:
    """Ocultações no período, ordenadas pelo meio do evento."""
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=dt.timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=dt.timezone.utc)
    n = int((end_utc - start_utc).total_seconds() / 60.0 / STEP_MIN) + 2
    times = [start_utc + dt.timedelta(minutes=STEP_MIN * i) for i in range(n)]
    t = engine.ts.from_datetimes(times)
    mvec, mrad = _moon_state(engine, t)                      # (3,N), (N,)

    targets: list[tuple[str, str, float, int, object]] = []  # nome, tipo, mag, hip, vetor/corpo
    stars = _stars()
    if stars is not None:
        sel = np.nonzero(stars["mag"] <= mag_limit)[0]
        epoch = start_utc.year + (start_utc.timetuple().tm_yday - 1) / 365.25
        svec = _star_vectors(stars, sel, epoch)
        # pré-filtro: a até 1,6° de algum ponto da trajetória da Lua
        # (amostrada a cada hora — anda ~0,55°/h)
        coarse = mvec[:, ::12]
        near = (svec @ coarse).max(axis=1) > math.cos(math.radians(1.6))
        for k in np.nonzero(near)[0]:
            i = sel[k]
            name = str(stars["name"][i]) or f"HIP {int(stars['hip'][i])}"
            targets.append((name, "star", float(stars["mag"][i]), int(stars["hip"][i]),
                            svec[k]))
    if planets:
        obs = engine.site.at(t)
        for name in PLANETS:
            p = np.asarray(obs.observe(engine.eph[engine.body_key(name)]).position.au,
                           dtype=np.float64)
            pu = p / np.linalg.norm(p, axis=0)
            if np.max(np.sum(pu * mvec, axis=0)) > math.cos(math.radians(1.6)):
                targets.append((name, "planet", 0.0, 0, name))

    out = []
    for name, kind, mag, hip, obj in targets:
        occ = _solve(engine, times, mvec, mrad, name, kind, mag, hip, obj)
        if occ is not None and (not only_visible or occ.visible):
            out.append(occ)
    out.sort(key=lambda o: o.mid_utc)
    return out


def _target_vec(engine, obj, when) -> np.ndarray:
    if isinstance(obj, np.ndarray):
        return obj
    t = engine.ts.from_datetime(when) if isinstance(when, dt.datetime) else when
    p = np.asarray(engine.site.at(t).observe(engine.eph[engine.body_key(obj)]).position.au,
                   dtype=np.float64)
    return p / np.linalg.norm(p, axis=0)


def _f(engine, obj, when: dt.datetime) -> float:
    """Separação ao centro − raio da Lua (rad) num instante."""
    t = engine.ts.from_datetime(when)
    mv, mr = _moon_state(engine, t)
    v = _target_vec(engine, obj, t)
    return math.acos(max(-1.0, min(1.0, float(v @ mv)))) - float(mr)


def _solve(engine, times, mvec, mrad, name, kind, mag, hip, obj) -> Occultation | None:
    if isinstance(obj, np.ndarray):
        sep = np.arccos(np.clip(obj @ mvec, -1, 1))
    else:
        tv = _target_vec(engine, obj, engine.ts.from_datetimes(times))
        sep = np.arccos(np.clip(np.sum(tv * mvec, axis=0), -1, 1))
    f = sep - mrad
    k = int(np.argmin(f))
    # a Lua anda ~2,5′ em 5 min: com margem de 4′ não se perde nenhuma corda
    if f[k] > math.radians(4.0 / 60.0):
        return None
    lo = times[max(k - 1, 0)]
    hi = times[min(k + 1, len(times) - 1)]
    # mínimo exato
    g = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = 0.0, (hi - lo).total_seconds()
    fn = lambda x: _f(engine, obj, lo + dt.timedelta(seconds=x))  # noqa: E731
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = fn(c), fn(d)
    while b - a > 2.0:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = fn(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = fn(d)
    tmin = lo + dt.timedelta(seconds=(a + b) / 2.0)
    fmin = fn((a + b) / 2.0)
    if fmin >= 0:
        return None

    def root(t0: dt.datetime, t1: dt.datetime) -> dt.datetime | None:
        f0, f1 = _f(engine, obj, t0), _f(engine, obj, t1)
        if (f0 > 0) == (f1 > 0):
            return None
        for _ in range(40):
            mid = t0 + (t1 - t0) / 2
            fm = _f(engine, obj, mid)
            if (fm > 0) == (f0 > 0):
                t0, f0 = mid, fm
            else:
                t1 = mid
            if (t1 - t0).total_seconds() < 0.5:
                break
        return t0 + (t1 - t0) / 2

    span = dt.timedelta(hours=2.5)        # duração máxima ~ 1,2 h
    imm = root(tmin - span, tmin)
    em = root(tmin, tmin + span)

    # geometria do evento
    def limb(when):
        tt = engine.ts.from_datetime(when)
        mv, _ = _moon_state(engine, tt)
        v = _target_vec(engine, obj, tt)
        s = np.asarray(engine.site.at(tt).observe(engine.eph["sun"]).position.au,
                       dtype=np.float64)
        s /= np.linalg.norm(s)
        pa_star = _pa(v - (v @ mv) * mv, mv)
        pa_sun = _pa(s, mv)
        diff = abs((pa_star - pa_sun + 180.0) % 360.0 - 180.0)
        return pa_star, diff > 90.0

    pa_i, dark_i = limb(imm) if imm else (0.0, True)
    pa_e, dark_e = limb(em) if em else (0.0, True)
    tt = engine.ts.from_datetime(tmin)
    obs = engine.site.at(tt)
    moon_alt = obs.observe(engine.eph["moon"]).apparent().altaz()[0].degrees
    sun_alt = obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees
    from skyfield import almanac

    illum = float(almanac.fraction_illuminated(engine.eph, "moon", tt))
    if kind == "planet":
        try:
            from skyfield.magnitudelib import planetary_magnitude

            mag = float(planetary_magnitude(obs.observe(
                engine.eph[engine.body_key(obj)]).apparent()))
        except Exception:
            mag = 0.0
    mv, mr = _moon_state(engine, tt)
    return Occultation(
        target=name, kind=kind, mag=mag, immersion_utc=imm, emersion_utc=em,
        pa_immersion=pa_i, pa_emersion=pa_e, dark_immersion=dark_i,
        dark_emersion=dark_e, moon_alt=float(moon_alt), sun_alt=float(sun_alt),
        illumination=illum,
        min_sep_arcmin=math.degrees(fmin + float(mr)) * 60.0, hip=hip,
    )
