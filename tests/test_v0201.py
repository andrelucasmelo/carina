"""0.20.1: a sessão de astrofoto mais fácil de achar — botão na ficha e a
sub-exposição com as margens de perda no próprio setup (Campo de visão)."""

import pytest


class FakeSettings:
    def __init__(self):
        self.d = {}

    def value(self, key, default, type_=None):
        return self.d.get(key, default)

    def set_value(self, key, value):
        self.d[key] = value


@pytest.fixture()
def win(qt_app):
    from carina.ui.mainwindow import MainWindow

    w = MainWindow()
    w.skip_state_save = True
    yield w
    w.close()


def test_card_session_button(win):
    row = win.dso_catalog.cx.execute("SELECT id FROM objects WHERE name = 'M 42'").fetchone()
    sel = ("dso", int(row[0]))
    win.card.set_selection(sel)
    btn = win.card.buttons["session"]
    assert btn.isEnabled()
    btn.click()
    sess = win._session_window
    assert any(t.ident == "M 42" for t in sess.targets)
    win.card.set_selection(("body", "Júpiter"))
    assert not win.card.buttons["session"].isEnabled()
    sess.close()


def test_setup_sub_and_margins_in_fov_dialog(tmp_path, isolated_userdata, monkeypatch):
    import json

    from carina.catalogs.equipment import EquipmentStore, load_setup
    from carina.ui import session_window
    from carina.ui.fov_dialog import FovDialog

    st = EquipmentStore(tmp_path / "eq.json")
    settings = FakeSettings()
    d = FovDialog(st, settings=settings)
    d.restore_last()
    d.cb_scope.setCurrentIndex(d.cb_scope.findText("Refrator ED 80/600"))
    d.cb_camera.setCurrentIndex(d.cb_camera.findText("ZWO ASI2600MC (APS-C)"))
    assert d.sp_sub.value() == 0 and d.sp_sub.text() == "a sugerida pelo céu"
    d.sp_sub.setValue(180)
    d._store_setup("80ED subs")
    assert load_setup("80ED subs", isolated_userdata).sub_s == 180

    class FakeMargins:
        def __init__(self, table, parent=None):
            self._t = table

        def exec(self):
            return True

        def table(self):
            return [(60.0, 5.0), (None, 12.0)]

    monkeypatch.setattr(session_window, "MarginsDialog", FakeMargins)
    d._edit_margins()
    assert json.loads(settings.d["session/sub_margins"]) == [[60.0, 5.0], [None, 12.0]]
    d.close()


def test_session_uses_setup_sub(win, isolated_userdata):
    from carina.catalogs.equipment import Setup, save_setup

    save_setup(Setup("Sub fixa", "Refrator ED 80/600", camera="ZWO ASI2600MC (APS-C)",
                     sub_s=240), isolated_userdata)
    save_setup(Setup("Sub auto", "Refrator ED 80/600", camera="ZWO ASI2600MC (APS-C)"),
               isolated_userdata)
    win._open_session(None, focus=False)
    sess = win._session_window
    sess.refresh_setups("Sub fixa")
    assert sess.sp_sub.value() == 240
    sess.refresh_setups("Sub auto")
    assert sess.sp_sub.value() == sess._advice().sub_s
    sess.close()


def test_session_window_fits_screen(win):
    win._open_session(None, focus=False)
    sess = win._session_window
    area = sess.screen().availableGeometry()
    assert sess.width() <= area.width() and sess.height() <= area.height()
    sess.close()
