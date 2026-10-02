"""Visibilidade (v0.15 T1): nascer/culminação/ocaso contra o almanaque do
Skyfield, janela útil, horizonte do quintal e corpos do Sistema Solar."""

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"

SIRIUS = (math.radians(101.287155), math.radians(-16.716116))
M42 = (math.radians(83.8221), math.radians(-5.3911))
DATES = [dt.datetime(2026, 1, 15, 3, tzinfo=dt.timezone.utc),
         dt.datetime(2026, 4, 10, 3, tzinfo=dt.timezone.utc),
         dt.datetime(2026, 12, 20, 3, tzinfo=dt.timezone.utc)]
SITES = [("Rio de Janeiro", -22.9068, -43.1729, "America/Sao_Paulo"),
         ("Lisboa", 38.7223, -9.1393, "Europe/Lisbon")]


def _engine(lat, lon, tz):
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride não disponível")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation("t", lat, lon, 0.0, tz))
    return e


@pytest.fixture(scope="module", params=SITES, ids=[s[0] for s in SITES])
def engine(request):
    _name, lat, lon, tz = request.param
    yield _engine(lat, lon, tz)
    from carina.core.localtime import set_timezone

    set_timezone("America/Sao_Paulo")


def _almanac_events(engine, ra, dec, start, end):
    from skyfield import almanac
    from skyfield.api import Star

    star = Star(ra_hours=math.degrees(ra) / 15.0, dec_degrees=math.degrees(dec))
    t0, t1 = engine.ts.from_datetime(start), engine.ts.from_datetime(end)
    rises, _ = almanac.find_risings(engine.site, star, t0, t1)
    sets, _ = almanac.find_settings(engine.site, star, t0, t1)
    transits = almanac.find_transits(engine.site, star, t0, t1)
    return ([t.utc_datetime() for t in rises], [t.utc_datetime() for t in sets],
            [t.utc_datetime() for t in transits])


def _close(when, candidates, tol_s=60.0):
    return any(abs((when - c).total_seconds()) < tol_s for c in candidates)


@pytest.mark.parametrize("radec", [SIRIUS, M42], ids=["Sirius", "M42"])
@pytest.mark.parametrize("ref", DATES, ids=lambda d: d.strftime("%m-%d"))
def test_events_match_almanac(engine, radec, ref):
    from carina.core.visibility import Target, compute_visibility

    vis = compute_visibility(engine, Target.from_radec(*radec), ref)
    start = vis.grid.times[0]
    end = vis.grid.times[-1]
    rises, sets, transits = _almanac_events(engine, *radec, start, end)
    assert vis.rise_utc is not None and _close(vis.rise_utc, rises), (vis.rise_utc, rises)
    assert vis.set_utc is not None and _close(vis.set_utc, sets), (vis.set_utc, sets)
    assert _close(vis.transit_utc, transits), (vis.transit_utc, transits)
    # altitude de culminação: 90 − |φ − δ|
    lat = engine.topos.latitude.degrees
    expected = 90.0 - abs(lat - math.degrees(radec[1]))
    assert abs(vis.transit_alt - expected) < 0.3


def test_m42_season(engine):
    """M 42 é alvo de dezembro, não de junho (noite escura)."""
    from carina.core.visibility import Target, compute_visibility

    dec = compute_visibility(engine, Target.from_radec(*M42),
                             dt.datetime(2026, 12, 20, 3, tzinfo=dt.timezone.utc))
    jun = compute_visibility(engine, Target.from_radec(*M42),
                             dt.datetime(2026, 6, 20, 3, tzinfo=dt.timezone.utc))
    assert dec.window_minutes > 120
    assert jun.window_minutes < dec.window_minutes / 4
    assert dec.best_alt > 30


def test_moon_matches_tracking(engine):
    """Corpo do Sistema Solar: nascer/ocaso da Lua contra o almanaque."""
    from skyfield import almanac

    from carina.core.visibility import Target, compute_visibility

    ref = dt.datetime(2026, 3, 5, 3, tzinfo=dt.timezone.utc)
    vis = compute_visibility(engine, Target(body="Lua"), ref)
    t0 = engine.ts.from_datetime(vis.grid.times[0])
    t1 = engine.ts.from_datetime(vis.grid.times[-1])
    moon = engine.eph["moon"]
    rises, _ = almanac.find_risings(engine.site, moon, t0, t1)
    sets, _ = almanac.find_settings(engine.site, moon, t0, t1)
    # o almanaque usa o limbo superior; o Carina, o centro com refração:
    # a diferença é de poucos minutos (semidiâmetro de ~0,26°)
    if vis.rise_utc:
        assert _close(vis.rise_utc, [t.utc_datetime() for t in rises], 4 * 60)
    if vis.set_utc:
        assert _close(vis.set_utc, [t.utc_datetime() for t in sets], 4 * 60)
    assert vis.rise_utc or vis.set_utc


def test_horizon_blocks_window(engine):
    from carina.core.horizon import HorizonProfile
    from carina.core.visibility import Target, compute_visibility

    ref = DATES[2]
    target = Target.from_radec(*SIRIUS)
    free = compute_visibility(engine, target, ref, min_alt=10)
    wall = HorizonProfile([(az, 88.0) for az in range(0, 360, 30)])
    blocked = compute_visibility(engine, target, ref, min_alt=10, horizon=wall)
    assert free.window_minutes > 60
    assert blocked.window_minutes == 0 and not blocked.observable
    assert blocked.blocked_minutes > 60
    # nascer/ocaso continuam geométricos
    assert blocked.rise_utc == free.rise_utc


def test_batch_matches_single(engine):
    from carina.core.visibility import Target, batch_usable, compute_visibility, night_grid

    ref = DATES[0]
    grid = night_grid(engine, ref)
    vecs = np.array([Target.from_radec(*SIRIUS).icrs, Target.from_radec(*M42).icrs])
    best, minutes, _a, _z = batch_usable(grid, vecs, 20.0)
    for i, radec in enumerate((SIRIUS, M42)):
        v = compute_visibility(engine, Target.from_radec(*radec), ref, grid=grid)
        assert abs(minutes[i] - v.window_minutes) <= 2 * grid.step_minutes
        assert abs(best[i] - v.best_alt) < 1.5


def test_airmass():
    from carina.core.visibility import airmass

    assert abs(airmass(90.0) - 1.0) < 0.001
    assert 1.99 < airmass(30.0) < 2.0
    assert airmass(-1.0) == float("inf")
