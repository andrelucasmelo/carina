"""Resumo "Hoje à noite" (v0.15 T11).

Junta numa página o que se quer saber ao abrir o programa no fim da tarde:
crepúsculos, a Lua (fase, nascer e ocaso, quanto da noite escura fica sem
ela), os **melhores alvos de céu profundo** pela pontuação de
observabilidade — já com o horizonte do quintal e o Bortle — e os
planetas que valem a pena.

A seleção dos melhores parte da lista curada do planejamento (objetos
brilhantes ou grandes com designação conhecida), pontua todos de uma vez
na grade da noite (:func:`core.score.score_batch`) e refina os primeiros
com o cálculo exato.
"""

from __future__ import annotations

import datetime as dt

from dataclasses import dataclass, field

import numpy as np

from ..catalogs import names
from .twilight import NightInfo

PHASES = [(22.5, "Lua nova"), (67.5, "Crescente"), (112.5, "Quarto crescente"),
          (157.5, "Gibosa crescente"), (202.5, "Cheia"), (247.5, "Gibosa minguante"),
          (292.5, "Quarto minguante"), (337.5, "Minguante"), (360.1, "Lua nova")]
PLANETS = ["Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno"]


@dataclass
class TonightItem:
    kind: str
    ident: str
    name: str
    klass: str
    type_label: str
    score: int
    explain: str
    best_utc: dt.datetime | None
    best_alt: float
    window_start: dt.datetime | None
    window_end: dt.datetime | None
    magnitude: float | None = None


@dataclass
class TonightSummary:
    ref_utc: dt.datetime
    night: NightInfo
    moon_illum: float
    moon_phase: str
    moon_rise: dt.datetime | None
    moon_set: dt.datetime | None
    dark_minutes: float               # noite astronômica
    moonless_minutes: float           # noite astronômica sem Lua
    best: list[TonightItem] = field(default_factory=list)
    planets: list[TonightItem] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """Uma frase sobre a noite para o céu profundo."""
        hours = self.moonless_minutes / 60.0
        h = f"{hours:.1f}".replace(".", ",")
        if self.dark_minutes <= 0:
            return "Sem noite astronômica nesta data — só alvos brilhantes."
        if hours >= 5:
            return f"Noite excelente para céu profundo: {h} h de céu escuro sem Lua."
        if hours >= 2:
            return f"Boa noite: {h} h de céu escuro sem Lua."
        if hours > 0.25:
            return f"Lua presente quase toda a noite: só {h} h escuras sem ela."
        return ("Lua no céu a noite inteira: prefira aglomerados, estrelas duplas, "
                "planetas e a própria Lua.")


def moon_phase_name(engine, t) -> tuple[str, float]:
    """Nome da fase e ângulo de fase (0 = nova, 180 = cheia) em graus."""
    from skyfield import almanac

    deg = float(almanac.moon_phase(engine.eph, t).degrees) % 360.0
    for limit, name in PHASES:
        if deg < limit:
            return name, deg
    return "Lua nova", deg


def _item_from(vis, score, kind, ident, name, klass, type_label, mag) -> TonightItem:
    return TonightItem(kind, ident, name, klass, type_label, score.total,
                       score.explain(), vis.best_utc, vis.best_alt,
                       vis.window_start, vis.window_end, mag)


def tonight_summary(engine, dso, ref_utc: dt.datetime, bortle: int = 4,
                    horizon=None, min_alt: float = 20.0, instrument: str = "pequeno",
                    n_best: int = 5) -> TonightSummary:
    """Resumo da noite que contém ``ref_utc`` (determinístico por data/local)."""
    from ..catalogs.dso import type_label
    from .observing import _curated_rows
    from .score import score_batch, score_visibility
    from .visibility import Target, compute_visibility, night_grid

    grid = night_grid(engine, ref_utc)
    step = grid.step_minutes
    astro = grid.sun_alt < -18.0
    dark_min = float(astro.sum() * step)
    moonless = float((astro & (grid.moon_alt < 0.0)).sum() * step)
    mid = engine.ts.from_datetime(grid.start + dt.timedelta(hours=12))
    phase, _deg = moon_phase_name(engine, mid)
    moon = compute_visibility(engine, Target(body="Lua"), ref_utc, 0.0, grid=grid,
                              refine=False)
    summary = TonightSummary(ref_utc=ref_utc, night=grid.night,
                             moon_illum=grid.moon_illum, moon_phase=phase,
                             moon_rise=moon.rise_utc, moon_set=moon.set_utc,
                             dark_minutes=dark_min, moonless_minutes=moonless)

    # --- céu profundo: pontuação em massa e refinamento dos primeiros -----
    rows = [dict(r) for r in _curated_rows(dso, limit=400)]
    if rows:
        ra = np.array([r["ra"] for r in rows])
        dec = np.array([r["dec"] for r in rows])
        icrs = np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra),
                         np.sin(dec)], axis=1)
        scores = score_batch(grid, icrs, [r["mag"] for r in rows],
                             [r["maj"] for r in rows], [r["min"] for r in rows],
                             [r["klass"] for r in rows], bortle, instrument,
                             min_alt, horizon)
        order = np.argsort(-scores, kind="stable")[: n_best * 4]
        refined = []
        for i in order:
            if scores[i] <= 0:
                break
            r = rows[int(i)]
            t = Target(icrs=icrs[int(i)])
            vis = compute_visibility(engine, t, ref_utc, min_alt, horizon, grid=grid,
                                     refine=False)
            sc = score_visibility(vis, r["mag"], r["maj"], r["min"], r["klass"],
                                  bortle=bortle, instrument=instrument)
            if sc.total <= 0:
                continue
            common = names.common_label(r["common"]) if r["common"] else ""
            label = f"{r['name']} — {common}" if common else r["name"]
            famous = 1 if common else 0
            mag = r["mag"] if r["mag"] is not None else 99.0
            messier = 1 if r["name"].startswith("M ") else 0
            refined.append(((sc.total, messier, famous, -mag), _item_from(
                vis, sc, "dso", r["name"], label, r["klass"], type_label(r["type"]),
                r["mag"])))
        # nota primeiro; no empate (muitos chegam a 100), os famosos e os
        # Messier e os mais brilhantes — e no máximo dois do mesmo tipo, para variar
        refined.sort(key=lambda x: x[0], reverse=True)
        seen: set[str] = set()
        per_class: dict[str, int] = {}
        for _key, item in refined:
            name_key = item.name.split(" — ")[-1].lower()
            if name_key in seen or per_class.get(item.klass, 0) >= 2:
                continue
            seen.add(name_key)
            per_class[item.klass] = per_class.get(item.klass, 0) + 1
            summary.best.append(item)
            if len(summary.best) >= n_best:
                break

    # --- planetas -----------------------------------------------------------
    t_mid = engine.ts.from_datetime(grid.start + dt.timedelta(hours=12))
    mags = {b.name: b.magnitude for b in engine.bodies(t_mid)}
    for name in PLANETS:
        vis = compute_visibility(engine, Target(body=name), ref_utc, min_alt, horizon,
                                 grid=grid, refine=False)
        sc = score_visibility(vis, mags.get(name, 0.0), None, None, "PLANET",
                              bortle=bortle, instrument=instrument)
        if sc.total > 0:
            summary.planets.append(_item_from(vis, sc, "body", name, name, "PLANET",
                                              "Planeta", mags.get(name)))
    summary.planets.sort(key=lambda it: (-it.score, it.magnitude or 99.0))
    return summary


def format_minutes(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


