"""Planejador de foto lunar, Lunar 100 e Janela da Lua (v0.17 T5/T6)."""

import datetime as dt
from pathlib import Path

import numpy as np
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


def test_photo_nights(engine):
    from carina.core import moon

    nights = moon.photo_nights(engine, dt.datetime(2026, 12, 10, 15, tzinfo=UTC), 20)
    assert len(nights) == 20
    assert [n.date for n in nights] == [dt.date(2026, 12, 10) + dt.timedelta(days=i)
                                        for i in range(20)]
    full = next(n for n in nights if n.date == dt.date(2026, 12, 23))
    assert full.illumination > 0.97 and full.kind == "disco"
    assert full.rise_az is not None and 50 < full.rise_az < 75     # nasce a ENE
    quarter = next(n for n in nights if n.date == dt.date(2026, 12, 16))
    assert quarter.kind == "relevo" and quarter.features
    assert any(n.kind == "cinerea" for n in nights[:4])
    assert moon.azimuth_label(62) == "ENE" and moon.azimuth_label(359) == "N"


def test_lunar100_program(isolated_userdata):
    from carina.core.programs import lunar100

    prog = lunar100()
    assert len(prog.items) == 100 and prog.items[4].name == "Copernicus"
    assert prog.items[0].lat is None and prog.items[4].lat == pytest.approx(9.7)
    observed = {("lunar", "L100 5"), ("lunar", "L100 1"), ("dso", "M 42")}
    assert prog.progress(observed) == (2, 100)
    assert prog.next_item(observed).number == 2


def test_moon_view_roundtrip():
    from carina.render.moon_cpu import MoonView

    for mirror in (False, True):
        v = MoonView(800, 600, zoom=2.3, pan_a=0.1, pan_b=-0.2, rotation=37.0, mirror=mirror)
        a = np.array([0.3, -0.5, 0.0])
        b = np.array([0.1, 0.4, -0.7])
        x, y = v.to_screen(a, b)
        a2, b2 = v.to_local(x, y)
        assert np.allclose(a, a2) and np.allclose(b, b2)
    plain = MoonView(800, 800)
    x, y = plain.to_screen(0.5, 0.0)        # meio raio para leste
    assert x < 400 and y == pytest.approx(400)   # leste à esquerda


def test_cpu_render(engine):
    from carina.core import moon
    from carina.render import moontex
    from carina.render.moon_cpu import MoonView, render

    arrays = moontex.moon_arrays(4)
    assert arrays is not None
    g = moon.geometry(engine, dt.datetime(2026, 12, 16, 23, tzinfo=UTC))   # quarto crescente
    _e, _n, _w, v2b = moon.view_basis(g)
    img = render(MoonView(200, 200), v2b, g.sun_body, g.obs_body, *arrays,
                 illumination=g.illumination)
    assert img.shape == (200, 200, 3) and img.dtype == np.uint8
    lum = img.mean(axis=2)
    disc = lum[100 - 60:100 + 60, 100 - 60:100 + 60]
    # metade iluminada, metade escura (com luz cinérea fraca)
    assert (disc > 80).mean() > 0.25 and (disc < 30).mean() > 0.25
    assert lum[2, 2] < 20                      # fundo fora do disco


def test_dialogs_build(engine, isolated_userdata):
    from carina.ui.moon_planner import Lunar100Dialog, MoonPlannerDialog
    from carina.ui.moon_window import MoonWindow

    when = dt.datetime(2026, 12, 16, 23, tzinfo=UTC)
    win = MoonWindow(engine, when)
    assert win.term.topLevelItemCount() > 5
    from carina.core import moon

    win.select_feature(moon.find_feature("Copernicus"))
    assert "Copernicus" in win.detail.toPlainText()
    win.step(24)
    assert win.when == when + dt.timedelta(hours=24)
    win.close()

    dlg = MoonPlannerDialog(engine, when, None)
    assert dlg.table.rowCount() == 30
    dlg.close()
    l100 = Lunar100Dialog({("lunar", "L100 5")})
    assert l100.bar.value() == 1
    l100.close()
