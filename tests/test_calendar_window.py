"""Janela do Calendário do céu e cartão "Hoje no céu" (v0.17 T7)."""

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


def test_calendar_month(engine, tmp_path, isolated_userdata):
    from carina.core.ics import parse_ics
    from carina.ui.calendar_window import CalendarWindow

    win = CalendarWindow(engine, dt.date(2026, 12, 14), "Rio de Janeiro")
    assert win.events and win.lbl.text() == "Dezembro de 2026"
    titles = [win.day_list.topLevelItem(i).text(1)
              for i in range(win.day_list.topLevelItemCount())]
    assert any("Geminídeas" in t for t in titles)
    # filtro: só meteoros
    for key, chk in win.chk_cat.items():
        chk.setChecked(key == "meteoros")
    assert {e.category for e in win.visible_events()} == {"meteoros"}
    path = win.export_ics(str(tmp_path / "dez.ics"))
    back = parse_ics(Path(path).read_text(encoding="utf-8"))
    assert len(back) == len(win.visible_events()) >= 3
    # lembrete pelo botão
    win.day_list.setCurrentItem(win.day_list.topLevelItem(0))
    win._toggle_reminder()
    from carina.core import events

    assert events.reminders() and win.btn_remind.isChecked()
    win._toggle_reminder()
    assert not events.reminders()
    win.shift(1)
    assert (win.year, win.month) == (2027, 1)
    win.close()


def test_today_dialog(engine):
    from carina.ui.calendar_window import TodayDialog, today_events

    evs = today_events(engine, dt.datetime(2026, 12, 14, 12, tzinfo=UTC))
    assert any("Geminídeas" in e.title for e in evs)
    dlg = TodayDialog(evs, [])
    dlg.close()
