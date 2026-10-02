"""Calendário de noites escuras (v0.15 T12)."""

import datetime as dt
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


def test_new_moon_darker_than_full(engine):
    from carina.core.dark_nights import best_nights, month_nights

    nights = month_nights(engine, 2026, 12)
    assert len(nights) == 31 and nights[0].date == dt.date(2026, 12, 1)
    by_day = {n.date.day: n for n in nights}
    new, full = by_day[8], by_day[23]                 # lua nova 9/12 · cheia 24/12
    assert new.moonless_minutes > full.moonless_minutes + 240
    assert new.moon_illum < 0.05 and full.moon_illum > 0.9
    assert full.phase_name in ("Cheia", "Gibosa crescente")
    for n in nights:
        assert 0 <= n.moonless_minutes <= n.astro_minutes <= 12 * 60
    best = best_nights(nights)
    assert all(abs((b.date - dt.date(2026, 12, 8)).days) <= 4 for b in best)


def test_dialog_navigation_and_click(engine):
    from carina.ui.dark_calendar import DarkCalendarDialog

    dlg = DarkCalendarDialog(engine, dt.date(2026, 12, 15))
    assert "Dezembro de 2026" in dlg.title.text()
    dlg._shift(+1)
    assert "Janeiro de 2027" in dlg.title.text()
    got = []
    dlg.dateChosen.connect(got.append)
    dlg.grid.resize(700, 480)
    night, rect = next(iter(dlg.grid._cells()))
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    c = rect.center()
    ev = QMouseEvent(QEvent.MouseButtonPress, c, c, Qt.LeftButton, Qt.LeftButton,
                     Qt.NoModifier)
    dlg.grid.mousePressEvent(ev)
    assert got == [dt.date(2027, 1, 1)]
    dlg.close()
