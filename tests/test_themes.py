"""Temas e modo noturno (v0.16 T2)."""

from PySide6.QtGui import QPalette

from carina.render.themes import THEMES, normalize
from carina.ui.nightmode import MAX_GB, NightMode, night_palette, palette_max_gb


def test_night_palette_has_no_blue_or_green():
    assert palette_max_gb(night_palette()) <= MAX_GB


def test_night_mode_restores_palette(qt_app):
    before = qt_app.palette().color(QPalette.Window).name()
    style = qt_app.styleSheet()
    mode = NightMode()
    mode.apply(True)
    assert palette_max_gb(qt_app.palette()) <= MAX_GB
    mode.apply(False)
    assert qt_app.palette().color(QPalette.Window).name() == before
    assert qt_app.styleSheet() == style


def test_theme_names():
    assert set(THEMES) == {"dark", "light", "red"}
    assert normalize("red") == "red" and normalize("roxo") == "dark"


def test_main_window_night_toggle(qt_app):
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    win.act_night.setChecked(True)
    assert win.sky.theme == "red" and not win.act_chart.isEnabled()
    assert palette_max_gb(qt_app.palette()) <= MAX_GB
    win.show()
    win._night.tint_window(win)
    from carina.ui.nightmode import RedOnlyEffect

    assert isinstance(win.card.graphicsEffect(), RedOnlyEffect)
    assert win.sky.graphicsEffect() is None          # céu GL usa o tema red
    win.act_night.setChecked(False)
    assert win.sky.theme == "dark" and win.act_chart.isEnabled()
    assert win.card.graphicsEffect() is None
    win.close()
