"""Visibilidade de um objeto numa noite: quando nasce, culmina e se põe.

Responde à pergunta mais frequente de quem observa — "dá para ver isto
hoje, e a que horas?" — para estrelas, céu profundo e corpos do Sistema
Solar, levando em conta a altitude mínima útil e o horizonte do quintal.

Como funciona
-------------
:class:`NightGrid` amostra as 24 h de meio-dia a meio-dia (hora local do
observador) a cada 10 min e guarda, por instante, a matriz ICRS→horizontal
(calculada de forma vetorizada), a altitude do Sol e a posição da Lua. A
mesma grade serve a qualquer número de objetos: para os de posição fixa a
altitude é um único produto matricial.

Os eventos (nascer, ocaso, culminação, entrada e saída da janela útil) são
localizados na grade e depois **refinados** com o instante exato — bisseção
para as passagens por um limiar, busca da razão áurea para o máximo — com
erro de segundos. O nascer e o ocaso usam o horizonte padrão dos almanaques
(−0,5667°, refração no horizonte; −0,8333° para o Sol, que soma o raio do
disco), para baterem com o ``skyfield.almanac``.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np

from .twilight import NightInfo, night_info

STAR_HORIZON_DEG = -0.5667     # refração padrão no horizonte
SUN_HORIZON_DEG = -0.8333      # idem + semidiâmetro do Sol
GRID_MINUTES = 10.0
DEFAULT_MIN_ALT = 20.0

_GRID_CACHE: "OrderedDict[tuple, NightGrid]" = OrderedDict()
_GRID_CACHE_MAX = 6


@dataclass
class Target:
    """O que se quer observar: um vetor ICRS fixo ou um corpo pelo nome."""

    icrs: np.ndarray | None = None
    body: str | None = None
    label: str = ""

    @classmethod
    def from_ref(cls, ref) -> "Target":
        """A partir de um :class:`core.objects.ObjectRef`."""
        if ref.icrs is not None:
            return cls(icrs=np.asarray(ref.icrs, dtype=np.float64), label=ref.name)
        return cls(body=str(ref.key), label=ref.name)

    @classmethod
    def from_radec(cls, ra: float, dec: float, label: str = "") -> "Target":
        cd = math.cos(dec)
        return cls(icrs=np.array([cd * math.cos(ra), cd * math.sin(ra),
                                  math.sin(dec)]), label=label)

    @property
    def horizon_deg(self) -> float:
        return SUN_HORIZON_DEG if self.body == "Sol" else STAR_HORIZON_DEG


def _noon_before(ref_utc: dt.datetime) -> dt.datetime:
    """Meio-dia local (do observador) que abre a noite de ``ref_utc``."""
    from .localtime import to_local

    local = to_local(ref_utc)
    noon = local.replace(hour=12, minute=0, second=0, microsecond=0)
    if local < noon:
        noon -= dt.timedelta(days=1)
    return noon.astimezone(dt.timezone.utc)


@dataclass
class NightGrid:
    """Amostragem de 24 h (meio-dia → meio-dia) compartilhada pelos objetos."""

    engine: object
    start: dt.datetime
    step_minutes: float
    times: list[dt.datetime]
    mats: np.ndarray            # (T, 3, 3): v_horizontal = M @ v_icrs
    sun_alt: np.ndarray         # graus
    moon_vec: np.ndarray        # (T, 3) horizontal
    moon_alt: np.ndarray        # graus
    moon_illum: float
    night: NightInfo

    @property
    def n(self) -> int:
        return len(self.times)

    @property
    def dark_mask(self) -> np.ndarray:
        """Instantes de céu escuro: noite astronômica; onde ela não existe
        (verão em latitudes altas), cai para a náutica e depois para a
        noite civil — sempre há uma "noite" para planejar."""
        for limit in (-18.0, -12.0, -6.0, SUN_HORIZON_DEG):
            mask = self.sun_alt < limit
            if mask.any():
                return mask
        return np.zeros(self.n, dtype=bool)

    @property
    def dark_limit_deg(self) -> float:
        for limit in (-18.0, -12.0, -6.0, SUN_HORIZON_DEG):
            if (self.sun_alt < limit).any():
                return limit
        return SUN_HORIZON_DEG

    def index_of(self, when: dt.datetime) -> int:
        k = (when - self.start).total_seconds() / 60.0 / self.step_minutes
        return int(max(0, min(self.n - 1, round(k))))

    def altaz(self, icrs: np.ndarray):
        """Altitude e azimute (graus) de vetores ICRS fixos em toda a grade.

        ``icrs`` (3,) → arrays (T,); ``icrs`` (N, 3) → arrays (N, T).
        """
        v = np.asarray(icrs, dtype=np.float64)
        single = v.ndim == 1
        if single:
            v = v[np.newaxis, :]
        h = np.einsum("tij,nj->nti", self.mats, v)          # (N, T, 3)
        alt = np.degrees(np.arcsin(np.clip(h[..., 2], -1.0, 1.0)))
        az = np.degrees(np.arctan2(h[..., 1], h[..., 0])) % 360.0
        if single:
            return alt[0], az[0]
        return alt, az

    def body_altaz(self, name: str):
        """Altitude e azimute (graus) de um corpo do Sistema Solar."""
        eng = self.engine
        ts = eng.ts.from_datetimes(self.times)
        app = eng.site.at(ts).observe(eng.eph[eng.body_key(name)]).apparent()
        alt, az, _ = app.altaz()
        return np.asarray(alt.degrees), np.asarray(az.degrees) % 360.0

    def target_altaz(self, target: Target):
        if target.icrs is not None:
            return self.altaz(target.icrs)
        return self.body_altaz(target.body)

    def moon_separation(self, alt: np.ndarray, az: np.ndarray, idx=None) -> np.ndarray:
        """Separação angular (graus) entre o alvo e a Lua.

        ``alt``/``az`` cobrem a grade inteira (último eixo = tempo) ou só os
        instantes ``idx`` da grade.
        """
        moon = self.moon_vec if idx is None else self.moon_vec[np.asarray(idx)]
        a = np.radians(alt)
        z = np.radians(az)
        ca = np.cos(a)
        v = np.stack([ca * np.cos(z), ca * np.sin(z), np.sin(a)], axis=-1)
        dots = np.clip(np.sum(v * moon, axis=-1), -1.0, 1.0)
        return np.degrees(np.arccos(dots))


def night_grid(engine, ref_utc: dt.datetime,
               step_minutes: float = GRID_MINUTES) -> NightGrid:
    """Grade da noite que contém ``ref_utc`` (cacheada por local e data)."""
    start = _noon_before(ref_utc)
    topos = getattr(engine, "topos", None)
    loc_key = (round(topos.latitude.degrees, 5), round(topos.longitude.degrees, 5),
               round(topos.elevation.m, 1)) if topos is not None else None
    key = (id(engine), loc_key, start, step_minutes)
    cached = _GRID_CACHE.get(key)
    if cached is not None:
        _GRID_CACHE.move_to_end(key)
        return cached

    n = int(round(24 * 60 / step_minutes))
    times = [start + dt.timedelta(minutes=step_minutes * i) for i in range(n + 1)]
    ts = engine.ts.from_datetimes(times)
    obs = engine.site.at(ts)
    rows = []
    for alt_deg, az_deg in ((0.0, 0.0), (0.0, 90.0), (90.0, 0.0)):
        p = obs.from_altaz(alt_degrees=alt_deg, az_degrees=az_deg).position.au
        rows.append(p / np.linalg.norm(p, axis=0))
    mats = np.moveaxis(np.stack(rows), 2, 0)               # (T, 3, 3)

    sun_alt = obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees
    malt, maz, _ = obs.observe(engine.eph["moon"]).apparent().altaz()
    ma, mz = np.radians(malt.degrees), np.radians(maz.degrees)
    moon_vec = np.stack([np.cos(ma) * np.cos(mz), np.cos(ma) * np.sin(mz),
                         np.sin(ma)], axis=1)
    mid = engine.ts.from_datetime(start + dt.timedelta(hours=12))
    grid = NightGrid(
        engine=engine, start=start, step_minutes=step_minutes, times=times,
        mats=mats, sun_alt=np.asarray(sun_alt), moon_vec=moon_vec,
        moon_alt=np.asarray(malt.degrees),
        moon_illum=float(engine.moon_illumination(mid)),
        night=night_info(engine, ref_utc),
    )
    _GRID_CACHE[key] = grid
    while len(_GRID_CACHE) > _GRID_CACHE_MAX:
        _GRID_CACHE.popitem(last=False)
    return grid


def clear_cache() -> None:
    """Esquece as grades (troca de local ou de efeméride)."""
    _GRID_CACHE.clear()


# ---------------------------------------------------------------------------
# Resultado por objeto
# ---------------------------------------------------------------------------

@dataclass
class Visibility:
    """Visibilidade de um alvo na noite da grade. Instantes em UTC."""

    target: Target
    grid: NightGrid
    min_alt: float                         # graus (limiar útil pedido)
    alts: np.ndarray                       # graus, na grade inteira
    azs: np.ndarray
    rise_utc: dt.datetime | None = None
    transit_utc: dt.datetime | None = None
    set_utc: dt.datetime | None = None
    transit_alt: float = -90.0
    always_up: bool = False                # circumpolar nesta data
    never_up: bool = False
    segments: list[tuple[dt.datetime, dt.datetime]] = field(default_factory=list)
    best_utc: dt.datetime | None = None
    best_alt: float = -90.0
    best_az: float = 0.0
    dark_start: dt.datetime | None = None
    dark_end: dt.datetime | None = None
    blocked_minutes: float = 0.0           # acima do limiar mas atrás do horizonte
    moon_sep_best: float = 180.0           # graus
    moon_alt_best: float = -90.0

    # -- derivados -----------------------------------------------------
    @property
    def window_start(self) -> dt.datetime | None:
        return self.segments[0][0] if self.segments else None

    @property
    def window_end(self) -> dt.datetime | None:
        return self.segments[-1][1] if self.segments else None

    @property
    def window_minutes(self) -> float:
        return sum((b - a).total_seconds() for a, b in self.segments) / 60.0

    @property
    def dark_minutes(self) -> float:
        if self.dark_start is None or self.dark_end is None:
            return 0.0
        return max(0.0, (self.dark_end - self.dark_start).total_seconds() / 60.0)

    @property
    def dark_fraction(self) -> float:
        """Fração da noite escura em que o alvo está utilizável."""
        d = self.dark_minutes
        return min(1.0, self.window_minutes / d) if d > 0 else 0.0

    @property
    def observable(self) -> bool:
        return bool(self.segments)

    def alt_at(self, when: dt.datetime) -> float:
        """Altitude (graus) interpolada na grade."""
        k = (when - self.grid.start).total_seconds() / 60.0 / self.grid.step_minutes
        return float(np.interp(k, np.arange(len(self.alts)), self.alts))

    def is_up(self, when: dt.datetime, horizon=None) -> bool:
        """Acima do horizonte (do quintal, se dado) no instante?"""
        alt = self.alt_at(when)
        k = self.grid.index_of(when)
        limit = horizon.altitude_at(self.azs[k]) if horizon is not None else 0.0
        return alt > max(0.0, limit)

    def airmass_best(self) -> float:
        return airmass(self.best_alt)


def airmass(alt_deg: float) -> float:
    """Massa de ar de Kasten & Young (1989); infinita abaixo do horizonte."""
    if alt_deg <= 0.0:
        return float("inf")
    return 1.0 / (math.sin(math.radians(alt_deg))
                  + 0.50572 * (alt_deg + 6.07995) ** -1.6364)


# -- instantes exatos ----------------------------------------------------------

def _exact_altaz(engine, target: Target, when: dt.datetime) -> tuple[float, float]:
    t = engine.ts.from_datetime(when)
    if target.icrs is not None:
        m = engine.horizontal_matrix(t)
        v = m @ target.icrs
        alt = math.degrees(math.asin(max(-1.0, min(1.0, float(v[2])))))
        az = math.degrees(math.atan2(float(v[1]), float(v[0]))) % 360.0
        return alt, az
    app = engine.site.at(t).observe(engine.eph[engine.body_key(target.body)]).apparent()
    alt, az, _ = app.altaz()
    return float(alt.degrees), float(az.degrees) % 360.0


def _bisect(f, t0: dt.datetime, t1: dt.datetime, iters: int = 12) -> dt.datetime:
    """Instante entre t0 e t1 em que f troca de sinal (f(t0)·f(t1) ≤ 0)."""
    f0 = f(t0)
    for _ in range(iters):
        tm = t0 + (t1 - t0) / 2
        fm = f(tm)
        if (fm >= 0) == (f0 >= 0):
            t0, f0 = tm, fm
        else:
            t1 = tm
    return t0 + (t1 - t0) / 2


def _golden_max(f, t0: dt.datetime, t1: dt.datetime, iters: int = 18):
    """Máximo de f em [t0, t1] (função unimodal no intervalo)."""
    g = (math.sqrt(5.0) - 1.0) / 2.0
    span = (t1 - t0).total_seconds()
    a, b = 0.0, span
    c, d = b - g * (b - a), a + g * (b - a)
    fc = f(t0 + dt.timedelta(seconds=c))
    fd = f(t0 + dt.timedelta(seconds=d))
    for _ in range(iters):
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(t0 + dt.timedelta(seconds=c))
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(t0 + dt.timedelta(seconds=d))
    x = (a + b) / 2.0
    when = t0 + dt.timedelta(seconds=x)
    return when, f(when)


def _crossings(values: np.ndarray) -> list[tuple[int, bool]]:
    """Índices i em que values troca de sinal entre i e i+1 (True = subida)."""
    pos = values >= 0
    idx = np.nonzero(pos[1:] != pos[:-1])[0]
    return [(int(i), bool(pos[i + 1])) for i in idx]


def _dark_interval(grid: NightGrid):
    info = grid.night
    pairs = {
        -18.0: (info.astro_dusk, info.astro_dawn),
        -12.0: (info.nautical_dusk, info.nautical_dawn),
        -6.0: (info.civil_dusk, info.civil_dawn),
        SUN_HORIZON_DEG: (info.sunset, info.sunrise),
    }
    start, end = pairs.get(grid.dark_limit_deg, (None, None))
    mask = grid.dark_mask
    if mask.any():
        idx = np.nonzero(mask)[0]
        start = start or grid.times[int(idx[0])]
        end = end or grid.times[int(idx[-1])]
    return start, end


# ---------------------------------------------------------------------------
# Cálculo principal
# ---------------------------------------------------------------------------

def compute_visibility(engine, target: Target, ref_utc: dt.datetime,
                       min_alt: float = DEFAULT_MIN_ALT, horizon=None,
                       grid: NightGrid | None = None,
                       refine: bool = True) -> Visibility:
    """Visibilidade de ``target`` na noite de ``ref_utc``.

    ``horizon`` (:class:`core.horizon.HorizonProfile`) recorta a janela
    útil: o alvo só conta como utilizável quando está acima do limiar
    ``min_alt`` **e** acima do perfil naquele azimute. Nascer e ocaso
    continuam geométricos (horizonte padrão dos almanaques).

    ``refine=False`` dispensa o refinamento exato (resolução da grade,
    10 min) — útil para pontuar centenas de objetos de uma vez.
    """
    grid = grid or night_grid(engine, ref_utc)
    alts, azs = grid.target_altaz(target)
    vis = Visibility(target=target, grid=grid, min_alt=float(min_alt),
                     alts=alts, azs=azs)
    times = grid.times
    step = dt.timedelta(minutes=grid.step_minutes)

    def exact_alt(when):
        return _exact_altaz(engine, target, when)[0]

    # 1) nascer e ocaso geométricos
    h0 = target.horizon_deg
    rel = alts - h0
    vis.always_up = bool((rel > 0).all())
    vis.never_up = bool((rel < 0).all())
    for i, rising in _crossings(rel):
        t0, t1 = times[i], times[i + 1]
        when = (_bisect(lambda t: exact_alt(t) - h0, t0, t1) if refine
                else t0 + (t1 - t0) * float(rel[i] / (rel[i] - rel[i + 1])))
        if rising and vis.rise_utc is None:
            vis.rise_utc = when
        elif not rising and vis.set_utc is None:
            vis.set_utc = when

    # 2) culminação superior (máximo de altitude nas 24 h)
    k = int(np.argmax(alts))
    if refine and 0 < k < len(times) - 1:
        vis.transit_utc, vis.transit_alt = _golden_max(
            exact_alt, times[k] - step, times[k] + step)
    else:
        vis.transit_utc, vis.transit_alt = times[k], float(alts[k])

    # 3) janela útil dentro da noite escura
    vis.dark_start, vis.dark_end = _dark_interval(grid)
    limit = np.full_like(alts, float(min_alt))
    if horizon is not None and not horizon.is_flat:
        limit = np.maximum(limit, horizon.altitude_at(azs))
    usable = alts - limit

    def exact_usable(when):
        alt, az = _exact_altaz(engine, target, when)
        lim = float(min_alt)
        if horizon is not None and not horizon.is_flat:
            lim = max(lim, horizon.altitude_at(az))
        return alt - lim

    raw: list[tuple[dt.datetime, dt.datetime]] = []
    seg_start = times[0] if usable[0] >= 0 else None
    for i, rising in _crossings(usable):
        t0, t1 = times[i], times[i + 1]
        when = (_bisect(exact_usable, t0, t1, iters=10) if refine
                else t0 + (t1 - t0) * float(usable[i] / (usable[i] - usable[i + 1])))
        if rising:
            seg_start = when
        elif seg_start is not None:
            raw.append((seg_start, when))
            seg_start = None
    if seg_start is not None:
        raw.append((seg_start, times[-1]))

    if vis.dark_start is not None and vis.dark_end is not None:
        for a, b in raw:
            a2, b2 = max(a, vis.dark_start), min(b, vis.dark_end)
            if b2 > a2:
                vis.segments.append((a2, b2))

    # minutos perdidos para o horizonte do quintal (acima do limiar, atrás
    # de prédio/árvore, durante a noite escura)
    if horizon is not None and not horizon.is_flat:
        dark = grid.dark_mask
        hidden = dark & (alts >= min_alt) & (usable < 0)
        vis.blocked_minutes = float(hidden.sum() * grid.step_minutes)

    # 4) melhor hora: altitude máxima dentro da janela útil; sem janela,
    #    a maior altitude durante a noite escura (para a ficha explicar)
    if vis.segments:
        best = None
        for a, b in vis.segments:
            ia, ib = grid.index_of(a), grid.index_of(b)
            kk = ia + int(np.argmax(alts[ia:ib + 1]))
            cand_t, cand_alt = times[kk], float(alts[kk])
            if refine:
                lo, hi = max(a, times[kk] - step), min(b, times[kk] + step)
                if hi > lo:
                    cand_t, cand_alt = _golden_max(exact_alt, lo, hi, iters=14)
                for edge in (a, b):
                    e_alt = exact_alt(edge)
                    if e_alt > cand_alt:
                        cand_t, cand_alt = edge, e_alt
            if best is None or cand_alt > best[1]:
                best = (cand_t, cand_alt)
        vis.best_utc, vis.best_alt = best
    else:
        dark = grid.dark_mask
        if dark.any():
            idx = np.nonzero(dark)[0]
            kk = int(idx[np.argmax(alts[idx])])
            vis.best_utc, vis.best_alt = times[kk], float(alts[kk])

    if vis.best_utc is not None:
        kb = grid.index_of(vis.best_utc)
        vis.best_az = float(azs[kb])
        sep = grid.moon_separation(alts[kb:kb + 1], azs[kb:kb + 1], [kb])
        vis.moon_sep_best = float(sep[0])
        vis.moon_alt_best = float(grid.moon_alt[kb])
    return vis


def visibility_of(engine, ref, ref_utc: dt.datetime, **kwargs) -> Visibility:
    """Atalho para um :class:`core.objects.ObjectRef`."""
    return compute_visibility(engine, Target.from_ref(ref), ref_utc, **kwargs)


def batch_usable(grid: NightGrid, icrs: np.ndarray, min_alt: float = DEFAULT_MIN_ALT,
                 horizon=None):
    """Para N alvos fixos de uma vez: (alt máx. na noite escura,
    minutos utilizáveis na noite escura, alt (N,T), az (N,T)).

    Resolução da grade (10 min) — é o que a pontuação em massa precisa.
    """
    alts, azs = grid.altaz(np.atleast_2d(icrs))
    limit = np.full_like(alts, float(min_alt))
    if horizon is not None and not horizon.is_flat:
        limit = np.maximum(limit, horizon.altitude_at(azs))
    dark = grid.dark_mask[np.newaxis, :]
    ok = (alts >= limit) & dark
    minutes = ok.sum(axis=1) * grid.step_minutes
    best = np.where(dark, alts, -90.0).max(axis=1)
    return best, minutes, alts, azs
