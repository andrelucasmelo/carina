"""Rodapé da noite, modo observação e preferências (v0.16 T5)."""

import datetime as dt
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
NIGHT = dt.datetime(2026, 10, 3, 1, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def grid():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine
    from carina.core.visibility import night_grid

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return night_grid(e, NIGHT)


def test_time_position_round_trip(grid):
    from carina.ui.widgets.night_slider import NightSlider

    s = NightSlider()
    s.resize(900, 32)
    s.set_night(grid)
    assert s.t0 < grid.night.sunset < grid.night.sunrise < s.t1
    x = s.time_to_x(NIGHT)
    assert abs((s.x_to_time(x) - NIGHT).total_seconds()) <= 60
    assert s.x_to_time(-50) == s.t0
    assert abs((s.x_to_time(5000) - s.t1).total_seconds()) < 60     # arredonda ao minuto


def test_click_emits_time(grid):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from carina.ui.widgets.night_slider import NightSlider

    s = NightSlider()
    s.resize(900, 32)
    s.set_night(grid)
    got = []
    s.timeChosen.connect(got.append)
    x = s.time_to_x(NIGHT)
    ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(x, 10), QPointF(x, 10),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    s.mousePressEvent(ev)
    assert got and abs((got[0] - NIGHT).total_seconds()) <= 120


def test_countdown_and_next_index():
    from carina.ui.observing_mode import countdown, next_index

    now = dt.datetime(2026, 10, 3, 0, 0, tzinfo=dt.timezone.utc)
    assert countdown(now + dt.timedelta(minutes=12), now, 4) == "em 12 min"
    assert countdown(now - dt.timedelta(minutes=1), now, 4) == "agora (restam 3 min)"
    assert countdown(now - dt.timedelta(minutes=70), now, 4) == "há 1 h 10 min"

    class E:
        def __init__(self, m):
            self.when_utc = now + dt.timedelta(minutes=m)

    class P:
        minutes_per_object = 5
        entries = [E(-20), E(-3), E(10)]

    assert next_index(P, now) == 1          # a parada de -3 min ainda está no tempo
    assert next_index(None, now) == -1


def test_main_window_field_tools(qt_app):
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    assert win.night_slider is not None and win._slider_bar is not None
    win.act_observe.setChecked(True)
    assert win.sky.label_scale > 1.3 and not win.side_dock.isVisible()
    assert win._next_card is not None
    win.act_observe.setChecked(False)
    assert win.sky.label_scale < 1.3
    win.close()
