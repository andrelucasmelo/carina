"""Previsão de eclipses lunares e solares (itens 4 e 5 do escopo).

Lunares: ``skyfield.eclipselib.lunar_eclipses`` (geometria exata da sombra).
Solares: para cada lua nova (almanaque), minimiza-se a separação aparente
Sol–Lua vista do GEOCENTRO (existência/tipo global do eclipse) e do LOCAL do
observador (circunstâncias locais: obscuração máxima por sobreposição de
discos e altitude do Sol). Aproximações documentadas no ADR-018: o tipo
global usa a geometria no instante de mínima separação geocêntrica — para
listas e planejamento é equivalente às tabelas canônicas (datas/tipos
conferidos contra os eclipses de 2026-2028).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np
from skyfield import almanac, eclipselib

R_SUN_KM = 695_700.0
R_MOON_KM = 1_737.4
R_EARTH_KM = 6_378.137

LUNAR_TYPES = {0: "Penumbral", 1: "Parcial", 2: "Total"}


@dataclass
class EclipseEvent:
    kind: str            # 'lunar' | 'solar'
    when_utc: dt.datetime  # instante do máximo
    type_label: str      # Total / Parcial / Anular / Penumbral
    detail: str          # magnitude ou obscuração
    alt_deg: float       # altitude do astro no máximo (no local)
    visible: bool        # astro acima do horizonte no máximo


def moon_influence_radii(illumination: float) -> tuple[float, float]:
    """Raios (rad) da zona de influência da Lua para astrofotografia.

    Regra prática: zona crítica de 10°..50° conforme a iluminação (uma Lua
    cheia lava o céu a dezenas de graus; um fino crescente, pouco). A zona de
    cautela é 1,6× maior. Modelo fotométrico (Krisciunas & Schaefer 1991) é
    pendência futura.
    """
    r1 = math.radians(10.0 + 40.0 * max(0.0, min(1.0, illumination)))
    return r1, 1.6 * r1


def _disc_overlap_fraction(rs: float, rm: float, d: float) -> float:
    """Fração da área do disco solar (raio rs) coberta pelo lunar (rm)."""
    if d >= rs + rm:
        return 0.0
    if d <= abs(rm - rs):
        return 1.0 if rm >= rs else (rm / rs) ** 2
    a1 = rs * rs * math.acos((d * d + rs * rs - rm * rm) / (2 * d * rs))
    a2 = rm * rm * math.acos((d * d + rm * rm - rs * rs) / (2 * d * rm))
    a3 = 0.5 * math.sqrt(
        max(0.0, (-d + rs + rm) * (d + rs - rm) * (d - rs + rm) * (d + rs + rm))
    )
    return (a1 + a2 - a3) / (math.pi * rs * rs)


def lunar_eclipses(engine, start_utc: dt.datetime,
                   end_utc: dt.datetime) -> list[EclipseEvent]:
    t0 = engine.ts.from_datetime(start_utc)
    t1 = engine.ts.from_datetime(end_utc)
    times, kinds, details = eclipselib.lunar_eclipses(t0, t1, engine.eph)
    events: list[EclipseEvent] = []
    for i, (ti, yi) in enumerate(zip(times, kinds)):
        moon = next(b for b in engine.bodies(ti) if b.name == "Lua")
        alt = math.degrees(moon.alt)
        mag_u = float(details["umbral_magnitude"][i])
        mag_p = float(details["penumbral_magnitude"][i])
        detail = (
            f"mag. umbral {mag_u:.2f}" if yi > 0 else f"mag. penumbral {mag_p:.2f}"
        )
        events.append(
            EclipseEvent(
                kind="lunar",
                when_utc=ti.utc_datetime(),
                type_label=LUNAR_TYPES.get(int(yi), "?"),
                detail=detail,
                alt_deg=alt,
                visible=alt > -0.5,
            )
        )
    return events


def solar_eclipses(engine, start_utc: dt.datetime,
                   end_utc: dt.datetime) -> list[EclipseEvent]:
    ts = engine.ts
    eph = engine.eph
    t0 = ts.from_datetime(start_utc)
    t1 = ts.from_datetime(end_utc)
    phase_t, phase_y = almanac.find_discrete(t0, t1, almanac.moon_phases(eph))
    new_moons = phase_t[phase_y == 0]

    earth = eph["earth"]
    sun = eph["sun"]
    moon = eph["moon"]
    events: list[EclipseEvent] = []

    for tn in new_moons:
        # janela de ±7 h em torno da lua nova, passo ~3,5 min
        window = ts.tt_jd(np.linspace(tn.tt - 0.30, tn.tt + 0.30, 241))

        # --- geometria geocêntrica: o eclipse existe? de que tipo? ---
        e = earth.at(window)
        s_app = e.observe(sun).apparent()
        m_app = e.observe(moon).apparent()
        sep = s_app.separation_from(m_app).radians
        ds = s_app.distance().km
        dm = m_app.distance().km
        rs = np.arcsin(R_SUN_KM / ds)
        rm = np.arcsin(R_MOON_KM / dm)
        # paralaxe lunar: um eclipse existe em ALGUM ponto da Terra se a
        # separação geocêntrica for menor que rs + rm + π_lua
        pi_m = np.arcsin(R_EARTH_KM / dm)
        i_min = int(np.argmin(sep))
        if sep[i_min] >= rs[i_min] + rm[i_min] + pi_m[i_min]:
            continue  # sem eclipse nesta lunação

        # tipo global: distância do eixo da sombra ao centro da Terra (gama,
        # em raios terrestres); central se |gama| < 0,9972 (Meeus)
        gamma = sep[i_min] * dm[i_min] / R_EARTH_KM
        if gamma < 0.9972:
            depth = math.sqrt(max(0.0, 1.0 - gamma * gamma))
            dm_surface = dm[i_min] - R_EARTH_KM * depth
            rm_surface = math.asin(R_MOON_KM / dm_surface)
            g_type = "Total" if rm_surface >= rs[i_min] else "Anular"
        else:
            g_type = "Parcial"

        # --- circunstâncias locais do observador ---
        o = engine.site.at(window)
        s_loc = o.observe(sun).apparent()
        m_loc = o.observe(moon).apparent()
        sep_l = s_loc.separation_from(m_loc).radians
        rs_l = np.arcsin(R_SUN_KM / s_loc.distance().km)
        rm_l = np.arcsin(R_MOON_KM / m_loc.distance().km)
        alt_l = s_loc.altaz()[0].degrees
        cover = rs_l + rm_l - sep_l
        up = alt_l > -0.5
        cover_up = np.where(up, cover, -np.inf)
        j = int(np.argmax(cover_up))

        if cover_up[j] > 0:
            frac = _disc_overlap_fraction(
                float(rs_l[j]), float(rm_l[j]), float(sep_l[j])
            )
            if sep_l[j] < abs(rm_l[j] - rs_l[j]):
                l_type = "Total" if rm_l[j] >= rs_l[j] else "Anular"
            else:
                l_type = "Parcial"
            events.append(
                EclipseEvent(
                    kind="solar",
                    when_utc=window[j].utc_datetime(),
                    type_label=f"{l_type} (local)",
                    detail=f"obscuração local {frac:.0%} · global: {g_type}",
                    alt_deg=float(alt_l[j]),
                    visible=True,
                )
            )
        else:
            events.append(
                EclipseEvent(
                    kind="solar",
                    when_utc=window[i_min].utc_datetime(),
                    type_label=g_type,
                    detail="não visível deste local",
                    alt_deg=float(alt_l[i_min]),
                    visible=False,
                )
            )
    return events


def find_eclipses(engine, start_utc: dt.datetime, years: float) -> list[EclipseEvent]:
    """Lunares + solares no intervalo, ordenados por data."""
    end = start_utc + dt.timedelta(days=365.25 * years)
    events = lunar_eclipses(engine, start_utc, end)
    events += solar_eclipses(engine, start_utc, end)
    events.sort(key=lambda ev: ev.when_utc)
    return events
