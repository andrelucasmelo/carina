"""'Qual constelação é esta?': ponto → constelação pelas fronteiras IAU."""

from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


@pytest.fixture(scope="module")
def bounds():
    if not (DATA / "const_bounds.npz").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs import skygeometry

    b = skygeometry.load_constellation_bounds(DATA)
    if b.ids is None:
        pytest.skip("const_bounds.npz sem ids (regenerar com build_data)")
    return b


def test_bright_stars_land_in_their_constellation(bounds):
    """As 300 estrelas mais brilhantes do catálogo caem na constelação que
    o próprio catálogo (HYG) atribui a elas — tolerância para divergências
    de borda e siglas (Serpens vem como Se1/Se2)."""
    from carina.catalogs import skygeometry
    from carina.catalogs.stars import StarCatalog

    stars = StarCatalog(DATA)
    order = np.argsort(stars.mag)[:300]
    agree = total = 0
    for idx in order:
        expected = stars.con.get(int(idx), "")
        if not expected:
            continue
        got = skygeometry.constellation_at(bounds, stars.xyz[int(idx)])
        total += 1
        exp = expected.replace("Se1", "Ser").replace("Se2", "Ser")
        if got == exp:
            agree += 1
    assert total > 250
    assert agree / total > 0.97, f"{agree}/{total} concordam"


def test_poles_and_known_points(bounds):
    from carina.catalogs import skygeometry

    assert skygeometry.constellation_at(bounds, [0.0, 0.0, -1.0]) == "Oct"
    assert skygeometry.constellation_at(bounds, [0.0, 0.0, 1.0]) == "UMi"
    # M 42 (AR 5h35m, Dec −5°23′) está em Órion
    import math
    ra, dec = math.radians(83.82), math.radians(-5.39)
    v = [math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)]
    assert skygeometry.constellation_at(bounds, v) == "Ori"


def test_subset_keeps_only_one_constellation(bounds):
    sub = bounds.subset({"Ori"})
    assert len(sub.counts) >= 1
    assert set(sub.ids.tolist()) == {"Ori"}
    assert sub.verts.shape[0] == int(sub.counts.sum())
