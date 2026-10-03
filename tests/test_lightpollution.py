"""Bortle automático pelo mapa de luzes noturnas (v0.19 T6)."""

import pytest


def test_reference_sites():
    from carina.core import lightpollution as lp

    if not lp.available():
        pytest.skip("mapa de poluição luminosa ausente")
    rio = lp.sqm_at(-22.91, -43.18)
    sp = lp.sqm_at(-23.55, -46.63)
    atacama = lp.sqm_at(-22.9, -68.2)
    amazonia = lp.sqm_at(-5.0, -63.0)
    assert rio < 19.0 and sp < 19.0                  # centros urbanos claros
    assert atacama > 21.3 and amazonia > 21.8        # céus escuros
    assert lp.suggest(-22.91, -43.18).bortle >= 8
    assert lp.suggest(-5.0, -63.0).bortle == 1
    assert lp.suggest(-22.9, -68.2).bortle <= 3
    # longitude dá a volta sem erro
    assert lp.sqm_at(0.0, 179.99) is not None and lp.sqm_at(0.0, -180.0) is not None


def test_bortle_scale_monotonic():
    from carina.core.lightpollution import bortle_from_sqm

    values = [bortle_from_sqm(s) for s in (22.0, 21.7, 21.4, 21.0, 20.5, 19.8, 19.2, 18.6, 17.5)]
    assert values == sorted(values) and values[0] == 1 and values[-1] == 9
