"""Tours gerados para a data e o local (v0.20 T7–T9)."""

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
EPHEM = ROOT / "data" / "ephemeris"

CITIES = {"Rio": (-22.9, -43.2, "America/Sao_Paulo"),
          "Porto Alegre": (-30.0, -51.2, "America/Sao_Paulo"),
          "Lisboa": (38.7, -9.1, "Europe/Lisbon")}


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.catalogs import skygeometry
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.core.engine import SkyEngine
    from carina.core.tours import Resolver

    e = SkyEngine(EPHEM)
    stars = StarCatalog(DATA)
    dso = DsoCatalog(DATA / "dso.sqlite", tmp_path_factory.mktemp("dso") / "dso.sqlite")
    res = Resolver(stars, dso, skygeometry.load_constellation_info(DATA),
                   json.loads((DATA / "asterisms.json").read_text(encoding="utf-8")))
    return e, stars, dso, res


def _ctx(env, city: str, when_local: dt.datetime):
    from carina.config import ObserverLocation
    from carina.core import localtime
    from carina.core.tours_generated import GenContext

    e, stars, dso, _res = env
    lat, lon, tz = CITIES[city]
    e.set_location(ObserverLocation(name=city, latitude=lat, longitude=lon, timezone=tz))
    localtime.set_timezone(tz)
    now = localtime.from_local_naive(when_local).astimezone(dt.timezone.utc)
    return GenContext(e, stars, dso, now, latitude=lat, bortle=5), now


def _run(env, tour, now, lat):
    from carina.core.tours import TourRun, validate

    assert validate(tour) == [], tour.key
    assert env[3].unresolved(tour) == [], tour.key
    return TourRun(tour, env[0], env[3], now, lat).prepare()


@pytest.mark.parametrize("key", ["como-se-orientar", "estrelas-brilhantes", "lua-e-planetas"])
def test_beginner_generators(env, key):
    from carina.core.tours_generated import generate

    for city in ("Rio", "Lisboa"):
        ctx, now = _ctx(env, city, dt.datetime(2026, 10, 5, 15, 0))
        tour = generate(key, ctx)
        run = _run(env, tour, now, ctx.latitude)
        assert tour.generated and len(run.steps) >= 3
        assert not [s for s in run.skipped if "abaixo" in s.reason], (city, run.skipped)
    if key == "estrelas-brilhantes":
        names = [s.title for s in tour.steps[1:-1]]
        assert 3 <= len(names) <= 7


def test_orientation_pole_matches_latitude(env):
    from carina.core.tours_generated import generate

    ctx, _now = _ctx(env, "Rio", dt.datetime(2026, 10, 5, 15, 0))
    tour = generate("como-se-orientar", ctx)
    pole = next(s for s in tour.steps if "polo sul" in s.title)
    assert pole.target == "altaz:180,23"
    assert "asterism:cruzeiro" in pole.highlight


@pytest.mark.parametrize("month", [1, 4, 7, 10])
@pytest.mark.parametrize("city", ["Rio", "Porto Alegre", "Lisboa"])
def test_month_sky(env, month, city):
    from carina.core.localtime import to_local
    from carina.core.tours_generated import generate

    ctx, now = _ctx(env, city, dt.datetime(2026, month, 5, 15, 0))
    tour = generate("ceu-do-mes", ctx)
    run = _run(env, tour, now, ctx.latitude)
    dsos = [p for p in run.steps if p.target is not None and p.target.kind == "dso"]
    consts = [p for p in run.steps if p.target is not None and p.target.kind == "const"]
    assert len(dsos) >= 4, (city, month, [p.step.title for p in run.steps])
    assert len(consts) >= 3
    assert not [s for s in run.skipped if "abaixo" in s.reason]
    # "no início da noite": objetos nas primeiras horas (até 4 h depois do crepúsculo)
    for p in dsos:
        assert (p.when - run.base) <= dt.timedelta(hours=4, minutes=10), p.step.title
        assert p.alt >= 25
    assert to_local(run.base).day == 15


@pytest.mark.parametrize("month", range(1, 13))
def test_month_photo_targets_rio(env, month):
    from carina.core.tours_generated import PHOTO_MIN_HOURS, generate

    ctx, now = _ctx(env, "Rio", dt.datetime(2026, month, 5, 15, 0))
    tour = generate("objetos-do-mes", ctx)
    run = _run(env, tour, now, ctx.latitude)
    sections, cur = {}, None
    for s in tour.steps:
        if s.kind == "intro" and s.title in ("Aglomerados estelares", "Nebulosas", "Galáxias"):
            cur = s.title
            sections[cur] = []
        elif s.card and cur:
            sections[cur].append(s)
    assert list(sections) == [t for t in ("Aglomerados estelares", "Nebulosas", "Galáxias")
                              if t in sections]          # ordem fixa das seções
    assert len(sections) >= 2, month
    for title, items in sections.items():
        assert items, (month, title)
        entries = []
        for s in items:
            c = s.card
            assert float(np.median(c["hours"])) >= PHOTO_MIN_HOURS - 1e-6
            alts = np.array(c["alts"])
            dark = np.array(c["dark"])
            ok = (alts > c["min_alt"]) & dark
            entries.append(int(np.argmax(ok)))
        # mais cedo primeiro (tolerância de uma amostra: as alturas do cartão
        # vêm arredondadas a 0,1°)
        assert all(a <= b + 1 for a, b in zip(entries, entries[1:])), (month, title)
    assert not [s for s in run.skipped if "abaixo" in s.reason]


def test_month_imaging_matches_imageability(env):
    """O cálculo vetorizado bate com o calendário de imageabilidade (v0.19)."""
    from carina.core.imageability import compute
    from carina.core.localtime import from_local_naive
    from carina.core.tours_generated import month_imaging

    ctx, _now = _ctx(env, "Rio", dt.datetime(2026, 10, 5, 15, 0))
    e = env[0]
    ra, dec = np.radians(13.25 * 15), np.radians(-29.9)            # M 83
    m42 = np.radians(5.588 * 15), np.radians(-5.39)
    icrs = np.array([[np.cos(d) * np.cos(r), np.cos(d) * np.sin(r), np.sin(d)]
                     for r, d in ((ra, dec), m42)])
    mi = month_imaging(e, icrs, 2026, 12, min_alt=30.0)
    start = from_local_naive(dt.datetime(2026, 12, 1, 15, 0)).astimezone(dt.timezone.utc)
    for k in range(2):
        img = compute(e, icrs[k], start, days=31, step_days=1, min_alt=30.0)
        a = np.array(mi.hours[k][:28])
        b = np.array(img.hours[:28])
        assert np.abs(a - b).mean() < 0.35, (k, a[:6], b[:6])
