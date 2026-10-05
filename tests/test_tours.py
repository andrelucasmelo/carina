"""Tours guiados — motor, alvos, estado do céu, asterismos e histórias (v0.20)."""

import datetime as dt
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
EPHEM = ROOT / "data" / "ephemeris"
BRT = dt.timezone(dt.timedelta(hours=-3))


def _utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=BRT).astimezone(dt.timezone.utc)


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.config import ObserverLocation
    from carina.core import localtime
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    loc = ObserverLocation()
    e.set_location(loc)
    localtime.set_timezone(loc.timezone)
    return e


@pytest.fixture(scope="module")
def resolver():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from build_tours import _Dso

    from carina.catalogs import skygeometry
    from carina.catalogs.stars import StarCatalog
    from carina.core.tours import Resolver

    return Resolver(StarCatalog(DATA), _Dso(DATA / "dso.sqlite"),
                    skygeometry.load_constellation_info(DATA),
                    json.loads((DATA / "asterisms.json").read_text(encoding="utf-8")))


def _tour(**kw):
    from carina.core.tours import Tour

    base = {"key": "teste", "title": "Teste", "category": "iniciante",
            "when": "data:01-15 hora:22:00",
            "steps": [
                {"title": "Abertura", "text": "Olá.", "kind": "intro",
                 "target": "altaz:180,40"},
                {"title": "Órion", "text": "As Três Marias.", "target": "const:Ori",
                 "highlight": ["asterism:tres-marias"]},
                {"title": "Escorpião", "text": "Antares.", "target": "star:Antares"},
                {"title": "M 42", "text": "A nebulosa.", "target": "dso:M 42", "time": "+1h"},
            ]}
    base.update(kw)
    return Tour.from_dict(base)


# --- esquema ---------------------------------------------------------------

def test_validate_catches_errors():
    from carina.core.tours import validate

    assert validate(_tour()) == []
    bad = _tour(key="Com Espaço", category="nada", when="amanhã")
    bad.steps[1].target = "planeta:X"
    bad.steps[2].text = ""
    bad.steps[3].time = "depois"
    errs = " | ".join(validate(bad))
    for frag in ("chave inválida", "categoria", "relógio", "alvo 'planeta:X'",
                 "sem título ou sem texto", "hora 'depois'"):
        assert frag in errs, frag


def test_builtin_tours_load_and_resolve(resolver):
    from carina.core.tours import builtin_dir, load_dir, validate

    tours = load_dir(builtin_dir())
    assert tours, "nenhum tour embarcado"
    for t in tours:
        assert validate(t) == [], t.key
        assert resolver.unresolved(t) == [], t.key


def test_authored_step_length():
    """Textos autorais: curtos o bastante para ler no painel (15–190 palavras,
    com a história da constelação expandida)."""
    from carina.core import lore
    from carina.core.tours import builtin_dir, load_dir

    for t in load_dir(builtin_dir()):
        for s in t.steps:
            words = len(re.findall(r"\w+", lore.expand(s.text)))
            assert 15 <= words <= 190, (t.key, s.title, words)


# --- alvos -------------------------------------------------------------------

def test_star_specs(resolver):
    st = resolver.stars
    assert st.proper[resolver.star_index("Alnilam")] == "Alnilam"
    assert st.proper[resolver.star_index("eps Ori")] == "Alnilam"
    assert st.proper[resolver.star_index("alf Cen")] == "Rigil Kentaurus"   # componente brilhante
    i = resolver.star_index("mu-1 Sco")
    assert st.bayer[i] == "Mu-1" and st.con[i] == "Sco"
    assert resolver.star_index("HIP 26311") == resolver.star_index("Alnilam")
    assert resolver.star_index("omega Xyz") is None


def test_resolve_kinds(resolver):
    r = resolver.resolve("dso:M 42")
    assert r.kind == "dso" and r.selection[0] == "dso" and r.size_deg > 0.5
    c = resolver.resolve("const:Cru")
    assert c.label == "Cruzeiro do Sul" and abs(np.linalg.norm(c.icrs) - 1) < 1e-9
    a = resolver.resolve("asterism:tres-marias")
    assert a.label == "Três Marias" and 2.0 < a.size_deg < 4.0
    assert resolver.resolve("body:Júpiter").body == "Júpiter"
    assert resolver.resolve("altaz:90,30").altaz == (90.0, 30.0)
    assert resolver.resolve("dso:NGC 99999") is None


# --- execução ----------------------------------------------------------------

def test_tour_run_times_and_skip(engine, resolver):
    from carina.core.localtime import to_local
    from carina.core.tours import TourRun

    # data típica de janeiro: Órion e M 42 no céu; Antares ainda não nasceu
    run = TourRun(_tour(), engine, resolver, _utc("2026-10-05T15:00"), -22.9).prepare()
    assert to_local(run.base).strftime("%m-%d %H:%M") == "01-15 22:00"
    titles = [p.step.title for p in run.steps]
    assert titles == ["Abertura", "Órion", "M 42"]
    assert run.skipped and "Antares" in run.skipped[0].reason
    m42 = run.steps[2]
    assert (m42.when - run.base) == dt.timedelta(hours=1)
    assert m42.alt > 40
    assert any("época" in w for w in run.warnings)          # janeiro ≠ outubro
    assert not run.viable_tonight
    # navegação
    assert run.current.step.title == "Abertura"
    run.next(); run.next(); run.next()
    assert run.at_end and run.current.step.title == "M 42"
    run.prev()
    assert run.current.step.title == "Órion"


def test_latitude_warning(engine, resolver):
    from carina.core.tours import TourRun

    t = _tour(lat_range=[-35, 10])
    run = TourRun(t, engine, resolver, _utc("2026-01-15T20:00"), 51.5).prepare()
    assert any("latitudes" in w for w in run.warnings)


def test_inicio_da_noite(engine):
    from carina.core.localtime import to_local
    from carina.core.tours import base_time

    # à tarde: o fim do crepúsculo náutico desta noite (Rio, outubro ≈ 18h40)
    b = to_local(base_time(engine, "inicio_da_noite", _utc("2026-10-05T15:00")))
    assert b.date() == dt.date(2026, 10, 5) and 18 <= b.hour <= 19
    # de madrugada, ainda noite: agora mesmo
    now = _utc("2026-10-06T02:00")
    assert base_time(engine, "inicio_da_noite", now) == now
    # de manhã: a noite que vem
    b = to_local(base_time(engine, "inicio_da_noite", _utc("2026-10-06T09:00")))
    assert b.date() == dt.date(2026, 10, 6) and b.hour >= 18
    # hora fixa depois da meia-noite pertence à noite em curso
    b = to_local(base_time(engine, "hora:01:30", _utc("2026-10-05T20:00")))
    assert (b.day, b.hour, b.minute) == (6, 1, 30)


def test_progress(isolated_userdata):
    from carina.core.tours import done_keys, mark_done

    assert "abc" not in done_keys(isolated_userdata)
    mark_done(isolated_userdata, "abc")
    assert "abc" in done_keys(isolated_userdata)


# --- estado do céu -------------------------------------------------------------

def test_skystate_restores_everything(qt_app):
    from carina.core.skystate import SkyState
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    sky, eng = win.sky, win.engine
    eng.time.set_fixed(dt.datetime(2026, 3, 1, 1, 0, tzinfo=dt.timezone.utc))
    before = SkyState.capture(sky, eng)
    # o que um tour faz
    eng.time.set_fixed(dt.datetime(2026, 7, 1, 1, 0, tzinfo=dt.timezone.utc))
    sky.camera.set_direction(1.0, 0.7)
    sky.camera.fov = math.radians(5)
    sky.set_layer("asterisms", True)
    sky.set_layer("grid_altaz", False)
    sky.set_bortle(9)
    sky.selection = ("star", 3)
    sky.highlight_constellation("Ori", 3600)
    sky.highlight_asterism("bule", 3600)
    assert SkyState.capture(sky, eng).same_as(before)
    before.restore(sky, eng)
    assert before.same_as(SkyState.capture(sky, eng)) == []
    assert sky.active_highlights() == []
    win.close()


def test_skystate_keeps_realtime(qt_app):
    from carina.core.skystate import SkyState
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    eng = win.engine
    eng.time.to_now()
    st = SkyState.capture(win.sky, eng)
    assert st.realtime
    eng.time.set_fixed(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
    st.restore(win.sky, eng)
    now = dt.datetime.now(dt.timezone.utc)
    assert eng.time.speed == 1.0
    assert abs((eng.time.current_datetime() - now).total_seconds()) < 5
    win.close()


# --- asterismos ------------------------------------------------------------------

def test_asterisms_data():
    from carina.catalogs.stars import StarCatalog
    from carina.core.objects import _hip_index

    data = json.loads((DATA / "asterisms.json").read_text(encoding="utf-8"))
    assert len(data) >= 15
    hip = _hip_index(StarCatalog(DATA))
    for a in data:
        assert a["name"] and a["text"] and a["lines"], a["key"]
        for line in a["lines"]:
            assert len(line) >= 2
            assert all(h in hip for h in line), a["key"]


def test_search_finds_asterism(tmp_path):
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.core.search import search

    dso = DsoCatalog(DATA / "dso.sqlite", tmp_path / "dso.sqlite")
    res = search("três marias", StarCatalog(DATA), dso)
    assert (res[0].kind, res[0].key) == ("asterism", "tres-marias")
    res = search("cruzeiro", StarCatalog(DATA), dso)
    assert (res[0].kind, res[0].key) == ("const", "Cru")      # a constelação vem antes


def test_sky_asterism_layer_and_goto(qt_app):
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    sky = win.sky
    keys = {a["key"] for a in sky.asterism_info}
    assert {"tres-marias", "cruzeiro", "bule"} <= keys
    assert len(sky._const_subset(sky.asterism_lines, "bule").verts) >= 8
    assert sky.goto_asterism("cruzeiro")
    assert ("asterism", "cruzeiro") in sky.active_highlights()
    assert "asterisms" in win._layer_acts
    win.close()


# --- histórias -----------------------------------------------------------------------

def test_lore_88():
    from carina.core import lore

    data = lore.load()
    ids = {c["id"] for c in json.loads((DATA / "constellations.json").read_text("utf-8"))}
    assert set(data) == ids and len(data) == 88
    origins = {}
    for cid, d in data.items():
        for f in ("history", "find", "curiosity", "origin_text"):
            assert d[f].strip(), (cid, f)
        origins[d["origin"]] = origins.get(d["origin"], 0) + 1
    # 47 de Ptolomeu + Argo dividida em 3; 12 dos navegadores; 14 de Lacaille; 7 de Hevelius
    assert origins == {"ptolomeu": 47, "argo": 3, "navegadores": 12, "lacaille": 14,
                       "hevelius": 7, "plancius": 4, "renascimento": 1}


def test_lore_expand_and_card(qt_app):
    from carina.core import lore
    from carina.ui.mainwindow import MainWindow

    txt = lore.expand("Antes. {lore:Ori} Depois. {lore:find:Cru}")
    assert "Três Marias" in txt and "Guardiões" in txt and "{lore" not in txt
    win = MainWindow()
    win.skip_state_save = True
    win._show_constellation_card("Ori")
    assert win.card.title.text() == "Órion"
    assert "caçador" in win.card.description.text()
    win._refresh_info()                       # não troca a ficha da constelação
    assert win.card.selection == ("const", "Ori")
    win.close()
