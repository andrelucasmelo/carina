"""Player, galeria e integração dos tours na janela principal (v0.20 T5–T6)."""

import datetime as dt

import pytest

BRT = dt.timezone(dt.timedelta(hours=-3))


def _utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=BRT).astimezone(dt.timezone.utc)


@pytest.fixture()
def win(qt_app):
    from carina.ui.mainwindow import MainWindow

    w = MainWindow()
    w.skip_state_save = True
    w.resize(1300, 850)
    w.show()
    qt_app.processEvents()
    yield w
    w.close()


def test_player_runs_and_restores(win, qt_app):
    from carina.core.skystate import SkyState

    eng, sky = win.engine, win.sky
    eng.time.set_fixed(_utc("2026-03-01T10:00"))
    sky.set_selection = None
    win.info_dock.show()
    before = SkyState.capture(sky, eng)
    layers_before = dict(sky.layers)
    finished = []
    win.start_tour("constelacoes-famosas", _utc("2026-01-15T20:00"))
    player = win.tour_player()
    player.finished.connect(lambda k, c: finished.append((k, c)))
    assert player.isVisible() and not win.info_dock.isVisible()
    run = player.run
    assert run.current.step.kind == "intro"
    # camadas do primeiro passo valem dali em diante
    assert sky.layers["asterisms"] and sky.layers["const_lines"] and not sky.layers["dso"]
    player.next()
    cur = run.current
    assert eng.time.current_datetime() == cur.when and eng.time.speed == 0.0
    assert ("asterism", "cruzeiro") in sky.active_highlights()
    player.finish_animation()
    # câmera apontada para o alvo (dentro do campo)
    import math

    import numpy as np

    from carina.core.tours import horizontal_vec
    v = horizontal_vec(eng, cur.target, eng.ts.from_datetime(cur.when))
    fwd = sky.camera.forward_component(np.asarray([v / np.linalg.norm(v)]))[0]
    assert fwd > math.cos(math.radians(cur.fov))
    player.prev()
    assert run.index == 0
    player.stop(False)
    assert not player.isVisible() and win.info_dock.isVisible()
    assert before.same_as(SkyState.capture(sky, eng)) == []
    assert dict(sky.layers) == layers_before
    assert finished == [("constelacoes-famosas", False)]


def test_player_finish_marks_done_and_saves_list(win, qt_app):
    from carina.core.tours import done_keys

    win.start_tour("famosos-ceu-profundo", _utc("2026-01-15T20:00"))
    player = win.tour_player()
    while not player.run.at_end:
        player.next()
    player.next()                            # "Concluir"
    assert "famosos-ceu-profundo" in done_keys(win.userdata)
    assert player.end_box.isVisible() and player.btn_list.isVisible()
    player._save_list()
    lid = win.userdata.list_id("Tour: Os famosos do céu profundo")
    names = {it["ident"] for it in win.userdata.items(lid)}
    assert {"M 42", "M 45"} <= names
    assert player.suggested_key and player.suggested_key != "famosos-ceu-profundo"
    player.next()                            # "Fechar o tour"
    assert not player.active


def test_escape_and_keys(win, qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win.start_tour("ceu-primavera", _utc("2026-10-05T15:00"))
    player = win.tour_player()
    QTest.keyClick(win, Qt.Key_Right)
    assert player.run.index == 1
    QTest.keyClick(win, Qt.Key_Left)
    assert player.run.index == 0
    QTest.keyClick(win, Qt.Key_Escape)
    assert not player.active
    assert not any(sc.isEnabled() for sc in player._shortcuts)


def test_bortle_step_restored(win, qt_app):
    from carina.core.tours import Tour

    sky = win.sky
    sky.set_bortle(3)
    tour = Tour.from_dict({"key": "cidade", "title": "Cidade", "category": "intermediario",
                           "when": "agora", "steps": [
                               {"title": "A", "text": "Céu de cidade grande.", "kind": "intro",
                                "target": "altaz:180,40", "bortle": 9},
                               {"title": "B", "text": "Continua Bortle 9.", "kind": "pause",
                                "target": "altaz:90,40"}]})
    win.start_tour(tour)
    assert sky.bortle == 9
    win.tour_player().next()
    assert sky.bortle == 9                       # cumulativo
    win.tour_player().stop(False)
    assert sky.bortle == 3


def test_generated_tour_in_player_with_card(win, qt_app):
    win.start_tour("objetos-do-mes", _utc("2026-10-05T15:00"))
    player = win.tour_player()
    run = player.run
    k = next(i for i, p in enumerate(run.steps) if p.step.card)
    player.go(k)
    assert player.card_holder.count() == 1
    card = player.card_holder.itemAt(0).widget()
    from PySide6.QtWidgets import QPushButton

    btn = next(b for b in card.findChildren(QPushButton) if "Sessão" in b.text())
    btn.click()
    sess = win._session_window
    assert any(t.ident == run.steps[k].step.card["ident"] for t in sess.targets)
    assert not sess.isVisible()                  # preparada sem roubar a frente
    player.stop(False)


def test_gallery_entries_and_welcome(win, qt_app):
    from carina.ui.tours_gallery import ToursGallery

    keys = [e["key"] for e in win.tour_entries()]
    for k in ("como-se-orientar", "constelacoes-famosas", "famosos-ceu-profundo",
              "conhecendo-o-carina", "ceu-primavera", "ceu-do-mes", "objetos-do-mes"):
        assert k in keys
    assert keys.index("como-se-orientar") < keys.index("ceu-do-mes")
    win.settings.set_value("tours/welcome_seen", False)
    g = ToursGallery(win)
    assert g.welcome.isVisibleTo(g)
    assert win.settings.value("tours/welcome_seen", False, bool) is False   # só ao usar
    assert set(g.lists) == {"iniciante", "intermediario", "astrofoto"}
    assert g.select("ceu-primavera") and g.current_key() == "ceu-primavera"
    started = []
    g.startRequested.connect(lambda k, ref: started.append(k))
    g._start_current()
    assert started == ["ceu-primavera"]
    assert win.settings.value("tours/welcome_seen", False, bool) is True


def test_tours_with_object_and_suggestions(win, qt_app):
    row = win.dso_catalog.cx.execute("SELECT id FROM objects WHERE name = 'M 42'").fetchone()
    assert "famosos-ceu-profundo" in win.tours_with(("dso", int(row[0])))
    assert win.tours_with(None) == []
    assert win.suggest_next_tour("como-se-orientar") == "estrelas-brilhantes"
    assert win.suggested_tour_tonight() in [e["key"] for e in win.tour_entries()]


def test_today_dialog_tour_button(qt_app):
    from PySide6.QtWidgets import QPushButton

    from carina.ui.calendar_window import TodayDialog

    dlg = TodayDialog([], [], tour=("como-se-orientar", "Como se orientar no céu"))
    got = []
    dlg.startTour.connect(got.append)
    btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Fazer o tour")
    btn.click()
    assert got == ["como-se-orientar"]
