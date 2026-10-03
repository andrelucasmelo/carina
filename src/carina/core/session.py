"""Sessão de astrofotografia (v0.19 T1): a noite dividida entre os alvos.

Diferente do roteiro visual (minutos por objeto), aqui cada alvo recebe
**blocos de horas** de integração, e a agenda respeita o que a montagem
permite:

- **equatorial alemã (GEM)**: nenhum bloco atravessa o **meridiano** — a
  montagem precisa virar (*meridian flip*); o bloco termina antes e o
  seguinte começa depois de uma folga;
- **altazimutal** (Seestar, Dobson motorizado): a rotação de campo dispara
  perto do zênite, então a agenda evita a **zona cega do zênite**
  (acima de ~80°).

Cada intervalo de 5 min da noite escura vai para o alvo de maior
**qualidade** naquele instante (altura × Lua × prioridade), entre os que
estão utilizáveis; depois os intervalos viram blocos contínuos, blocos
curtos demais são absorvidos pelos vizinhos e os cortes de meridiano são
aplicados.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np

UTC = dt.timezone.utc
STEP_MIN = 5.0


@dataclass
class SessionTarget:
    name: str
    icrs: np.ndarray
    ident: str = ""
    kind: str = "dso"
    priority: float = 1.0          # 0,5–2: peso na disputa pelos intervalos
    size_arcmin: float = 0.0
    hours: float | None = None     # horas desejadas nesta noite (None = parte igual)


@dataclass
class SessionOptions:
    min_alt: float = 30.0
    dark_sun: float = -18.0        # −18 noite astronômica; −12 náutica
    altaz: bool = False
    zenith_limit: float = 80.0     # alt-az: acima disso a rotação de campo dispara
    meridian_margin_min: float = 10.0   # GEM: folga antes/depois do meridiano
    min_block_min: float = 30.0
    moon_weight: float = 1.0
    balance: bool = True           # dividir a noite (cotas) ou só o melhor alvo


@dataclass
class Block:
    target: int                    # índice em targets
    start: dt.datetime
    end: dt.datetime
    alt_min: float
    alt_max: float
    quality: float                 # 0..1 (média)
    flip_after: bool = False       # GEM: termina por causa do meridiano

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0


@dataclass
class SessionPlan:
    targets: list[SessionTarget]
    options: SessionOptions
    night_start: dt.datetime | None
    night_end: dt.datetime | None
    times: list = field(default_factory=list)
    alts: np.ndarray | None = None          # (alvos, N) graus
    has: np.ndarray | None = None           # ângulo horário (horas), (alvos, N)
    usable: np.ndarray | None = None        # (alvos, N) bool
    quality: np.ndarray | None = None       # (alvos, N) 0..1
    blocks: list[Block] = field(default_factory=list)
    meridian: list = field(default_factory=list)   # instante do trânsito de cada alvo (ou None)
    notes: list[str] = field(default_factory=list)

    def hours_for(self, i: int) -> float:
        return sum(b.minutes for b in self.blocks if b.target == i) / 60.0

    def usable_hours(self, i: int) -> float:
        return float(self.usable[i].sum()) * STEP_MIN / 60.0 if self.usable is not None else 0.0


def plan_session(engine, targets: list[SessionTarget], ref_utc: dt.datetime,
                 options: SessionOptions | None = None, horizon=None) -> SessionPlan:
    """Agenda da noite que contém ``ref_utc``."""
    from .twilight import night_info

    opt = options or SessionOptions()
    info = night_info(engine, ref_utc)
    if opt.dark_sun <= -18:
        a, b = info.astro_dusk, info.astro_dawn
    else:
        a, b = info.nautical_dusk, info.nautical_dawn
    plan = SessionPlan(targets, opt, a, b)
    if a is None or b is None or not targets:
        plan.notes.append("Sem noite escura nesta data e local." if a is None else "")
        return plan
    n = int((b - a).total_seconds() / 60 / STEP_MIN) + 1
    times = [a + dt.timedelta(minutes=STEP_MIN * k) for k in range(n)]
    plan.times = times
    t = engine.ts.from_datetimes(times)
    obs = engine.site.at(t)
    rows = []
    for alt_deg, az_deg in ((0.0, 0.0), (0.0, 90.0), (90.0, 0.0)):
        p = obs.from_altaz(alt_degrees=alt_deg, az_degrees=az_deg).position.au
        rows.append(np.asarray(p) / np.linalg.norm(p, axis=0))
    moon = obs.observe(engine.eph["moon"]).apparent()
    malt = np.asarray(moon.altaz()[0].degrees)
    mvec = np.asarray(moon.position.au, np.float64)
    mvec /= np.linalg.norm(mvec, axis=0)
    from skyfield import almanac

    illum = float(almanac.fraction_illuminated(engine.eph, "moon", t[n // 2]))
    lst = np.asarray(t.gast) + engine.topos.longitude.degrees / 15.0
    m = len(targets)
    alts = np.zeros((m, n))
    has = np.zeros((m, n))
    usable = np.zeros((m, n), bool)
    quality = np.zeros((m, n))
    for i, tg in enumerate(targets):
        v = np.stack([r.T @ tg.icrs for r in rows])
        alt = np.degrees(np.arcsin(np.clip(v[2], -1, 1)))
        az = np.degrees(np.arctan2(v[1], v[0])) % 360.0
        ra_h = math.degrees(math.atan2(tg.icrs[1], tg.icrs[0])) % 360.0 / 15.0
        ha = (lst - ra_h + 12.0) % 24.0 - 12.0                 # horas, − = a leste
        ok = alt >= opt.min_alt
        if opt.altaz:
            ok &= alt <= opt.zenith_limit
        else:
            # folga em torno do meridiano (tempo do flip): ±margem
            ok &= np.abs(ha) * 60.0 >= opt.meridian_margin_min
        if horizon is not None:
            ok &= alt > np.asarray(horizon.altitude_at(az))
        sep = np.degrees(np.arccos(np.clip(tg.icrs @ mvec, -1, 1)))
        # qualidade: massa de ar (altura) × Lua (separação, fase, Lua no céu)
        q_alt = np.clip(np.sin(np.radians(alt)), 0, 1) ** 1.5
        moon_pen = np.where(malt > 0, illum * np.clip(1 - sep / 90.0, 0, 1), 0.0)
        q = q_alt * (1 - 0.7 * opt.moon_weight * moon_pen) * tg.priority
        alts[i], has[i], usable[i], quality[i] = alt, ha, ok, np.where(ok, q, 0.0)
        # trânsito durante a noite (ha cruza 0 subindo)
        cross = np.nonzero((ha[:-1] < 0) & (ha[1:] >= 0) & (ha[1:] - ha[:-1] < 1))[0]
        plan.meridian.append(times[int(cross[0]) + 1] if len(cross) else None)
    plan.alts, plan.has, plan.usable, plan.quality = alts, has, usable, quality

    # 1) quem fica com cada intervalo
    if opt.balance:
        owner = _sweep(usable, quality, opt, [tg.hours for tg in targets])
    else:
        owner = np.where(usable.any(axis=0), np.argmax(quality, axis=0), -1)
    # 2) GEM: quebra no meridiano — um bloco não pode ter ângulo horário dos
    #    dois sinais; o sinal entra na chave do agrupamento
    side = np.sign(has[np.clip(owner, 0, None), np.arange(n)]) if m else np.zeros(n)
    key = owner * 2 + (side > 0) if not opt.altaz else owner * 2
    key = np.where(owner < 0, -1, key)
    min_steps = max(1, int(round(opt.min_block_min / STEP_MIN)))
    # 3) absorve blocos curtos: troca pelo dono vizinho que também pode usar
    for _ in range(3):
        runs = _runs(key)
        changed = False
        for k0, k1, val in runs:
            if val < 0 or (k1 - k0) >= min_steps:
                continue
            for nb in (_neighbor(runs, k0, -1), _neighbor(runs, k1, +1)):
                if nb is None or nb < 0:
                    continue
                tgt = nb // 2
                if usable[tgt, k0:k1].all():
                    # o lado do meridiano tem de bater (GEM)
                    if not opt.altaz and np.any(np.sign(has[tgt, k0:k1]) != (1 if nb % 2 else -1)):
                        continue
                    key[k0:k1] = nb
                    owner[k0:k1] = tgt
                    changed = True
                    break
        if not changed:
            break
    # o que sobrou curto demais não serve para integrar: vira tempo livre
    for k0, k1, val in _runs(key):
        if val >= 0 and (k1 - k0) < min_steps:
            key[k0:k1] = -1
    for k0, k1, val in _runs(key):
        if val < 0:
            continue
        i = val // 2
        # GEM: o bloco acabou porque o alvo chegou à folga do meridiano
        flip = (not opt.altaz and k1 < n and has[i, k1 - 1] < 0
                and abs(has[i, k1]) * 60.0 < opt.meridian_margin_min + STEP_MIN)
        plan.blocks.append(Block(int(i), times[k0], times[k1 - 1] + dt.timedelta(minutes=STEP_MIN),
                                 float(alts[i, k0:k1].min()), float(alts[i, k0:k1].max()),
                                 float(quality[i, k0:k1].mean()), bool(flip)))
    for i, tg in enumerate(targets):
        if not usable[i].any():
            plan.notes.append(f"{tg.name}: não fica acima de {opt.min_alt:.0f}° no céu escuro "
                              "nesta noite" + (" (ou só dentro da zona do zênite)"
                                               if opt.altaz else "") + ".")
    return plan


def _sweep(usable: np.ndarray, quality: np.ndarray, opt: SessionOptions,
           wanted: list) -> np.ndarray:
    """Varredura no tempo com cotas: fica no alvo atual até a cota acabar
    ou ele deixar de ser utilizável; o próximo é o de maior qualidade,
    preferindo quem tem pouco tempo utilizável pela frente (vai se pôr)."""
    m, n = usable.shape
    total = usable.any(axis=0).sum()
    has_time = usable.any(axis=1)
    k_usable = max(1, int(has_time.sum()))
    quota = np.array([(w * 60 / STEP_MIN) if w else total / k_usable for w in wanted])
    remaining = np.cumsum(usable[:, ::-1], axis=1)[:, ::-1]      # utilizável daqui em diante
    min_steps = max(1, int(round(opt.min_block_min / STEP_MIN)))
    owner = np.full(n, -1)
    got = np.zeros(m)
    cur, run = -1, 0
    for k in range(n):
        keep = cur >= 0 and usable[cur, k] and (got[cur] < quota[cur] or run < min_steps)
        if not keep:
            cand = [i for i in range(m) if usable[i, k]]
            if cand:
                under = [i for i in cand if got[i] < quota[i]] or cand
                cur = max(under, key=lambda i: quality[i, k] / np.sqrt(remaining[i, k] + 1.0))
                run = 0
            else:
                cur = -1
        if cur >= 0:
            owner[k] = cur
            got[cur] += 1
            run += 1
    return owner


def _runs(arr: np.ndarray) -> list[tuple[int, int, int]]:
    out = []
    k = 0
    n = len(arr)
    while k < n:
        j = k
        while j + 1 < n and arr[j + 1] == arr[k]:
            j += 1
        out.append((k, j + 1, int(arr[k])))
        k = j + 1
    return out


def _neighbor(runs, edge: int, direction: int):
    for k0, k1, val in runs:
        if direction < 0 and k1 == edge:
            return val
        if direction > 0 and k0 == edge:
            return val
    return None
