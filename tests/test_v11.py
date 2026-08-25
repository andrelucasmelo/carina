"""Testes da v0.11: poluição sobre o céu profundo, previsão da Lua e
planejamento das maratonas."""

import datetime as dt
import math
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride não disponível")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


# --- poluição luminosa sobre o céu profundo -------------------------------

def test_sky_dimming_and_milkyway_cutoff():
    from carina.ui.skywidget import SkyWidget

    dim = SkyWidget.sky_dimming
    vis = SkyWidget.milkyway_visible

    class Fake:
        pass

    values = []
    for level in range(1, 10):
        obj = Fake()
        obj.bortle = level
        values.append(dim(obj))
        # a Via Láctea some a partir de Bortle 7 (pedido do usuário)
        assert vis(obj) == (level <= 6)
    assert values[0] == 1.0
    assert values[-1] == 0.0
    assert all(a >= b for a, b in zip(values, values[1:])), "deve ser monótona"


def test_zoom_out_limited_to_100_degrees():
    from carina.core.projection import FOV_MAX, Camera

    assert math.degrees(FOV_MAX) == pytest.approx(100.0)
    cam = Camera()
    for _ in range(40):
        cam.zoom(1.3)
    assert math.degrees(cam.fov) <= 100.0 + 1e-9


# --- previsão da Lua ------------------------------------------------------

def test_moon_forecast_phases(engine):
    from carina.core.planetpath import compute_moon_forecast

    start = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    marks = compute_moon_forecast(engine, start, days=28)
    assert len(marks) == 29
    assert all(0.0 <= m.illumination <= 1.0 for m in marks)

    named = {m.phase_name: m for m in marks if m.phase_name}
    assert "cheia" in named and "nova" in named
    # coerência entre nome da fase e iluminação
    assert named["cheia"].illumination > 0.97
    assert named["nova"].illumination < 0.05
    # lua cheia de agosto de 2026: 28/08
    assert named["cheia"].when_utc.date() in (
        dt.date(2026, 8, 27), dt.date(2026, 8, 28)
    )
    # o ciclo synodico tem ~29,5 dias: nova ~14 dias depois da cheia
    delta = (named["nova"].when_utc - named["cheia"].when_utc).days
    assert 13 <= delta <= 16


def test_moon_forecast_positions_move(engine):
    from carina.core.planetpath import compute_moon_forecast
    import numpy as np

    start = dt.datetime(2026, 8, 25, tzinfo=dt.timezone.utc)
    marks = compute_moon_forecast(engine, start, days=28)
    # a Lua anda ~13°/dia: passos consecutivos devem refletir isso
    seps = [
        math.degrees(math.acos(
            max(-1.0, min(1.0, float(np.dot(a.vec, b.vec))))
        ))
        for a, b in zip(marks, marks[1:])
    ]
    assert 11.0 < sum(seps) / len(seps) < 15.0


# --- maratonas ------------------------------------------------------------

@pytest.fixture(scope="module")
def marathon(engine):
    from carina.catalogs import skygeometry
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.core.observing import build_marathon

    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "dso.sqlite"
    dso = DsoCatalog(DATA / "dso.sqlite", tmp)
    stars = StarCatalog(DATA)
    const = {c["id"]: c for c in skygeometry.load_constellation_info(DATA)}
    start = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    return build_marathon(engine, dso, stars, "M", start, const)


def test_marathon_has_entries_and_night_window(marathon):
    assert marathon.title == "Maratona Messier"
    assert len(marathon.entries) > 50
    assert marathon.night_start is not None
    assert marathon.night_end > marathon.night_start


def test_marathon_entries_are_chronological_and_high(marathon):
    times = [e.when_utc for e in marathon.entries]
    assert times == sorted(times), "roteiro deve estar em ordem de horário"
    assert all(e.altitude >= 20.0 for e in marathon.entries)
    assert all(marathon.night_start <= e.when_utc <= marathon.night_end
               for e in marathon.entries)


def test_marathon_entries_are_scheduled_not_stacked(marathon):
    """O escalonamento deve espalhar os alvos pela noite, não empilhá-los."""
    distinct = {e.when_utc for e in marathon.entries}
    assert len(distinct) > 10


def test_marathon_instructions_present(marathon):
    for e in marathon.entries[:20]:
        assert e.what_to_see and len(e.what_to_see) > 30
        assert "binóculo" in e.binocular
        assert e.how_to_find and len(e.how_to_find) > 20
        assert e.constellation  # em português


def test_marathon_no_duplicate_objects(marathon):
    ids = [e.catalog_id for e in marathon.entries]
    assert len(ids) == len(set(ids))
