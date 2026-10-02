"""Pontuação de observabilidade (v0.15 T2)."""

import dataclasses
import datetime as dt
import math
from pathlib import Path

import numpy as np
import pytest

from carina.core import score as sc

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
M42 = (math.radians(83.8221), math.radians(-5.3911))


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride não disponível")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


def test_factors_monotonic():
    alts = [sc.altitude_factor(a) for a in range(0, 91, 5)]
    assert alts == sorted(alts) and alts[0] == 0 and alts[-1] == 1
    times = [sc.time_factor(m) for m in range(0, 300, 10)]
    assert times == sorted(times)
    pens = sc.moon_penalty(np.arange(0, 180, 5), np.full(36, 30.0), 0.9)
    assert all(np.diff(pens) <= 1e-12)              # mais longe, menos prejuízo
    by_illum = [float(sc.moon_penalty(20.0, 30.0, i)) for i in (0.0, 0.3, 0.6, 1.0)]
    assert by_illum == sorted(by_illum)
    assert float(sc.moon_penalty(5.0, -10.0, 1.0)) == 0.0   # Lua abaixo
    skies = [sc.sky_factor(9.0, 10.0, 6.0, "GAL", b) for b in range(1, 10)]
    assert all(a >= b for a, b in zip(skies, skies[1:]))
    # combine é monotônico em cada fator
    base = sc.combine(0.5, 0.5, 0.5, 0.5)
    for i in range(4):
        args = [0.5] * 4
        args[i] = 0.9
        assert sc.combine(*args) > base


def test_surface_brightness_separates_m31_m33():
    sb31 = sc.surface_brightness(3.4, 190.0, 60.0)
    sb33 = sc.surface_brightness(5.7, 70.8, 41.7)
    assert sb33 > sb31                    # M 33 é mais difusa
    f31 = sc.sky_factor(3.4, 190.0, 60.0, "GAL", 6)
    f33 = sc.sky_factor(5.7, 70.8, 41.7, "GAL", 6)
    assert f31 > f33
    assert sc.sky_factor(None, 60.0, 30.0, "DARK", 2) > sc.sky_factor(None, 60.0, 30.0, "DARK", 8)


def test_m42_december_beats_june(engine):
    from carina.core.visibility import Target, compute_visibility

    t = Target.from_radec(*M42)
    dec = compute_visibility(engine, t, dt.datetime(2026, 12, 10, 3, tzinfo=dt.timezone.utc))
    jun = compute_visibility(engine, t, dt.datetime(2026, 6, 20, 3, tzinfo=dt.timezone.utc))
    s_dec = sc.score_visibility(dec, 4.0, 85.0, 60.0, "NEB")
    s_jun = sc.score_visibility(jun, 4.0, 85.0, 60.0, "NEB")
    assert s_dec.total > s_jun.total
    assert s_dec.total >= 55
    assert "alto no céu" in s_dec.explain()
    assert s_jun.total == 0 or s_jun.total < 20


def test_full_moon_reduces(engine):
    from carina.core.visibility import Target, compute_visibility

    ref = dt.datetime(2026, 12, 24, 3, tzinfo=dt.timezone.utc)   # Lua cheia
    vis = compute_visibility(engine, Target.from_radec(*M42), ref)
    assert vis.grid.moon_illum > 0.9
    full = sc.score_visibility(vis, 4.0, 85.0, 60.0, "NEB")
    dark_grid = dataclasses.replace(vis.grid, moon_illum=0.0)
    dark = sc.score_visibility(dataclasses.replace(vis, grid=dark_grid),
                               4.0, 85.0, 60.0, "NEB")
    assert dark.total > full.total
    assert "Lua" in full.factor("moon").text


def test_not_visible_reason(engine):
    from carina.core.visibility import Target, compute_visibility

    polaris = Target.from_radec(math.radians(37.95), math.radians(89.26))
    vis = compute_visibility(engine, polaris, dt.datetime(2026, 12, 10, 3, tzinfo=dt.timezone.utc))
    s = sc.score_visibility(vis, 2.0, None, None, "STAR")
    assert s.total == 0 and "não nasce" in s.explain()


def test_batch_close_to_single(engine):
    from carina.core.visibility import Target, compute_visibility, night_grid

    ref = dt.datetime(2026, 12, 10, 3, tzinfo=dt.timezone.utc)
    grid = night_grid(engine, ref)
    t = Target.from_radec(*M42)
    single = sc.score_visibility(compute_visibility(engine, t, ref, grid=grid),
                                 4.0, 85.0, 60.0, "NEB").total
    batch = sc.score_batch(grid, t.icrs[np.newaxis], [4.0], [85.0], [60.0], ["NEB"])
    assert abs(batch[0] - single) <= 6
