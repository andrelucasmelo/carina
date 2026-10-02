"""Estrutura dos menus (revisão 2026-10, §4): oito menus, atalhos únicos,
Ajuda com documentação e atalhos. Constrói a janela principal sem exibir
(o OpenGL só é inicializado ao mostrar)."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CARINA_SKIP_GUI") == "1", reason="sem GUI"
)


@pytest.fixture(scope="module")
def window(qt_app):
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    yield win
    win.close()


def _menus(win):
    return [a.text().replace("&", "") for a in win.menuBar().actions() if a.menu()]


def test_eight_menus_grouped_by_task(window):
    assert _menus(window) == [
        "Arquivo", "Exibir", "Tempo", "Local", "Objetos", "Sistema Solar",
        "Planejar", "Ajuda",
    ]


def test_shortcuts_are_unique(window):
    from carina.ui.shortcuts_dialog import collect_menu_shortcuts

    rows = collect_menu_shortcuts(window.menuBar())
    keys = [k for _m, _a, k in rows for k in k.split(" ou ")]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"atalhos repetidos: {dupes}"
    assert len(rows) >= 40


def test_view_menu_has_submenus_and_help_has_docs(window):
    view = next(a.menu() for a in window.menuBar().actions()
                if a.text().replace("&", "") == "Exibir")
    subs = [a.text() for a in view.actions() if a.menu()]
    assert subs[:4] == ["Objetos", "Linhas e grades", "Rótulos", "Céu"]
    help_menu = next(a.menu() for a in window.menuBar().actions()
                     if a.text().replace("&", "") == "Ajuda")
    titles = [a.text() for a in help_menu.actions() if not a.isSeparator()]
    assert any("Documentação" in t for t in titles)
    assert any("Atalhos" in t for t in titles)


def test_layer_actions_cover_every_layer(window):
    from carina.ui.mainwindow import _LAYER_ACTIONS

    assert set(window._layer_acts) == {k for k, *_ in _LAYER_ACTIONS}


def test_render_options_capture_and_apply(window):
    """A fotografia do estado volta igual depois de aplicada (T13)."""
    sky = window.sky
    opts = sky.render_options()
    opts.bortle = 4
    opts.layers["grid_eq"] = True
    opts.const_label_mode = "latin"
    sky.apply_render_options(opts)
    again = sky.render_options()
    assert again.bortle == 4 and again.layers["grid_eq"] is True
    assert again.const_label_mode == "latin" and sky.layers["const_names"]
    assert again == sky.render_options()
