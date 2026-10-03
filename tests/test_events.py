"""Motor do Calendário do céu e exportação .ics (v0.17 T4)."""

import datetime as dt
from pathlib import Path

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


def test_december_2026(engine):
    from carina.core import events

    s, f = events.month_range(2026, 12)
    evs = events.compute_events(engine, s, f)
    assert evs == sorted(evs, key=lambda e: (e.start_utc, e.category, e.title))
    assert len({e.uid for e in evs}) == len(evs)
    titles = [e.title for e in evs]
    assert "Lua cheia" in titles and "Lua nova" in titles
    assert "Pico das Geminídeas" in titles
    assert any(t.startswith("Solstício de dezembro: início do verão") for t in titles)
    assert any(t.startswith("Superlua") for t in titles)
    gem = next(e for e in evs if e.title == "Pico das Geminídeas")
    assert gem.local_start().date() in (dt.date(2026, 12, 13), dt.date(2026, 12, 14))
    assert gem.importance >= 2 and gem.visible
    for e in evs:
        assert s <= e.start_utc <= f, e.title
        assert e.category in events.CATEGORIES


def test_filters_and_importance(engine):
    from carina.core import events

    s, f = events.month_range(2026, 12)
    only = events.compute_events(engine, s, f, ["meteoros"])
    assert only and {e.category for e in only} == {"meteoros"}
    top = events.compute_events(engine, s, f, min_importance=2)
    assert top and all(e.importance >= 2 for e in top)
    # Úrsidas: o radiante não sobe no Rio
    urs = next(e for e in only if "Úrsidas" in e.title)
    assert urs.visible is False and urs.importance == 1


def test_planet_and_eclipse_events(engine):
    from carina.core import events

    start = dt.datetime(2026, 1, 1, tzinfo=UTC)
    end = dt.datetime(2027, 1, 1, tzinfo=UTC)
    pl = events.planet_events(engine, start, end)
    assert any(e.title == "Saturno em oposição" for e in pl)
    opp = next(e for e in pl if e.title == "Saturno em oposição")
    assert opp.start_utc.month == 10
    ecl = events.eclipse_events(engine, start, end)
    # 2026: eclipse total do Sol em 12/08 e total da Lua em 03/03
    assert any("total do Sol" in e.title and e.start_utc.month == 8 for e in ecl)
    assert any("da Lua" in e.title and e.start_utc.month == 3 for e in ecl)


def test_ics_roundtrip(engine):
    from carina.core import events
    from carina.core.ics import parse_ics, parse_stamp, to_ics

    s, f = events.month_range(2026, 12)
    evs = events.compute_events(engine, s, f, ["lua", "meteoros"])
    text = to_ics([e.to_ics("Rio de Janeiro, Brasil", 30) for e in evs])
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    back = parse_ics(text)
    assert len(back) == len(evs)
    for orig, ev in zip(evs, back):
        assert ev["UID"] == orig.uid + "@carina"
        assert ev["SUMMARY"] == orig.title
        assert ev.get("DESCRIPTION", "") == orig.detail
        assert parse_stamp(ev["DTSTART"]) == orig.start_utc.replace(microsecond=0)


def test_ics_escaping():
    from carina.core.ics import IcsEvent, parse_ics, to_ics

    tricky = "Vírgula, ponto; barra \\ e\nquebra — " + "é" * 60
    when = dt.datetime(2026, 12, 14, 3, tzinfo=UTC)
    back = parse_ics(to_ics([IcsEvent("x1", when, tricky, tricky)]))
    assert back[0]["SUMMARY"] == tricky and back[0]["DESCRIPTION"] == tricky


def test_reminders(tmp_path):
    from carina.core import events
    from carina.core.userdata import UserData

    db = UserData(tmp_path / "c.sqlite")
    ev = events.SkyEvent(dt.datetime(2026, 12, 14, 3, 0, tzinfo=UTC), "meteoros",
                         "Pico das Geminídeas", "x")
    assert not events.is_reminded(ev, db)
    events.add_reminder(ev, db)
    assert events.is_reminded(ev, db)
    due = events.due_reminders(dt.datetime(2026, 12, 13, 12, tzinfo=UTC), data=db)
    assert [e.uid for e in due] == [ev.uid]
    assert events.due_reminders(dt.datetime(2026, 12, 1, tzinfo=UTC), data=db) == []
    assert events.purge_old_reminders(dt.datetime(2027, 1, 1, tzinfo=UTC), db) == 1
    assert events.reminders(db) == []
