"""Sessão de astrofoto, exposição e imageabilidade (v0.19 T1–T3)."""

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
UTC = dt.timezone.utc


def _vec(ra_h, dec_d):
    ra, dec = math.radians(ra_h * 15), math.radians(dec_d)
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


TARGETS = [("M 42", 5.588, -5.39), ("NGC 2070", 5.643, -69.1), ("M 8", 18.06, -24.38),
           ("NGC 253", 0.793, -25.29), ("M 83", 13.617, -29.87)]


def _targets(names=None):
    from carina.core.session import SessionTarget

    return [SessionTarget(n, _vec(ra, dec), n) for n, ra, dec in TARGETS
            if names is None or n in names]


def test_gem_blocks_never_cross_meridian(engine):
    from carina.core.session import SessionOptions, plan_session

    plan = plan_session(engine, _targets(["M 42", "NGC 253", "NGC 2070"]),
                        dt.datetime(2026, 12, 15, 3, tzinfo=UTC), SessionOptions(min_alt=25))
    assert plan.blocks
    for b in plan.blocks:
        k0 = plan.times.index(b.start)
        k1 = k0 + int(b.minutes / 5)
        ha = plan.has[b.target, k0:k1]
        assert (ha < 0).all() or (ha > 0).all(), "bloco atravessa o meridiano"
        assert b.minutes >= 30 - 1e-6
    # M 42 culmina perto da meia-noite em dezembro: precisa de um flip
    assert any(b.flip_after for b in plan.blocks)
    # sem sobreposição e em ordem
    for a, b in zip(plan.blocks, plan.blocks[1:]):
        assert a.end <= b.start


def test_altaz_avoids_zenith(engine):
    from carina.core.session import SessionOptions, plan_session

    # M 42 passa a 72° no Rio; com limite de 65° a agenda precisa evitar o topo
    opt = SessionOptions(min_alt=25, altaz=True, zenith_limit=65.0)
    plan = plan_session(engine, _targets(["M 42", "NGC 2070"]),
                        dt.datetime(2026, 12, 15, 3, tzinfo=UTC), opt)
    assert plan.blocks
    for b in plan.blocks:
        assert b.alt_max <= 65.0 + 1e-6
    assert plan.alts[0].max() > 65                  # a zona existia de fato


def test_exposure_monotonic():
    from carina.catalogs.equipment import Camera, Telescope
    from carina.core.exposure import BORTLE_SQM, nights_for, suggest_sub

    scope = Telescope("80/480", 80, 480)
    cam = Camera("ZWO ASI533MC (1\")", 11.31, 11.31, 3.76, 3008, 3008)
    subs = [suggest_sub(BORTLE_SQM[b], scope, cam).sub_s for b in range(1, 10)]
    assert subs == sorted(subs, reverse=True) and subs[-1] < subs[0]
    assert suggest_sub(BORTLE_SQM[8], scope, cam).sub_s < suggest_sub(BORTLE_SQM[3], scope, cam).sub_s
    seestar = suggest_sub(BORTLE_SQM[3], Telescope("S50", 50, 250),
                          Camera("Seestar S50 — IMX462", 5.57, 3.13, 2.9), altaz=True)
    assert seestar.sub_s <= 30
    assert nights_for(10, [3, 0, 4, 4]) == 4 and nights_for(100, [1, 1]) is None


def test_imageability_m42(engine):
    from carina.core.imageability import compute

    img = compute(engine, _vec(5.588, -5.39), dt.datetime(2026, 1, 1, tzinfo=UTC),
                  days=366, step_days=7)
    by_month = {}
    for d, h in zip(img.dates, img.hours):
        by_month.setdefault(d.month, []).append(h)
    dec = np.mean(by_month[12])
    jun = np.mean(by_month[6])
    assert dec > jun + 1.0
    assert 12 in img.best_months(4) or 1 in img.best_months(4)


def test_mosaic_and_fit():
    from carina.catalogs.equipment import (Camera, Setup, Telescope, fit_in_field,
                                           mosaic_extent, mosaic_shapes, compute_camera_fov)

    shape = compute_camera_fov(Telescope("S50", 50, 250), Camera("IMX462", 5.57, 3.13, 2.9))
    tiles = mosaic_shapes(shape, 3, 2, 0.2)
    assert len(tiles) == 6
    w, h = mosaic_extent(shape, 3, 2, 0.2)
    xs = [t.offset[0] for t in tiles]
    assert max(xs) - min(xs) + shape.width == pytest.approx(w)
    # M 31 (178′ × 63′) não cabe no Seestar (1,28° × 0,72°): mosaico
    fit = fit_in_field(178, 63, shape)
    assert not fit["fits"] and fit["mosaic"][0] >= 2
    assert fit_in_field(8, 6, shape)["fits"]
    s = Setup("Quintal", "Seestar S50 (50/250)", "Seestar S50 — IMX462")
    assert Setup.from_dict(s.to_dict()) == s


def test_setup_persistence(tmp_path):
    from carina.catalogs.equipment import Setup, delete_setup, load_setup, save_setup, setup_names
    from carina.core.userdata import UserData

    db = UserData(tmp_path / "c.sqlite")
    save_setup(Setup("80ED + 533", "Refrator ED 80/600", "ZWO ASI533MC (1\")", mosaic_cols=2), db)
    assert setup_names(db) == ["80ED + 533"]
    assert load_setup("80ED + 533", db).mosaic_cols == 2
    delete_setup("80ED + 533", db)
    assert setup_names(db) == []
