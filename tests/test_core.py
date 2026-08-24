"""Testes dos módulos puros: projeção, relógio da simulação e formatação."""

import datetime as dt
import math

import numpy as np
import pytest

from carina.core.formats import dec_dms, ra_hms, speed_label
from carina.core.projection import Camera, altaz_to_vec, vec_to_altaz


class FakeTimescale:
    def from_datetime(self, value):
        return value


@pytest.fixture
def clock():
    from carina.core.engine import TimeController

    return TimeController(FakeTimescale())


# ---------------------------------------------------------------------------
# Projeção
# ---------------------------------------------------------------------------

def test_center_projects_to_screen_center():
    cam = Camera(az=math.radians(120), alt=math.radians(35))
    cam.set_viewport(800, 600)
    x, y, vis = cam.project(altaz_to_vec(cam.az, cam.alt)[np.newaxis, :])
    assert vis[0]
    assert x[0] == pytest.approx(400.0, abs=1e-6)
    assert y[0] == pytest.approx(300.0, abs=1e-6)


def test_project_unproject_roundtrip():
    cam = Camera(az=math.radians(300), alt=math.radians(-10))
    cam.set_viewport(1024, 768)
    for az_deg, alt_deg in [(300, -10), (310, 5), (285, -30), (350, 20)]:
        vec = altaz_to_vec(math.radians(az_deg), math.radians(alt_deg))
        x, y, vis = cam.project(vec[np.newaxis, :], margin=5000)
        assert vis[0]
        az2, alt2 = cam.screen_to_altaz(float(x[0]), float(y[0]))
        assert math.degrees(az2) == pytest.approx(az_deg % 360, abs=1e-6)
        assert math.degrees(alt2) == pytest.approx(alt_deg, abs=1e-6)


def test_screen_up_is_sky_up():
    """Um ponto acima do centro da vista deve ter altitude maior."""
    cam = Camera(az=0.0, alt=math.radians(20))
    cam.set_viewport(800, 600)
    _, alt_above = cam.screen_to_altaz(400.0, 200.0)
    _, alt_below = cam.screen_to_altaz(400.0, 400.0)
    assert alt_above > math.radians(20) > alt_below


def test_altaz_vec_roundtrip():
    az, alt = math.radians(217.0), math.radians(-33.0)
    az2, alt2 = vec_to_altaz(altaz_to_vec(az, alt))
    assert az2 == pytest.approx(az)
    assert alt2 == pytest.approx(alt)


# ---------------------------------------------------------------------------
# Relógio da simulação
# ---------------------------------------------------------------------------

def test_speed_ladder(clock):
    assert clock.speed == 1.0
    clock.faster()
    assert clock.speed == 10.0
    clock.slower()
    assert clock.speed == 1.0
    clock.slower()
    assert clock.speed == -1.0
    clock.slower()
    assert clock.speed == -10.0
    clock.faster()
    assert clock.speed == -1.0
    clock.faster()
    assert clock.speed == 1.0


def test_pause_resume(clock):
    clock.set_speed(100.0)
    clock.toggle_pause()
    assert clock.speed == 0.0
    clock.toggle_pause()
    assert clock.speed == 100.0


def test_set_datetime_clamps_to_ephemeris_range(clock):
    clock.set_datetime(dt.datetime(1700, 1, 1, tzinfo=dt.timezone.utc))
    assert clock.current_datetime() >= clock.SIM_MIN
    clock.set_datetime(dt.datetime(3000, 1, 1, tzinfo=dt.timezone.utc))
    assert clock.current_datetime() <= clock.SIM_MAX


def test_fixed_time_is_paused(clock):
    when = dt.datetime(2026, 8, 24, 22, 0, tzinfo=dt.timezone.utc)
    clock.set_fixed(when)
    assert clock.speed == 0.0
    assert clock.current_datetime() == when


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def test_ra_hms_antares():
    # Antares: AR 16h 29m 24s
    ra = (16 + 29 / 60 + 24.5 / 3600) * math.pi / 12
    assert ra_hms(ra) == "16h 29m 24.5s"


def test_dec_dms_negative():
    dec = -math.radians(26 + 25 / 60 + 55.2 / 3600)
    assert dec_dms(dec) == "-26° 25′ 55.2″"


def test_speed_labels():
    assert speed_label(1.0) == ""
    assert speed_label(0.0).startswith("⏸")
    assert speed_label(100.0) == "×100"
    assert speed_label(-10.0) == "×-10"


# ---------------------------------------------------------------------------
# Fase da Lua (usa a efeméride local, se disponível)
# ---------------------------------------------------------------------------

def test_moon_phase_angle_matches_illumination():
    from pathlib import Path

    ephem = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
    if not (ephem / "de440s.bsp").exists():
        pytest.skip("efeméride não disponível")

    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    engine = SkyEngine(ephem)
    engine.set_location(ObserverLocation())
    t = engine.ts.utc(2026, 8, 25, 1, 0)
    moon = next(b for b in engine.bodies(t) if b.name == "Lua")
    # Fração iluminada f = (1 + cos i) / 2 deve bater com o almanaque
    f_from_phase = (1.0 + math.cos(moon.phase_angle)) / 2.0
    f_almanac = engine.moon_illumination(t)
    assert f_from_phase == pytest.approx(f_almanac, abs=0.01)
    assert 0.85 < f_almanac < 0.95  # gibosa crescente em 24/08/2026 à noite
