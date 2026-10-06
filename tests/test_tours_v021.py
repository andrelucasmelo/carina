"""Tours, parte 2 (v0.21): datas nos passos, rota, valores do local, geradores
novos, campo de binóculo, apresentação e voz."""

import datetime as dt
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
EPHEM = ROOT / "data" / "ephemeris"
BRT = dt.timezone(dt.timedelta(hours=-3))


def _utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=BRT).astimezone(dt.timezone.utc)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.catalogs import skygeometry
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core import localtime
    from carina.core.engine import SkyEngine
    from carina.core.tours import Resolver

    e = SkyEngine(EPHEM)
    loc = ObserverLocation()
    e.set_location(loc)
    localtime.set_timezone(loc.timezone)
    stars = StarCatalog(DATA)
    dso = DsoCatalog(DATA / "dso.sqlite", tmp_path_factory.mktemp("d") / "dso.sqlite")
    res = Resolver(stars, dso, skygeometry.load_constellation_info(DATA),
                   json.loads((DATA / "asterisms.json").read_text(encoding="utf-8")))
    return e, stars, dso, res


def test_step_time_other_nights(env):
    from carina.core.localtime import to_local
    from carina.core.tours import step_time

    base = _utc("2026-10-06T19:00")
    t = to_local(step_time(env[0], "data:07-15 hora:21:00", base, None))
    assert (t.year, t.month, t.day, t.hour) == (2026, 7, 15, 21)
    t = to_local(step_time(env[0], "data:01-15 hora:01:30", base, None))
    assert (t.month, t.day, t.hour, t.minute) == (1, 16, 1, 30)      # madrugada seguinte
    t = to_local(step_time(env[0], "em:2027-02-03T04:05", base, None))
    assert (t.year, t.month, t.day, t.hour, t.minute) == (2027, 2, 3, 4, 5)


def test_expand_context():
    from carina.core.tours import expand_context

    out = expand_context("Céu de {local}: SQM {sqm_local}, {desconhecido}.",
                         {"local": "Rio", "sqm_local": "18,9"})
    assert out == "Céu de Rio: SQM 18,9, {desconhecido}."


def test_finder_steps_have_route(env):
    from carina.core.tours import TourRun, builtin_dir, load_dir

    tours = {t.key: t for t in load_dir(builtin_dir())}
    run = TourRun(tours["foto-inverno"], env[0], env[3], _utc("2026-07-10T15:00"),
                  -22.9).prepare()
    finders = [p for p in run.steps if p.step.finder]
    assert len(finders) >= 5
    for p in finders:
        assert p.finder_text.startswith(("Comece por", "Sem estrela")), p.step.title
    assert all(p.step.setup_fov for p in finders)


def test_all_v021_tours_present():
    from carina.core.tours import builtin_dir, load_dir

    keys = {t.key for t in load_dir(builtin_dir())}
    for k in ("ceu-verao", "ceu-outono", "ceu-inverno", "cidade-grande", "historias-do-ceu",
              "historia-astronomia", "foto-verao", "foto-outono", "foto-inverno",
              "foto-primavera", "mosaicos", "lua-fotografar", "ceu-austral"):
        assert k in keys, k


def _ctx(env, when):
    from carina.core.tours_generated import GenContext

    e, stars, dso, _r = env
    return GenContext(e, stars, dso, when, latitude=-22.9, bortle=5)


@pytest.mark.parametrize("month", [1, 4, 7, 10])
def test_binocular_by_season(env, month):
    from carina.core.tours import TourRun, validate
    from carina.core.tours_generated import generate

    now = _utc(f"2026-{month:02d}-05T15:00")
    tour = generate("ceu-binoculo", _ctx(env, now))
    assert validate(tour) == [] and env[3].unresolved(tour) == []
    targets = [s for s in tour.steps if s.fov_circle]
    assert len(targets) >= 6, month
    assert all(s.fov_circle == 6 for s in targets)
    run = TourRun(tour, env[0], env[3], now, -22.9).prepare()
    assert not [s for s in run.skipped if "abaixo" in s.reason]


def test_extras_generators(env):
    from carina.core.tours import TourRun, validate
    from carina.core.tours_generated import generate

    now = _utc("2026-10-06T15:00")
    for key, minimum in (("ceu-de-uma-data", 3), ("lua-10-noites", 8), ("planetas-ano", 6),
                         ("ano-no-ceu", 5)):
        tour = generate(key, _ctx(env, now))
        assert validate(tour) == [], key
        assert env[3].unresolved(tour) == [], key
        run = TourRun(tour, env[0], env[3], now, -22.9).prepare()
        assert len(run.steps) >= minimum, (key, [s.reason for s in run.skipped])
    # um mês de Lua: as noites em ordem e a Lua acima do horizonte em cada uma
    run = TourRun(generate("lua-10-noites", _ctx(env, now)), env[0], env[3], now,
                  -22.9).prepare()
    moon = [p for p in run.steps if p.target is not None and p.target.kind == "body"]
    assert [p.when for p in moon] == sorted(p.when for p in moon)
    assert all(p.alt > 3 for p in moon)


def test_date_tour_uses_chosen_night(env):
    from carina.core.tours_generated import generate

    tour = generate("ceu-de-uma-data", _ctx(env, _utc("1990-05-20T15:00")))
    assert tour.title == "O céu de 20/05/1990"
    assert tour.when == "data:05-20 hora:21:00"


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


def test_city_tour_bortle_and_binocular_field(win):
    sky = win.sky
    sky.set_bortle(3)
    shapes_before = list(sky.fov_shapes)
    win.start_tour("cidade-grande", _utc("2026-01-15T20:00"))
    player = win.tour_player()
    assert sky.bortle == 9
    assert "{" not in player._last_text                       # {local} etc. expandidos
    k = next((i for i, p in enumerate(player.run.steps) if p.step.fov_circle), None)
    assert k is not None
    player.go(k)
    assert len(sky.fov_shapes) == 1 and sky.fov_shapes[0].kind == "circle"
    assert abs(math.degrees(sky.fov_shapes[0].width) - 6.0) < 1e-6
    player.stop(False)
    assert sky.bortle == 3 and list(sky.fov_shapes) == shapes_before


def test_presentation_mode_restores_window(win, qt_app):
    win.start_tour("ceu-primavera", _utc("2026-10-05T15:00"))
    player = win.tour_player()
    assert win.menuBar().isVisible()
    player.btn_present.setChecked(True)
    qt_app.processEvents()
    assert player.presenting and not win.menuBar().isVisible()
    assert player.overlay.isVisible() and player.overlay.title.text()
    assert player.btn_auto.isChecked()
    player.next()
    assert player.overlay.counter.text().startswith("2 /")
    player.btn_present.setChecked(False)
    qt_app.processEvents()
    assert not player.presenting and win.menuBar().isVisible() and player.isVisible()
    assert not player.btn_auto.isChecked()
    player.btn_present.setChecked(True)
    player.stop(False)                       # sair do tour sai da apresentação
    qt_app.processEvents()
    assert not player.presenting and win.menuBar().isVisible()


def test_speech_text_and_unavailable(monkeypatch):
    from carina.core import speech

    assert speech.plain_text("**Antares**, a 30° — `Ctrl+F` ▸ busca\n- item") == \
        "Antares, a 30 graus — Ctrl+F , busca item"
    monkeypatch.setattr(speech, "powershell", lambda: None)
    sp = speech.Speaker()
    assert not sp.available() and sp.say("Olá") is False and not sp.speaking()
