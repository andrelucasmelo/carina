"""Testes da previsão de eclipses contra eventos canônicos de 2026."""

import datetime as dt
import math
from pathlib import Path

import pytest

from carina.core.eclipses import _disc_overlap_fraction, moon_influence_radii

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride não disponível")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


def test_overlap_fraction_limits():
    assert _disc_overlap_fraction(1.0, 1.0, 2.5) == 0.0
    assert _disc_overlap_fraction(1.0, 1.0, 0.0) == 1.0
    assert _disc_overlap_fraction(1.0, 0.5, 0.0) == pytest.approx(0.25)
    partial = _disc_overlap_fraction(1.0, 1.0, 1.0)
    assert 0.0 < partial < 1.0


def test_moon_influence_radii_monotonic():
    r1_new, _ = moon_influence_radii(0.0)
    r1_full, r2_full = moon_influence_radii(1.0)
    assert math.degrees(r1_new) == pytest.approx(10.0)
    assert math.degrees(r1_full) == pytest.approx(50.0)
    assert r2_full > r1_full


def test_lunar_eclipses_2026(engine):
    from carina.core.eclipses import lunar_eclipses

    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    events = lunar_eclipses(engine, start, end)
    assert len(events) == 2
    total, partial = events
    assert total.when_utc.date() == dt.date(2026, 3, 3)
    assert total.type_label == "Total"
    assert partial.when_utc.date() == dt.date(2026, 8, 28)
    assert partial.type_label == "Parcial"
    assert partial.visible  # visível do Rio de Janeiro


def test_solar_eclipses_2026(engine):
    from carina.core.eclipses import solar_eclipses

    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    events = solar_eclipses(engine, start, end)
    assert len(events) == 2
    annular, total = events
    assert annular.when_utc.date() == dt.date(2026, 2, 17)
    assert annular.type_label == "Anular"
    assert total.when_utc.date() == dt.date(2026, 8, 12)
    assert total.type_label == "Total"
