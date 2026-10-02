"""Linha do tempo do roteiro e janela de planejamento v2 (v0.15 T10)."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EPHEM = ROOT / "data" / "ephemeris"
DATA = ROOT / "data" / "processed"
NIGHT = dt.datetime(2026, 10, 3, 1, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def plan_ctx(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists() or not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine
    from carina.core.observing import PlanSettings, build_marathon

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    tmp = tmp_path_factory.mktemp("tl")
    shutil.copy2(DATA / "dso.sqlite", tmp / "dso.sqlite")
    dso = DsoCatalog(DATA / "dso.sqlite", tmp / "dso.sqlite")
    stars = StarCatalog(DATA)

    def make(**kw):
        return build_marathon(e, dso, stars, "GC", NIGHT, {},
                              settings=PlanSettings(max_objects=8, **kw))
    yield e, dso, stars, make
    dso.cx.close()


def test_time_x_round_trip_and_drag(plan_ctx):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent

    from carina.core.visibility import night_grid
    from carina.ui.widgets.timeline import HEAD_H, ROW_H, NightTimeline

    engine, _d, _s, make = plan_ctx
    plan = make()
    tl = NightTimeline()
    tl.resize(1000, 400)
    tl.set_plan(plan, night_grid(engine, plan.night_start))
    when = plan.entries[2].when_utc
    x = tl.time_to_x(when)
    assert abs((tl.x_to_time(x) - when).total_seconds()) < 1
    assert tl.row_at(HEAD_H + 2.5 * ROW_H) == 2
    moved = []
    tl.slotMoved.connect(lambda i, w: moved.append((i, w)))
    y = HEAD_H + 2 * ROW_H + ROW_H / 2
    shift = tl.time_to_x(when + dt.timedelta(minutes=60)) - x
    for etype, px in ((QEvent.MouseButtonPress, x + 2), (QEvent.MouseMove, x + 2 + shift),
                      (QEvent.MouseButtonRelease, x + 2 + shift)):
        ev = QMouseEvent(etype, QPointF(px, y), QPointF(px, y), Qt.LeftButton,
                         Qt.LeftButton, Qt.NoModifier)
        {QEvent.MouseButtonPress: tl.mousePressEvent, QEvent.MouseMove: tl.mouseMoveEvent,
         QEvent.MouseButtonRelease: tl.mouseReleaseEvent}[etype](ev)
    assert moved and moved[0][0] == 2
    assert abs((moved[0][1] - (when + dt.timedelta(minutes=60))).total_seconds()) < 120


def test_set_slot_reorders_chronologically(plan_ctx):
    _e, _d, _s, make = plan_ctx
    plan = make()
    target = plan.entries[0]
    later = plan.entries[-1].when_utc + dt.timedelta(minutes=30)
    plan.set_slot(0, later)
    assert plan.entries[-1] is target
    assert abs((target.when_utc - later).total_seconds()) < 1
    times = [e.when_utc for e in plan.entries]
    assert times == sorted(times)


def test_plan_window_builds_and_reacts(plan_ctx):
    from carina.ui.plan_window import PlanWindow

    _e, _d, stars, make = plan_ctx
    calls = []

    def recompute(settings):
        calls.append(settings)
        return make(min_altitude=settings.min_altitude)

    win = PlanWindow(make(), stars, None, settings=None, recompute_cb=recompute,
                     observed=lambda: {("dso", "M 4")})
    n = win.table.rowCount()
    assert n == len(win.plan.entries) > 0
    assert win.timeline.plan is win.plan
    assert win.chart.pixmap() is not None and not win.chart.pixmap().isNull()
    got = []
    win.gotoAtTimeRequested.connect(lambda k, i, w: got.append((k, i, w)))
    win.buttons["time"].click()
    assert got and got[0][2] == win.plan.entries[0].when_utc
    first = win.plan.entries[0].ident
    win.table.selectRow(0)
    win.buttons["remove"].click()
    assert win.table.rowCount() == n - 1 and first not in [e.ident for e in win.plan.entries]
    win.f_alt.setValue(35)
    win._apply_filters()
    assert calls and calls[-1].min_altitude == 35.0
    assert all(e.altitude >= 30 for e in win.plan.entries)
    labels = [win.table.item(r, 2).text() for r in range(win.table.rowCount())]
    assert all(labels)
    win.close()


def test_best_plan_label_has_designation(plan_ctx):
    from carina.core.observing import build_marathon

    engine, dso, stars, _make = plan_ctx
    plan = build_marathon(engine, dso, stars, "BEST", NIGHT, {})
    lagoa = next(e for e in plan.entries if "Lagoa" in e.label)
    assert lagoa.label.startswith("M 8 — ")
