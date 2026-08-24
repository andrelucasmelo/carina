"""Testes de crepúsculos e do rastreamento noturno."""

import datetime as dt
import math
from pathlib import Path

import pytest

from carina.core.twilight import format_night_summary, sun_altitude_band

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


def test_sun_altitude_bands():
    assert sun_altitude_band(10.0) == "day"
    assert sun_altitude_band(-3.0) == "day"      # antes do crepúsculo civil
    assert sun_altitude_band(-8.0) == "civil"
    assert sun_altitude_band(-15.0) == "nautical"
    assert sun_altitude_band(-30.0) == "astro"


def test_night_info_ordering(engine):
    from carina.core.twilight import night_info

    ref = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    info = night_info(engine, ref)
    seq = [
        info.sunset, info.civil_dusk, info.nautical_dusk, info.astro_dusk,
        info.astro_dawn, info.nautical_dawn, info.civil_dawn, info.sunrise,
    ]
    assert all(v is not None for v in seq)
    assert seq == sorted(seq), "eventos da noite fora de ordem cronológica"
    # noite astronômica do Rio no fim de agosto: algo entre 9 e 11 h de escuro
    dark = (info.astro_dawn - info.astro_dusk).total_seconds() / 3600
    assert 8.0 < dark < 11.5
    assert len(format_night_summary(info)) == 4


def test_track_m31_visible_and_bands(engine):
    from carina.core.tracking import compute_track

    ra, dec = math.radians(10.6847), math.radians(41.269)  # M31
    icrs = [
        math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra),
        math.sin(dec),
    ]
    ref = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    res = compute_track(engine, ("dso", 1), "M 31", icrs, ref)

    assert res.visible()
    # regra A: nenhum ponto abaixo do horizonte
    assert all(p.alt > 0 for p in res.points)
    # M31 do Rio (lat -23°, dec +41°) culmina baixa: ~25°
    assert 20 < math.degrees(res.max_alt) < 32
    assert {p.band for p in res.points} <= {"day", "civil", "nautical", "astro"}
    assert any(p.band == "astro" for p in res.points)


def test_track_moon_affects_nearby_object(engine):
    """Um alvo colado na Lua deve ser marcado como afetado."""
    from carina.core.tracking import compute_track

    ref = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    t = engine.ts.from_datetime(ref)
    moon = next(b for b in engine.bodies(t) if b.name == "Lua")
    m = engine.horizontal_matrix(t)
    icrs = m.T @ moon.vec  # posição da Lua em ICRS naquele instante

    res = compute_track(engine, ("dso", 1), "alvo junto à Lua", icrs, ref)
    assert res.visible()
    assert any(p.moon_affected for p in res.points)


def test_track_circumpolar_north_never_rises(engine):
    """Objeto no polo norte celeste nunca sobe no Rio de Janeiro."""
    from carina.core.tracking import compute_track

    ref = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    res = compute_track(engine, ("dso", 1), "polo norte", [0.0, 0.0, 1.0], ref)
    assert not res.visible()
