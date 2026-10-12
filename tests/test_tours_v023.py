"""v0.23: tours a partir do acervo do Astronomia no Quintal — alinhamentos
desenhados, formações lunares, quadro fixo de câmera, asterismos novos, tours
gerados da Lua e da Maratona Messier, quiz de asterismos e os tours novos."""

import datetime as dt
import json
import math
import random
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
EPHEM = ROOT / "data" / "ephemeris"
UTC = dt.timezone.utc
BRT = dt.timezone(dt.timedelta(hours=-3))

NEW_AUTHORED = {
    "asterismos-sul", "cruzeiro-polo", "orion-familia", "escorpiao-sagitario",
    "so-com-os-olhos", "duplas", "variaveis", "constelacoes-verao", "constelacoes-outono",
    "constelacoes-inverno", "constelacoes-primavera", "galaxias", "aglomerados-sul",
    "caldwell-sul", "maratona-lacaille", "smart-telescopes", "astrofoto-dificuldade",
}


def _utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=BRT).astimezone(UTC)


def _ang(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b)
                                                / np.linalg.norm(a) / np.linalg.norm(b)))))


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.catalogs import skygeometry
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.core.engine import SkyEngine
    from carina.core.tours import Resolver

    e = SkyEngine(EPHEM)
    stars = StarCatalog(DATA)
    dso = DsoCatalog(DATA / "dso.sqlite", tmp_path_factory.mktemp("dso") / "dso.sqlite")
    res = Resolver(stars, dso, skygeometry.load_constellation_info(DATA),
                   json.loads((DATA / "asterisms.json").read_text(encoding="utf-8")))
    return e, stars, dso, res


def _ctx(env, lat: float, when_local: dt.datetime):
    from carina.config import ObserverLocation
    from carina.core import localtime
    from carina.core.tours_generated import GenContext

    e, stars, dso, _res = env
    e.set_location(ObserverLocation(latitude=lat))
    localtime.set_timezone("America/Sao_Paulo")
    now = localtime.from_local_naive(when_local).astimezone(UTC)
    return GenContext(e, stars, dso, now, latitude=lat), now


@pytest.fixture()
def win(qt_app):
    from carina.ui.mainwindow import MainWindow

    w = MainWindow()
    w.skip_state_save = True
    w.resize(1200, 800)
    w.show()
    qt_app.processEvents()
    yield w
    w.close()


# --- dados ------------------------------------------------------------------------

def test_new_asterisms():
    data = {a["key"]: a for a in json.loads((DATA / "asterisms.json").read_text("utf-8"))}
    assert len(data) >= 27
    for key in ("espada-orion", "cruz-norte", "chave-hercules", "cabide", "circulo-peixes",
                "cabritinhas", "corvo", "y-virgem", "pequeno-carro"):
        assert data[key]["lines"] and data[key]["text"], key


def test_alignments_point_where_they_say():
    from carina.core.tours import load_alignments

    al = {a["key"]: a for a in load_alignments(DATA / "alignments.json")}
    assert len(al) >= 14
    for a in al.values():
        assert a["lines"] and a["text"], a["key"]
        for line in a["lines"]:
            assert len(line) >= 2
            assert all(abs(np.linalg.norm(p) - 1.0) < 1e-4 for p in line)
    pole = [0.0, 0.0, -1.0]
    lab = {x["text"]: x["xyz"] for x in al["cruzeiro-polo"]["labels"]}
    assert _ang(lab["Polo Sul Celeste"], pole) < 4.0           # braço × 4,5
    assert _ang(al["cruzeiro-polo"]["lines"][1][-1], pole) < 4.0   # mediatriz
    assert _ang(al["polo-canopus-achernar"]["lines"][1][-1], pole) < 0.1


def test_alignment_and_fov_rect_in_schema(env):
    from carina.core.tours import Tour, parse_fov_rect, validate

    res = env[3]
    r = res.resolve("alignment:cruzeiro-polo")
    assert r is not None and r.kind == "alignment" and r.size_deg > 20
    assert res.resolve("alignment:nao-existe") is None
    assert parse_fov_rect("1.29x0.73 Seestar S50") == (1.29, 0.73, "Seestar S50")
    assert parse_fov_rect("2,5 × 1,4") == (2.5, 1.4, "")
    assert parse_fov_rect("grande") is None
    bad = Tour.from_dict({"key": "t", "title": "T", "category": "extra", "steps": [
        {"title": "a", "text": "b", "fov_rect": "xx"}]})
    assert any("quadro" in e for e in validate(bad))


def test_smart_telescopes_in_equipment():
    from carina.catalogs.equipment import DEFAULT_DATA

    tels = {t["name"] for t in DEFAULT_DATA["telescopes"]}
    cams = {c["name"] for c in DEFAULT_DATA["cameras"]}
    assert {"Seestar S50 Pro (50/260)", "Vespera II (50/250)", "Dwarf 3 (30/150)"} <= tels
    assert {"Seestar S50 Pro — OS08B10", "Vespera Pro — IMX676"} <= cams


# --- tours gerados ----------------------------------------------------------------

@pytest.mark.parametrize("lat", [-22.9, -30.0])
def test_moon_terminator_tour(env, lat):
    from carina.core.tours import TourRun, validate
    from carina.core.tours_generated import generate

    ctx, now = _ctx(env, lat, dt.datetime(2026, 10, 12, 20, 0))
    tour = generate("lua-terminador", ctx)
    assert validate(tour) == [] and env[3].unresolved(tour) == []
    feats = [s for s in tour.steps if s.moon_feature]
    assert len(feats) >= 14
    whens = [s.time for s in feats]
    assert whens == sorted(whens)                     # na ordem das noites
    run = TourRun(tour, env[0], env[3], now, lat).prepare()
    assert not run.skipped, [s.reason for s in run.skipped]


def test_moon_terminator_sun_is_low_on_feature(env):
    from carina.core import moon as moonlib
    from carina.core.tours_generated import terminator_nights

    ctx, now = _ctx(env, -22.9, dt.datetime(2026, 10, 12, 18, 0))
    nights = terminator_nights(env[0], now)
    assert nights
    for e in nights[:6]:
        geom = moonlib.geometry(env[0], e["when"])
        alt = math.degrees(math.asin(float(e["feature"].vector @ geom.sun_body)))
        assert 0.5 <= alt <= 11.0, (e["feature"].name, alt)


@pytest.mark.parametrize("lat,minimum", [(-22.9, 90), (-30.0, 85), (-3.0, 105)])
def test_messier_marathon(env, lat, minimum):
    from carina.core.tours import TourRun, validate
    from carina.core.tours_generated import generate

    ctx, now = _ctx(env, lat, dt.datetime(2026, 10, 12, 20, 0))
    tour = generate("maratona-messier", ctx)
    assert validate(tour) == [] and env[3].unresolved(tour) == []
    labels = re.findall(r"\*\*(M \d+)\*\*", "\n".join(s.text for s in tour.steps))
    assert len(labels) == len(set(labels)) >= minimum
    times = [s.time for s in tour.steps[1:-1]]
    assert times == sorted(times)
    run = TourRun(tour, env[0], env[3], now, lat).prepare()
    assert len(run.steps) == len(tour.steps)


# --- quiz -------------------------------------------------------------------------

def test_asterism_quiz(env, qt_app):
    from carina.core import quiz as Q

    e = env[0]
    from carina.config import ObserverLocation
    e.set_location(ObserverLocation())
    info = []
    from carina.core.tours import Resolver
    for a in json.loads((DATA / "asterisms.json").read_text("utf-8")):
        r = env[3].resolve(f"asterism:{a['key']}")
        info.append(dict(a, center=r.icrs if r else None))
    when = dt.datetime(2026, 1, 16, 1, 0, tzinfo=UTC)             # 22h no Rio, janeiro
    keys = Q.visible_asterisms(e, info, when)
    assert "tres-marias" in keys and "bule" not in keys
    names = {a["key"]: a["name"] for a in info}
    q = Q.asterism_question(keys, names, random.Random(2))
    assert q.kind == "asterism" and q.answer in [k for k, _ in q.options]
    assert len({k for k, _ in q.options}) == 4


def test_asterism_quiz_dialog_hides_name_and_restores(win):
    from carina.core.skystate import SkyState
    from carina.ui.quiz import QuizDialog

    win.engine.time.set_fixed(dt.datetime(2026, 1, 16, 1, 0, tzinfo=UTC))
    before = SkyState.capture(win.sky, win.engine)
    dlg = QuizDialog(win, seed=4)
    dlg.mode.setCurrentIndex(dlg.mode.findData("asterism"))
    q = dlg.question
    assert q.kind == "asterism" and win.sky.hide_highlight_names
    assert ("asterism", q.answer) in win.sky.active_highlights()
    dlg._choose([k for k, _ in q.options].index(q.answer))
    assert dlg.score.right == 1
    dlg.close()
    assert not win.sky.hide_highlight_names
    assert before.same_as(SkyState.capture(win.sky, win.engine)) == []


# --- player -----------------------------------------------------------------------

def test_player_draws_alignment_moon_marker_and_rect(win, qt_app):
    from carina.core.tours import Tour

    tour = Tour.from_dict({
        "key": "teste-v023", "title": "Teste", "category": "extra",
        "when": "data:05-15 hora:21:00", "steps": [
            {"title": "Polo", "text": "Seta.", "target": "alignment:cruzeiro-polo",
             "fov": 70},
            {"title": "Quadro", "text": "Campo.", "target": "dso:NGC 3372",
             "fov_rect": "1.29x0.73 Seestar S50", "fov": 4},
            {"title": "Lua", "text": "Tycho.", "target": "body:Lua", "fov": 0.6,
             "moon_feature": "Tycho", "time": "em:2026-10-19T19:00", "skip_if_below": -90},
        ]})
    sky = win.sky
    win.start_tour(tour, _utc("2026-05-15T20:00"))
    player = win.tour_player()
    assert ("alignment", "cruzeiro-polo") in sky.active_highlights()
    assert len(sky._const_subset(sky.alignment_lines, "cruzeiro-polo").verts) > 10
    player.next()
    assert len(sky.fov_shapes) == 1 and sky.fov_shapes[0].kind == "rect"
    assert abs(math.degrees(sky.fov_shapes[0].width) - 1.29) < 1e-6
    assert sky.fov_shapes[0].label == "Seestar S50"
    player.next()
    assert sky.moon_marker == "Tycho"
    player.stop(False)
    assert sky.moon_marker == "" and not sky.active_highlights()


@pytest.mark.skipif(__import__("os").environ.get("CARINA_SKIP_GUI") == "1", reason="sem GUI")
def test_gl_alignment_and_moon_marker(tmp_path):
    """A seta e o anel da formação lunar desenhados com OpenGL, num subprocesso
    com a plataforma real do Qt (a "offscreen" da suíte não tem OpenGL)."""
    import os
    import subprocess
    import sys

    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
    env.pop("QT_QPA_PLATFORM", None)
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "gl_v023_script.py"),
                           str(tmp_path)], cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=300)
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")), None)
    assert line, proc.stderr[-2000:]
    r = json.loads(line[7:])
    assert r["alignment_frame"][2] is True
    assert r["moon_marker"] == "Tycho" and r["moon_r"] > 300
    assert r["tycho"] is not None and r["tycho"][2] > 5          # raio do anel em px
    assert r["after"] == ["", []]


# --- tours autorais novos ---------------------------------------------------------

def _authored() -> dict:
    from carina.core.tours import load_dir

    return {t.key: t for t in load_dir(DATA / "tours")}


def test_new_authored_tours_present_and_resolve(env):
    tours = _authored()
    missing = NEW_AUTHORED - set(tours)
    assert not missing, missing
    for key in NEW_AUTHORED:
        assert env[3].unresolved(tours[key]) == [], key


def test_88_constellations_in_four_nights():
    tours = _authored()
    seen = set()
    for key in ("constelacoes-verao", "constelacoes-outono", "constelacoes-inverno",
                "constelacoes-primavera"):
        for t in tours[key].targets():
            if t.startswith("const:"):
                seen.add(t[6:])
    ids = {c["id"] for c in json.loads((DATA / "constellations.json").read_text("utf-8"))}
    assert ids - seen == set(), sorted(ids - seen)


@pytest.mark.parametrize("key", sorted(NEW_AUTHORED))
def test_new_tours_fit_rio(env, key):
    """Escritos para o céu do Brasil: no Rio, nenhum passo é pulado."""
    from carina.config import ObserverLocation
    from carina.core import localtime
    from carina.core.tours import TourRun

    e = env[0]
    e.set_location(ObserverLocation())
    localtime.set_timezone("America/Sao_Paulo")
    tour = _authored()[key]
    run = TourRun(tour, e, env[3], _utc("2026-10-15T20:00"), -22.9).prepare()
    assert not run.skipped, [s.reason for s in run.skipped]
