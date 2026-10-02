"""Minhas listas (v0.15 T7): janela, ★ pela ficha e roteiro da lista."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EPHEM = ROOT / "data" / "ephemeris"
DATA = ROOT / "data" / "processed"
REF = dt.datetime(2026, 10, 3, 1, 0, tzinfo=dt.timezone.utc)


class _Store:
    def __init__(self):
        self.d = {}

    def value(self, key, default, _type=None):
        return self.d.get(key, default)

    def set_value(self, key, value):
        self.d[key] = value


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists() or not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine
    from carina.core.userdata import UserData
    from carina.ui.object_card import CardContext

    engine = SkyEngine(EPHEM)
    engine.set_location(ObserverLocation())
    engine.time.set_fixed(REF)
    tmp = tmp_path_factory.mktemp("lists")
    shutil.copy2(DATA / "dso.sqlite", tmp / "dso.sqlite")
    dso = DsoCatalog(DATA / "dso.sqlite", tmp / "dso.sqlite")
    ud = UserData(tmp / "carina.sqlite")
    yield CardContext(engine=engine, stars=StarCatalog(DATA), dso=dso, userdata=ud)
    dso.cx.close()
    ud.close()


def test_window_shows_tonight_and_edits(ctx):
    from carina.ui.lists_window import ListsWindow

    ud = ctx.userdata
    lid = ud.ensure_list()
    ud.add_item(lid, "dso", "M 8", "M 8 — Lagoa")
    ud.add_item(lid, "dso", "M 51", "M 51")               # abaixo do horizonte no Rio
    ud.add_item(lid, "body", "Saturno", "Saturno")
    ud.add_observation("dso", "M 8", "M 8", REF)
    store = _Store()
    win = ListsWindow(ctx, store)
    assert win.table.rowCount() == 3
    grades = [win.table.item(r, 2).text() for r in range(3)]
    assert grades[1] == "Não visível" and grades[0][0].isdigit()
    assert win.table.item(0, 5).text() == "✓"
    plans = []
    gotos = []
    win.planRequested.connect(plans.append)
    win.gotoRequested.connect(gotos.append)
    win.table.selectRow(2)
    win._move(-1)
    assert [i["ident"] for i in ud.items(lid)] == ["M 8", "Saturno", "M 51"]
    win.table.selectRow(0)
    win._goto()
    assert gotos and gotos[0][0] == "dso"
    win.btn_plan.click()
    assert plans == ["Minha lista"]
    win._set_current()
    assert store.d["lists/current"] == "Minha lista"
    win.table.selectRow(2)
    win._remove()
    assert len(ud.items(lid)) == 2
    win.close()


def test_list_to_plan_respects_window_and_horizon(ctx):
    from carina.core.horizon import preset_wall
    from carina.core.observing import build_from_list

    ud = ctx.userdata
    lid = ud.ensure_list("Teste plano")
    for ident in ("M 8", "NGC 104", "M 51"):
        ud.add_item(lid, "dso", ident, ident)
    items = ud.items(lid)
    plan = build_from_list(ctx.engine, ctx.dso, ctx.stars, items, REF, {})
    assert {e.ident for e in plan.entries} == {"M 8", "NGC 104"}
    assert "M 51" in plan.skipped_names
    walled = build_from_list(ctx.engine, ctx.dso, ctx.stars, items, REF, {},
                             horizon=preset_wall(60.0))
    assert len(walled.entries) < len(plan.entries)
