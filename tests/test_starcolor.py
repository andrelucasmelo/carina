"""Cor das estrelas por B−V (v0.16 T4)."""

import numpy as np

from carina.catalogs.stars import _bv_to_rgb, bv_to_temperature, temperature_to_rgb


def test_temperature_scale():
    t = bv_to_temperature(np.array([-0.3, 0.0, 0.65, 1.5]))
    assert t[0] > 15000 and 9000 < t[1] < 11000      # quente (a fórmula subestima as tipo B) / Vega
    assert 5500 < t[2] < 6100                         # o Sol
    assert 3500 < t[3] < 4200                         # gigante K/M
    assert all(np.diff(t) < 0)


def test_blackbody_extremes():
    hot, sun, cool = temperature_to_rgb(np.array([30000.0, 5800.0, 3000.0]))
    assert hot[2] >= hot[0]                          # quente: azulada
    assert cool[0] > cool[1] > cool[2]               # fria: laranja-avermelhada
    assert abs(sun[0] - 1.0) < 1e-6 and sun[2] > 0.8   # Sol: quase branco


def test_display_colors():
    rigel, vega, sun, arcturus, antares = _bv_to_rgb(np.array([-0.03, 0.0, 0.65, 1.23, 1.83]))
    for c in (rigel, vega, sun, arcturus, antares):
        assert abs(c.max() - 1.0) < 1e-6 and c.min() >= 0.0
    assert vega[2] >= vega[0]                        # Vega puxa para o azul
    assert sun[0] >= sun[2]
    redness = [c[0] - c[2] for c in (rigel, sun, arcturus, antares)]
    assert redness == sorted(redness)                # cada vez mais avermelhada
    assert antares[2] < 0.75                         # cor perceptível
    assert rigel.min() > 0.6                         # mas sutil (saturação reduzida)
