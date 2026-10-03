"""Ocultações pela Lua (v0.17 T3)."""

import datetime as dt
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
UTC = dt.timezone.utc


def _engine(lat, lon, elev=10.0, tz="America/New_York"):
    from carina.core import moon

    if not (EPHEM / "de440s.bsp").exists() or not moon.kernels_available():
        pytest.skip("efeméride ou kernels lunares ausentes")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation("teste", lat, lon, elev, tz))
    return e


@pytest.mark.parametrize("city,lat,lon,imm,em", [
    # Ocultação de Antares em 03/03/2024 (Sky & Telescope / whenthecurveslineup):
    # horários locais EST (UTC−5) publicados ao minuto
    ("Miami", 25.7617, -80.1918, (6, 58), (8, 3)),
    ("Atlanta", 33.7490, -84.3880, (7, 4), (7, 56)),
])
def test_antares_2024_03_03(city, lat, lon, imm, em):
    from carina.core.occultations import find_occultations

    eng = _engine(lat, lon)
    occ = find_occultations(eng, dt.datetime(2024, 3, 3, 4, tzinfo=UTC),
                            dt.datetime(2024, 3, 3, 10, tzinfo=UTC), mag_limit=1.5,
                            planets=False)
    ant = [o for o in occ if o.target == "Antares"]
    assert len(ant) == 1, [o.target for o in occ]
    o = ant[0]
    t_imm = dt.datetime(2024, 3, 3, *imm, tzinfo=UTC)
    t_em = dt.datetime(2024, 3, 3, *em, tzinfo=UTC)
    assert abs((o.immersion_utc - t_imm).total_seconds()) < 120
    assert abs((o.emersion_utc - t_em).total_seconds()) < 120
    assert o.visible and o.moon_alt > 5
    # Lua minguante: imersão no limbo iluminado, emersão no escuro
    assert not o.dark_immersion and o.dark_emersion


def test_no_false_positives_and_order():
    from carina.core.occultations import find_occultations

    eng = _engine(-22.9068, -43.1729, 15.0, "America/Sao_Paulo")
    occ = find_occultations(eng, dt.datetime(2026, 10, 1, tzinfo=UTC),
                            dt.datetime(2026, 10, 15, tzinfo=UTC))
    assert occ == sorted(occ, key=lambda o: o.mid_utc)
    for o in occ:
        assert o.min_sep_arcmin < 17.0
        if o.immersion_utc and o.emersion_utc:
            assert 0 < o.duration_min < 110
        assert o.describe()
