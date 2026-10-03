"""Núcleo lunar (v0.17 T2): libração, colongitude, formações e eventos."""

import datetime as dt
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
UTC = dt.timezone.utc


@pytest.fixture(scope="module")
def engine():
    from carina.core import moon

    if not (EPHEM / "de440s.bsp").exists() or not moon.kernels_available():
        pytest.skip("efeméride ou kernels lunares ausentes")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


def _tt(engine, jd_tt):
    return engine.ts.tt_jd(jd_tt).utc_datetime()


def test_libration_vs_meeus(engine):
    """Meeus, Astronomical Algorithms, exemplo 53.a: 1992-04-12 0h TD,
    libração geocêntrica l = −1,206°, b = +4,194°; Sol selenográfico
    l0 = 67,89°, b0 = 1,46° (colongitude 22,11°)."""
    from carina.core import moon

    g = moon.geometry(engine, _tt(engine, 2448724.5), topocentric=False)
    assert g.lib_lon == pytest.approx(-1.206, abs=0.1)
    assert g.lib_lat == pytest.approx(4.194, abs=0.1)
    assert g.sun_lon == pytest.approx(67.89, abs=0.1)
    assert g.sun_lat == pytest.approx(1.46, abs=0.1)
    assert g.colongitude == pytest.approx(22.11, abs=0.1)
    assert 0.0 <= g.pa_axis < 360.0


def test_perigee_supermoon_2016(engine):
    """Perigeu de 14/11/2016 às 11h23 UTC, 356 509 km (centro a centro)."""
    from carina.core import moon

    ev = moon.perigees_apogees(engine, dt.datetime(2016, 11, 10, tzinfo=UTC),
                               dt.datetime(2016, 11, 18, tzinfo=UTC))
    per = [e for e in ev if e.kind == "perigeu"]
    assert len(per) == 1
    target = dt.datetime(2016, 11, 14, 11, 23, tzinfo=UTC)
    assert abs((per[0].when_utc - target).total_seconds()) < 3600
    assert per[0].value == pytest.approx(356509, abs=15)


def test_lunar_x_near_first_quarter(engine):
    """O Lunar X acontece perto do quarto crescente (colongitude ≈ 358°)."""
    from skyfield import almanac

    from carina.core import moon

    start = dt.datetime(2026, 1, 1, tzinfo=UTC)
    end = dt.datetime(2026, 4, 1, tzinfo=UTC)
    xs = moon.colongitude_crossings(engine, moon.LUNAR_X_COLONG, start, end)
    assert len(xs) == 3
    t, y = almanac.find_discrete(engine.ts.from_datetime(start),
                                 engine.ts.from_datetime(end),
                                 almanac.moon_phases(engine.eph))
    quarters = [ti.utc_datetime() for ti, yi in zip(t, y) if int(yi) == 1]
    for x in xs:
        assert min(abs((x - q).total_seconds()) for q in quarters) < 1.5 * 86400
        g = moon.geometry(engine, x, topocentric=False)
        assert abs(((g.colongitude - 358.0) + 180) % 360 - 180) < 0.05


def test_geometry_phase_consistency(engine):
    from carina.core import moon

    full = moon.geometry(engine, dt.datetime(2026, 12, 24, 1, 28, tzinfo=UTC))
    assert full.illumination > 0.98 and full.phase_name == "Lua cheia"
    assert 85 < full.colongitude < 95
    new = moon.geometry(engine, dt.datetime(2026, 12, 9, 0, 52, tzinfo=UTC))
    assert new.illumination < 0.02
    assert 29.0 < full.angular_diameter_arcmin < 34.0


def test_terminator_features_and_good_dates(engine):
    from carina.core import moon

    # Copernicus (20°O): Sol nasce nele com colongitude ≈ 20°
    when = moon.colongitude_crossings(engine, 22.0,
                                      dt.datetime(2026, 10, 1, tzinfo=UTC),
                                      dt.datetime(2026, 11, 1, tzinfo=UTC))[0]
    g = moon.geometry(engine, when)
    names = [e.feature.name for e in moon.terminator_features(g)]
    assert "Copernicus" in names
    cop = next(e for e in moon.terminator_features(g) if e.feature.name == "Copernicus")
    assert cop.morning and 0 < cop.sun_alt < 6
    # Tycho (348,8°L = 11,2°O) longe do terminador na Lua cheia
    full = moon.geometry(engine, dt.datetime(2026, 12, 24, 1, 28, tzinfo=UTC))
    assert "Copernicus" not in [e.feature.name for e in moon.terminator_features(full)]

    wins = moon.good_dates(engine, 9.62, -20.08, dt.datetime(2026, 10, 1, tzinfo=UTC),
                           days=60)
    assert wins, "Copernicus deve ter noites boas em dois meses"
    for w in wins:
        assert moon.GOOD_SUN_MIN - 0.01 <= w.sun_alt_min <= w.sun_alt_max <= moon.GOOD_SUN_MAX + 0.01
        assert w.moon_alt_max >= 15


def test_features_data():
    from carina.core import moon

    feats = moon.features()
    assert 600 <= len(feats) <= 1500
    names = {f.name for f in feats}
    for n in ("Copernicus", "Tycho", "Plato", "Mare Imbrium", "Rupes Recta"):
        assert n in names
    cop = moon.find_feature("Copernicus")
    assert cop.l100 == 5 and cop.type == "crater" and 90 < cop.diam < 100
    assert moon.find_feature("Mar da Tranquilidade").name == "Mare Tranquillitatis"
    l100 = moon.lunar100_features()
    assert len(l100) == 100 and l100[16].name.startswith("Vallis")
    assert all(f.desc for f in l100)


def test_light_events_and_libration(engine):
    from carina.core import moon

    start = dt.datetime(2026, 10, 1, tzinfo=UTC)
    end = dt.datetime(2026, 12, 31, tzinfo=UTC)
    ev = moon.light_events(engine, start, end)
    kinds = {e.kind for e in ev}
    assert {"lunar_x", "alca_dourada", "rupes_recta", "luz_cinerea"} <= kinds
    assert ev == sorted(ev, key=lambda e: e.when_utc)
    lib = moon.libration_extremes(engine, start, end)
    assert lib and all(abs(e.value) >= 6.0 for e in lib)


def test_mosaic_and_advice():
    from carina.core import moon

    assert moon.mosaic_panels(0.52, 1.28, 0.72) == (1, 1)
    assert moon.mosaic_panels(0.52, 0.3, 0.2) == (2, 3)
    assert "relevo" in moon.photo_advice(0.5, True)
