"""Janela dos planetas, dados embarcados e luas vetorizadas (v0.18 T3/T4)."""

import datetime as dt
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
EPHEM = ROOT / "data" / "ephemeris"
PLANETS = ROOT / "data" / "processed" / "planets"
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


def test_planet_data_files():
    names = ["mercury.jpg", "venus.jpg", "mars.jpg", "jupiter.jpg", "saturn.jpg",
             "saturn_ring.png", "uranus.jpg", "neptune.jpg", "grs.json",
             "moons_jupiter.npz", "moons_saturn.npz"]
    total = 0
    for n in names:
        assert (PLANETS / n).exists(), n
        total += (PLANETS / n).stat().st_size
    assert total < 20e6
    d = np.load(PLANETS / "moons_jupiter.npz")
    assert list(d["names"]) == ["Io", "Europa", "Ganimedes", "Calisto"]
    assert d["t_start"] < 2451545.0 + 1 and d["t_end"] > 2472000.0    # 2000–2060


def test_vectorized_matches_scalar(engine):
    """Estados vetorizados das luas = estados instante a instante."""
    from carina.core import satellites as S
    from carina.core.planets import planet_state

    start = dt.datetime(2026, 10, 3, tzinfo=UTC)
    times = [start + dt.timedelta(minutes=37 * k) for k in range(60)]
    vec = S.moon_states(engine, "Júpiter", times)
    mismatches = 0
    for k, t in enumerate(times):
        for v in S.system_view(engine, planet_state(engine, "Júpiter", t)):
            st = vec[v.name]
            assert st["x"][k] == pytest.approx(v.x, abs=1e-3)
            assert st["y"][k] == pytest.approx(v.y, abs=1e-3)
            mismatches += int(bool(st["transito"][k]) != (v.status == "transito"))
            mismatches += int(bool(st["ocultacao"][k]) != (v.status == "ocultada"))
            mismatches += int(bool(st["sombra"][k]) != (v.shadow is not None))
    assert mismatches <= 2          # bordas do disco: diferença de arredondamento


def test_planet_window(engine, isolated_userdata):
    from carina.ui.planet_window import PlanetWindow

    when = dt.datetime(2026, 10, 3, 7, tzinfo=UTC)
    w = PlanetWindow(engine, when, planet="Júpiter")
    assert w.name == "Júpiter" and w.list.count() == 7
    assert w.strip.mode == "moons" and len(w.moons) == 4
    assert "Mancha Vermelha" in w.info.toPlainText()
    w.tabs.setCurrentIndex(1)
    assert "oposição" in w.best.toPlainText().lower() or "Oposição" in w.best.toPlainText()
    assert w.season.alts is not None and len(w.season.dates) > 100
    w.tabs.setCurrentIndex(2)
    assert "Io" in w.events.toPlainText()
    w.select("Vênus")
    assert w.strip.mode == "series" and len(w.strip.series) == 10
    assert "Fase" in w.info.toPlainText()
    w.select("Saturno")
    assert "inclinação" in w.info.toPlainText()
    w.step(24)
    assert w.when == when + dt.timedelta(hours=24)
    w.close()
