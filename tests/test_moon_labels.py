"""Projeção das formações lunares sobre o disco desenhado (v0.17 T5)."""

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
UTC = dt.timezone.utc


@pytest.fixture(scope="module")
def view():
    from carina.core import moon

    if not (EPHEM / "de440s.bsp").exists() or not moon.kernels_available():
        pytest.skip("efeméride ou kernels lunares ausentes")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    g = moon.geometry(e, dt.datetime(2026, 10, 25, 1, 0, tzinfo=UTC))   # perto da cheia
    u = g.moon_icrs
    pole = np.array([0.0, 0.0, 1.0])
    n_t = pole - (pole @ u) * u
    n_t /= np.linalg.norm(n_t)
    e_t = np.cross(pole, u)
    e_t /= np.linalg.norm(e_t)
    # tela: norte para cima (y negativo), leste para a esquerda (vista do céu)
    return {"cx": 500.0, "cy": 500.0, "r": 400.0, "e_t": e_t, "n_t": n_t, "w": -u,
            "e_scr": np.array([-1.0, 0.0]), "n_scr": np.array([0.0, -1.0]),
            "rot": g.rotation, "sun_body": g.sun_body}


def _positions(view, **kw):
    from carina.ui.skywidget import SkyWidget

    fake = SimpleNamespace(_moon_view=view)
    return {f.name: (x, y, r) for f, x, y, r in
            SkyWidget.moon_label_positions(fake, **kw)}


def test_orientation(view):
    pos = _positions(view, min_px=10.0, limit=400)
    crisium, plato, tycho = pos["Mare Crisium"], pos["Plato"], pos["Tycho"]
    # o "leste" selenográfico (Crisium) fica do lado OESTE do céu: à direita
    assert crisium[0] > view["cx"] + 200
    # Plato ao norte (em cima), Tycho ao sul (embaixo)
    assert plato[1] < view["cy"] - 250 and tycho[1] > view["cy"] + 200
    for x, y, _r in pos.values():
        assert (x - view["cx"]) ** 2 + (y - view["cy"]) ** 2 <= view["r"] ** 2 + 1


def test_size_filter(view):
    big = _positions(view, min_px=120.0, limit=400)
    small = _positions(view, min_px=10.0, limit=400)
    assert 0 < len(big) < len(small)
    assert "Mare Imbrium" in big and "Copernicus" not in big
    radius_px = small["Copernicus"][2]
    assert radius_px == pytest.approx(96.07 / 2 / 1737.4 * 400, rel=0.02)


def test_no_view_no_labels():
    from carina.ui.skywidget import SkyWidget

    assert SkyWidget.moon_label_positions(SimpleNamespace(_moon_view=None)) == []
