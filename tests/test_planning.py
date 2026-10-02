"""Planejamento: seleção dos "Melhores Objetos" sem estrelas/novas nem
nomes repetidos (achado D3 da revisão de 2026-10)."""

import shutil
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


@pytest.fixture(scope="module")
def dso(tmp_path_factory):
    bundled = DATA / "dso.sqlite"
    if not bundled.exists():
        pytest.skip("banco embarcado ausente")
    from carina.catalogs.dso import DsoCatalog

    user = tmp_path_factory.mktemp("dso") / "dso.sqlite"
    shutil.copy2(bundled, user)
    cat = DsoCatalog(bundled, user)
    yield cat
    cat.cx.close()


def test_best_rows_exclude_stars_and_duplicates(dso):
    from carina.core.observing import _NOT_SHOWPIECES, _best_rows

    rows = _best_rows(dso)
    assert 30 <= len(rows) <= 60
    names = {r["name"] for r, _label in rows}
    assert not names & {"NGC 1990", "IC 1318", "NGC 7114", "IC 4816"}
    assert all(r["type"] not in _NOT_SHOWPIECES for r, _l in rows)
    labels = [label.lower() for _r, label in rows]
    assert len(labels) == len(set(labels)), "nome comum repetido no roteiro"
    assert "nebulosa da lagoa" in labels and "grande nebulosa de órion" in labels


# ---------------------------------------------------------------------------
# v0.15 T9 — planejamento v2: brilho superficial, filtros, horizonte, edição
# ---------------------------------------------------------------------------

import datetime as _dt  # noqa: E402

EPHEM = DATA.parent / "ephemeris"
NIGHT = _dt.datetime(2026, 10, 3, 1, 0, tzinfo=_dt.timezone.utc)


@pytest.fixture(scope="module")
def ctx(dso):
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e, dso, StarCatalog(DATA)


def _row(dso, name):
    return dict(dso.cx.execute(
        "SELECT name, klass, mag, maj, min FROM objects WHERE name = ?", (name,)
    ).fetchone())


def test_surface_brightness_moves_diffuse_galaxies(dso):
    from carina.core.observing import MAG_BINOCULAR, instrument_for, is_diffuse

    r = _row(dso, "M 101")                       # antes: "binóculo" (só magnitude)
    assert r["mag"] <= MAG_BINOCULAR
    assert instrument_for(r["mag"], r["maj"], r["klass"], r["min"]) in ("pequeno", "medio")
    for name in ("M 101", "NGC 300", "M 33"):
        r = _row(dso, name)
        assert is_diffuse(r["mag"], r["maj"], r["min"], r["klass"])
    r = _row(dso, "M 33")                        # grande e difusa: olho → binóculo
    assert instrument_for(r["mag"], r["maj"], r["klass"], r["min"]) == "binoculo"
    for name in ("M 31", "NGC 253"):             # continuam no binóculo ou melhor
        r = _row(dso, name)
        assert instrument_for(r["mag"], r["maj"], r["klass"], r["min"]) in ("olho", "binoculo")


def test_plan_entries_have_visibility_and_score(ctx):
    from carina.core.observing import build_marathon

    engine, dso, stars = ctx
    plan = build_marathon(engine, dso, stars, "BEST", NIGHT, {})
    assert plan.entries
    for e in plan.entries:
        assert e.ident and e.kind in ("dso", "body")
        assert e.window_start is not None and e.window_start <= e.window_end
        assert e.score > 0
        assert e.window_start - _dt.timedelta(minutes=20) <= e.when_utc


def test_instrument_and_class_filters(ctx):
    from carina.core.observing import INSTRUMENT_ORDER, PlanSettings, build_marathon

    engine, dso, stars = ctx
    full = build_marathon(engine, dso, stars, "M", NIGHT, {})
    bino = build_marathon(engine, dso, stars, "M", NIGHT, {},
                          settings=PlanSettings(instrument_max="binoculo"))
    assert 0 < len(bino.entries) < len(full.entries)
    assert all(INSTRUMENT_ORDER.index(e.instrument) <= 1 for e in bino.entries)
    gc = build_marathon(engine, dso, stars, "M", NIGHT, {},
                        settings=PlanSettings(classes=("GC",), max_objects=5))
    assert 0 < len(gc.entries) <= 5 and {e.klass for e in gc.entries} == {"GC"}


def test_horizon_excludes_object_behind_building(ctx):
    """Aceite da v0.15: alvo atrás do "prédio" não entra no plano."""
    from carina.core.horizon import HorizonProfile
    from carina.core.observing import build_from_list

    engine, dso, stars = ctx
    items = [{"kind": "dso", "ident": "M 8", "name": "M 8"},
             {"kind": "dso", "ident": "NGC 104", "name": "NGC 104"}]
    free = build_from_list(engine, dso, stars, items, NIGHT, {})
    assert {e.ident for e in free.entries} == {"M 8", "NGC 104"}
    # M 8 desce a oeste no início da noite; NGC 104 fica ao sul
    building = HorizonProfile([(200, 0), (220, 75), (320, 75), (340, 0)], "Prédio")
    blocked = build_from_list(engine, dso, stars, items, NIGHT, {}, horizon=building)
    assert [e.ident for e in blocked.entries] == ["NGC 104"]
    assert "M 8" in blocked.skipped_names


def test_list_with_star_body_and_missing(ctx):
    from carina.core.observing import build_from_list

    engine, dso, stars = ctx
    items = [{"kind": "star", "ident": "HIP 113368", "name": "Fomalhaut"},
             {"kind": "body", "ident": "Saturno", "name": "Saturno"},
             {"kind": "dso", "ident": "não existe", "name": "Fantasma"}]
    plan = build_from_list(engine, dso, stars, items, NIGHT, {})
    kinds = {e.kind for e in plan.entries}
    assert kinds == {"star", "body"}
    assert "Fantasma" in plan.skipped_names


def test_remove_and_move_reschedule(ctx):
    from carina.core.observing import PlanSettings, build_marathon

    engine, dso, stars = ctx
    plan = build_marathon(engine, dso, stars, "GC", NIGHT, {},
                          settings=PlanSettings(minutes_per_object=5, max_objects=8))
    assert len(plan.entries) >= 4
    removed = plan.remove(0)
    times = [e.when_utc for e in plan.entries]
    assert removed.ident not in [e.ident for e in plan.entries]
    assert times == sorted(times)
    assert all((b - a) >= _dt.timedelta(minutes=5) for a, b in zip(times, times[1:]))
    last = plan.entries[-1].ident
    plan.move(len(plan.entries) - 1, 0)
    assert plan.entries[0].ident == last
    assert plan.entries[0].when_utc <= plan.entries[1].when_utc
    first_alt = plan.entries[0].altitude
    assert -90 <= first_alt <= 90
    with pytest.raises(ValueError):
        plan.reorder([0, 0])
