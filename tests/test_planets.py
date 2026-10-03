"""Núcleo planetário, luas e anéis (v0.18 T1/T2)."""

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
UTC = dt.timezone.utc


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists() or not (EPHEM / "pck00008.tpc").exists():
        pytest.skip("efeméride ou constantes planetárias ausentes")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


def _one(aps, kind):
    found = [a for a in aps if a.kind == kind]
    assert found, kind
    return found[0]


def test_oppositions(engine):
    """Oposições publicadas: Marte 19/02/2027, Saturno 04/10/2026."""
    from carina.core.planets import apparitions

    mars = _one(apparitions(engine, "Marte", dt.datetime(2026, 6, 1, tzinfo=UTC), 1.5),
                "oposicao")
    assert abs((mars.when_utc - dt.datetime(2027, 2, 19, 12, tzinfo=UTC)).total_seconds()) < 86400
    assert 13 < mars.diameter < 15 and mars.magnitude < -1.0
    sat = _one(apparitions(engine, "Saturno", dt.datetime(2026, 6, 1, tzinfo=UTC), 0.8),
               "oposicao")
    assert sat.when_utc.date() == dt.date(2026, 10, 4)
    assert 50 < sat.altitude < 80           # culmina alto no Rio (Dec ≈ +2°)


def test_venus_elongations(engine):
    """Vênus: 47,2° leste em 10/01/2025 e 45,9° oeste em 01/06/2025."""
    from carina.core.planets import apparitions

    aps = apparitions(engine, "Vênus", dt.datetime(2024, 12, 1, tzinfo=UTC), 0.7)
    east = _one(aps, "elong_leste")
    west = _one(aps, "elong_oeste")
    assert east.when_utc.date() == dt.date(2025, 1, 10) and east.elongation == pytest.approx(47.2, abs=0.1)
    assert west.when_utc.date() == dt.date(2025, 6, 1) and west.elongation == pytest.approx(45.9, abs=0.1)
    inf = _one(aps, "conj_inferior")
    assert inf.when_utc.month == 3 and inf.diameter > 55
    assert 0.45 < east.illumination < 0.55       # dicotomia perto da maior elongação


def test_mercury_conjunction_kinds(engine):
    from carina.core.planets import apparitions

    aps = apparitions(engine, "Mercúrio", dt.datetime(2026, 10, 1, tzinfo=UTC), 0.5)
    for a in aps:
        if a.kind == "conj_inferior":
            assert a.diameter > 9 and a.illumination < 0.1
        if a.kind == "conj_superior":
            assert a.diameter < 6 and a.illumination > 0.9


def test_state_and_orientation(engine):
    from carina.core.planets import planet_state

    v = planet_state(engine, "Vênus", dt.datetime(2026, 10, 3, tzinfo=UTC))
    assert v.illumination < 0.2 and v.diameter > 40 and v.evening
    # Meeus, exemplo 43.a: 16/12/1992 0h UT — meridiano central do Sistema II 72,74°
    jup = planet_state(engine, "Júpiter", dt.datetime(1992, 12, 16, tzinfo=UTC))
    assert abs((jup.cm2 - 72.74 + 180) % 360 - 180) < 1.0
    # anéis de Saturno: face norte bem aberta em 2017, face sul em 2026
    s17 = planet_state(engine, "Saturno", dt.datetime(2017, 10, 15, tzinfo=UTC))
    s26 = planet_state(engine, "Saturno", dt.datetime(2026, 10, 3, tzinfo=UTC))
    assert 26 < s17.ring_tilt < 27.5 and -9 < s26.ring_tilt < -5
    m = planet_state(engine, "Marte", dt.datetime(2026, 10, 3, tzinfo=UTC))
    assert 0 <= m.cm < 360 and 0.85 < m.illumination < 0.95


def test_ring_plane_crossing(engine):
    """A Terra cruzou o plano dos anéis em 23/03/2025."""
    from carina.core.satellites import next_ring_crossing

    when = next_ring_crossing(engine, dt.datetime(2024, 10, 1, tzinfo=UTC), years=2)
    assert when is not None and abs((when.date() - dt.date(2025, 3, 23)).days) <= 2


# Posições astrométricas geocêntricas do JPL Horizons, 03/10/2026 00:00 UT
HORIZONS = {
    "Júpiter": (142.185849391, 15.518186730, {
        "Io": (142.178816216, 15.520768595), "Europa": (142.146288694, 15.532233840),
        "Ganimedes": (142.182915825, 15.519480399), "Calisto": (142.289509414, 15.481470323)}),
    "Saturno": (11.211334980, 1.870404126, {
        "Titã": (11.259057806, 1.864463975), "Reia": (11.211836697, 1.873456362)}),
}


@pytest.mark.parametrize("planet", ["Júpiter", "Saturno"])
def test_moons_vs_horizons(planet):
    """Deslocamento lua − planeta (″) contra o Horizons: erro < 0,1″."""
    from carina.config import ObserverLocation
    from carina.core import satellites
    from carina.core.engine import SkyEngine
    from carina.core.planets import planet_state, radii_km

    if not satellites.available(planet):
        pytest.skip("efemérides das luas ausentes")
    e = SkyEngine(EPHEM)
    # geocêntrico: observador no centro da Terra (elevação −6 378 km não é
    # possível em wgs84; o deslocamento por paralaxe é igual para lua e planeta)
    e.set_location(ObserverLocation("geo", 0.0, 0.0, 0.0, "UTC"))
    st = planet_state(e, planet, dt.datetime(2026, 10, 3, tzinfo=UTC))
    views = {v.name: v for v in satellites.system_view(e, st)}
    ra0, de0, moons = HORIZONS[planet]
    req = radii_km(planet)[0]
    arcsec_per_r = math.degrees(math.atan(req / (st.distance_au * 149597870.7))) * 3600
    for name, (ra, de) in moons.items():
        d_east = (ra - ra0) * math.cos(math.radians(de0)) * 3600
        d_north = (de - de0) * 3600
        v = views[name]
        assert v.x * arcsec_per_r == pytest.approx(d_east, abs=0.1), name
        assert v.y * arcsec_per_r == pytest.approx(d_north, abs=0.1), name


def test_moon_events_and_grs(engine):
    from carina.core import satellites

    if not satellites.available("Júpiter"):
        pytest.skip("efemérides das luas ausentes")
    start = dt.datetime(2026, 10, 3, tzinfo=UTC)
    ev = satellites.moon_events(engine, "Júpiter", start, start + dt.timedelta(days=2),
                                step_minutes=5)
    kinds = {e.kind for e in ev}
    assert ev and ({"transito", "ocultacao", "eclipse", "sombra"} & kinds)
    # Io completa uma volta em 1,77 dia: passa na frente e atrás do disco
    io = [e for e in ev if e.moon == "Io"]
    assert any(e.kind == "transito" for e in io) and any(e.kind == "ocultacao" for e in io)
    # GMV: tabela JUPOS (dez/2025 = 79°) e deriva de ~16°/ano depois
    lon = satellites.grs_longitude(dt.date(2025, 12, 1))
    assert lon == pytest.approx(79.0, abs=0.01)
    assert satellites.grs_longitude(dt.date(2026, 12, 1)) == pytest.approx(95.0, abs=0.2)
    assert satellites.grs_longitude(dt.date(2027, 1, 1), override=(100.0, dt.date(2027, 1, 1))) == 100.0
    tr = satellites.grs_transits(engine, start, start + dt.timedelta(days=1), lon)
    assert 2 <= len(tr) <= 3                    # a cada 9 h 55 min
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(tr, tr[1:])]
    assert all(9.8 < g < 10.0 for g in gaps)


def test_planet_render():
    from carina.render.moon_cpu import MoonView
    from carina.render.planet_cpu import render_planet

    frame = np.eye(3)
    u = np.array([1.0, 0.0, 0.0])                   # observador vendo de +x
    sun = -u                                        # Sol atrás do observador: cheio
    img = render_planet(MoonView(100, 100), frame, u, sun, None, 0.9)
    assert img[50, 50].mean() > 150 and img[2, 2].mean() < 20
    # achatamento: o disco é mais largo que alto
    lit = img.mean(axis=2) > 60
    rows, cols = np.nonzero(lit)
    assert (cols.max() - cols.min()) > (rows.max() - rows.min()) + 3


def test_apparition_right_after_start(engine):
    """Oposição de Saturno (04/10/2026 12h UTC) vista na véspera, às 22h."""
    from carina.core.planets import apparitions, best_epoch_text

    start = dt.datetime(2026, 10, 4, 1, tzinfo=UTC)
    aps = apparitions(engine, "Saturno", start, 1.0)
    assert aps[0].kind == "oposicao" and aps[0].when_utc.date() == dt.date(2026, 10, 4)
    assert "04/10/2026" in best_epoch_text(engine, "Saturno", start, aps)
