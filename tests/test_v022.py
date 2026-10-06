"""v0.22: relatório da noite, planisfério, pôster, quiz, listas, lembretes,
caminho do Sol e brilho do céu pela Lua."""

import datetime as dt
import math
import random
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
EPHEM = ROOT / "data" / "ephemeris"
UTC = dt.timezone.utc
BRT = dt.timezone(dt.timedelta(hours=-3))


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


@pytest.fixture()
def win(qt_app):
    from carina.ui.mainwindow import MainWindow

    w = MainWindow()
    w.skip_state_save = True
    w.resize(1100, 760)
    w.show()
    qt_app.processEvents()
    yield w
    w.close()


# --- relatório da noite ------------------------------------------------------------

def test_night_report_data(engine, tmp_path):
    from carina.core.report import build_report, night_of, nights_with_observations
    from carina.core.userdata import UserData

    ud = UserData(tmp_path / "u.sqlite")
    ud.add_observation("dso", "M 42", "M 42", dt.datetime(2026, 10, 7, 1, 30, tzinfo=UTC))  # 22h30
    ud.add_observation("dso", "M 45", "M 45", dt.datetime(2026, 10, 7, 5, 0, tzinfo=UTC))   # 2h
    ud.add_observation("dso", "M 8", "M 8", dt.datetime(2026, 10, 7, 23, 0, tzinfo=UTC))    # outra noite
    assert night_of(dt.datetime(2026, 10, 7, 5, 0, tzinfo=UTC)) == dt.date(2026, 10, 6)
    rep = build_report(engine, ud, dt.date(2026, 10, 6), "Rio")
    assert [o["ident"] for o in rep.observations] == ["M 42", "M 45"]
    assert rep.astro_dusk is not None and rep.mid_utc is not None
    assert nights_with_observations(ud) == [dt.date(2026, 10, 7), dt.date(2026, 10, 6)]


@pytest.mark.skipif(__import__("os").environ.get("CARINA_SKIP_GUI") == "1", reason="sem GUI")
def test_gl_outputs(tmp_path):
    """Relatório, cartão, pôster, planisfério e camada do Sol, desenhados com
    OpenGL num subprocesso com a plataforma real (dados isolados)."""
    import json
    import os
    import subprocess
    import sys

    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
    env.pop("QT_QPA_PLATFORM", None)
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "gl_v022_script.py"),
                           str(tmp_path)], cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=300)
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")), None)
    assert line, proc.stderr[-2000:]
    r = json.loads(line[7:])
    assert r["report_bytes"] > 20_000
    assert r["card"][:2] == [1080, 1350] and r["card"][2] > 50_000
    assert r["poster"][1] > r["poster"][0] > 400 and r["poster_pdf"] == "%PDF-"
    assert r["planis_edit"] == "2026-10-05T21:00:00"
    assert r["sky_time"].startswith("2026-10-06T00:00:00")
    assert r["sun_path"][0] > 100 and r["sun_path"][1] > 60


# --- planisfério e pôster ------------------------------------------------------------------

def test_planisphere_date_and_hour_rings_align(engine):
    from carina.core.localtime import from_local_naive
    from carina.ui.planisphere import PlanisphereModel

    m = PlanisphereModel(-22.9, -43.2)
    for day, hh in ((dt.date(2026, 1, 15), 21), (dt.date(2026, 7, 10), 23),
                    (dt.date(2026, 10, 6), 2)):
        evening = day if hh >= 12 else day - dt.timedelta(days=1)
        local = dt.datetime.combine(day, dt.time(hh))
        when = from_local_naive(local).astimezone(UTC)
        lst = m.lst_hours(when)
        a_date = m.date_angle(evening, lst)
        a_clock = m.hour_angle_of_clock(hh if hh < 12 else hh - 24)
        diff = (math.degrees(a_date - a_clock) + 180) % 360 - 180
        assert abs(diff) < 1.5, (day, hh, diff)


def test_planisphere_horizon_is_altitude_zero(engine):
    from carina.ui.planisphere import PlanisphereModel, eq_from_altaz

    m = PlanisphereModel(-22.9, -43.2)
    az = np.radians(np.arange(0, 360, 15.0))
    ha, dec = eq_from_altaz(np.zeros_like(az), az, m.lat)
    lat = m.lat
    sin_alt = np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.cos(ha)
    assert np.allclose(sin_alt, 0.0, atol=1e-9)
    assert np.all(m.radius(dec) <= 1.0)                 # o horizonte cabe no disco
    # o zênite fica no meridiano, acima do polo (para cima na tela)
    zx, zy = m.altaz_point(90, 0)
    assert abs(zx) < 1e-9 and zy < 0


# --- quiz ------------------------------------------------------------------------

def test_quiz_questions(engine):
    import json

    from carina.catalogs.stars import StarCatalog
    from carina.core import quiz as Q

    info = json.loads((DATA / "constellations.json").read_text(encoding="utf-8"))
    when = dt.datetime(2026, 1, 16, 1, 0, tzinfo=UTC)            # 22h no Rio, janeiro
    cids = Q.visible_constellations(engine, info, when)
    assert "Ori" in cids and "Sco" not in cids
    rng = random.Random(3)
    q = Q.const_question(cids, rng)
    keys = [k for k, _l in q.options]
    assert q.answer in keys and len(set(keys)) == 4
    assert q.check(q.answer) and not q.check("Xyz")
    stars = StarCatalog(DATA)
    idx = Q.visible_bright_stars(engine, stars, when)
    assert stars.proper[idx[0]] == "Sirius"
    sq = Q.star_question(idx, stars, rng)
    assert sq.kind == "star" and sq.label


def test_quiz_dialog_scores_and_restores(win):
    from carina.core.skystate import SkyState
    from carina.ui.quiz import QuizDialog

    win.engine.time.set_fixed(dt.datetime(2026, 1, 16, 1, 0, tzinfo=UTC))
    before = SkyState.capture(win.sky, win.engine)
    dlg = QuizDialog(win, seed=1)
    q = dlg.question
    k = [key for key, _l in q.options].index(q.answer)
    dlg._choose(k)
    assert dlg.score.right == 1
    dlg.mode.setCurrentIndex(1)                       # encontre a estrela
    assert dlg.question.kind == "star" and not win.sky.layers["star_names"]
    assert dlg.answer_star(("star", -1)) is False     # clique errado
    assert dlg.score.wrong == 1
    dlg.close()
    assert before.same_as(SkyState.capture(win.sky, win.engine)) == []


# --- listas ----------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["csv", "telescopius", "skylist"])
def test_list_formats_roundtrip(fmt, tmp_path):
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.core.listformats import export, import_names, resolve

    stars = StarCatalog(DATA)
    dso = DsoCatalog(DATA / "dso.sqlite", tmp_path / "dso.sqlite")
    items, missing = resolve(["M 42", "NGC 253", "Sirius", "Plêiades"], stars, dso)
    assert not missing and len(items) == 4
    text = export(fmt, items)
    names = import_names(fmt, text)
    back, missing2 = resolve(names, stars, dso)
    assert not missing2
    assert [(b["kind"], b["ident"]) for b in back] == [(i["kind"], i["ident"]) for i in items]


def test_import_telescopius_sample(tmp_path):
    from carina.core.listformats import import_names

    sample = ('"Catalogue Entry","Familiar Name","Alternative Entries","Type"\n'
              '"NGC 2070","Tarantula Nebula","","Emission Nebula"\n'
              '"","Omega Centauri","NGC 5139","Globular Cluster"\n')
    assert import_names("telescopius", sample) == ["NGC 2070", "Omega Centauri"]


# --- lembretes ------------------------------------------------------------------------

def test_reminders_notify_once(win, monkeypatch):
    from carina.core.events import SkyEvent, add_reminder

    ev = SkyEvent(dt.datetime(2026, 10, 6, 23, 0, tzinfo=UTC), "lua", "Lua cheia", "")
    add_reminder(ev, win.userdata)
    shown = []
    monkeypatch.setattr(win, "notify", lambda t, b: shown.append((t, b)))
    assert win.check_reminders(dt.datetime(2026, 10, 6, 21, 0, tzinfo=UTC)) == []   # cedo
    due = win.check_reminders(dt.datetime(2026, 10, 6, 22, 20, tzinfo=UTC))
    assert [e.title for e in due] == ["Lua cheia"] and len(shown) == 1
    assert "40 min" in shown[0][1]
    assert win.check_reminders(dt.datetime(2026, 10, 6, 22, 30, tzinfo=UTC)) == []   # uma vez


def test_due_now_window():
    from carina.core.events import SkyEvent
    from carina.core.notify import due_now

    ev = SkyEvent(dt.datetime(2026, 1, 1, 12, tzinfo=UTC), "lua", "X")
    at = lambda h, m=0: dt.datetime(2026, 1, 1, h, m, tzinfo=UTC)  # noqa: E731
    assert due_now([ev], at(10, 59), set()) == []
    assert due_now([ev], at(11, 0), set()) == [ev]
    assert due_now([ev], at(12, 29), set()) == [ev]
    assert due_now([ev], at(12, 31), set()) == []
    assert due_now([ev], at(11, 30), {ev.uid}) == []


# --- caminho do Sol --------------------------------------------------------------------

def test_analemma_shape(engine):
    from carina.core.sunpath import analemma, analemma_extent

    for hour in (12.0, 8.0):                    # ao meio-dia, no Rio, passa perto do zênite
        length, width = analemma_extent(analemma(engine, 2026, hour))
        assert 45.5 < length < 48.5, hour       # 2 × 23,44°
        assert 2.0 < width < 9.0, hour          # a equação do tempo


def test_sunrise_azimuth_at_solstices(engine):
    from carina.core.sunpath import year_table

    rows = {r.date: r for r in year_table(engine, 2026, step_days=1)}
    june, dec = rows[dt.date(2026, 6, 21)], rows[dt.date(2026, 12, 21)]
    # Rio (22,9° S): nascer ~ENE em junho, ~ESE em dezembro, simétricos em torno de 90°
    assert 60 < june.sunrise_az < 68 and 112 < dec.sunrise_az < 120
    assert abs((june.sunrise_az + dec.sunrise_az) / 2 - 90) < 2
    assert dec.day_length_h > june.day_length_h + 2


# --- brilho do céu pela Lua (Krisciunas & Schaefer 1991) -------------------------------

def test_ks_model_behaviour():
    from carina.core.skybrightness import delta_mag, separation_for, sky_mag

    full = sky_mag(21.6, 0.0, 30.0, 45.0, 45.0)
    assert 17.0 < full < 19.0                   # Lua cheia a 30°: céu ~18 mag/arcsec²
    assert sky_mag(21.6, 0.0, 90.0, 45.0, 45.0) > full                 # mais longe, mais escuro
    assert delta_mag(21.6, 120.0, 30.0, 45.0, 45.0) > delta_mag(21.6, 0.0, 30.0, 45.0, 45.0)
    assert abs(delta_mag(21.6, 0.0, 30.0, 95.0, 45.0)) < 1e-9          # Lua abaixo do horizonte
    assert delta_mag(18.5, 0.0, 30.0, 45.0, 45.0) > delta_mag(21.6, 0.0, 30.0, 45.0, 45.0)
    # Lua cheia: o céu todo clareia mais de 2 mag; os anéis são relativos a 90° dela
    assert delta_mag(21.6, 0.0, 120.0, 45.0, 45.0) < -2.0
    assert separation_for(-1.0, 21.6, 0.0, 45.0, 45.0) == 180.0
    from carina.core.skybrightness import relative_separation
    rs = [relative_separation(d, 0.0, 45.0, 45.0) for d in (-1.5, -1.0, -0.5)]
    assert all(r is not None for r in rs) and rs == sorted(rs) and rs[-1] < 90
    ref = sky_mag(21.6, 0.0, 90.0, 45.0, 45.0)
    assert abs(sky_mag(21.6, 0.0, rs[1], 45.0, 45.0) - ref + 1.0) < 0.01
    # Lua quarto (α = 90°): mais fraca, anéis menores
    assert relative_separation(-1.0, 90.0, 45.0, 45.0) < rs[1]


def test_moon_zone_uses_ks(win):
    t = win.engine.ts.from_datetime(dt.datetime(2026, 10, 26, 2, 0, tzinfo=UTC))   # Lua cheia alta
    win.sky.set_bortle(3)
    rings = win.sky.moon_zone_radii(t)
    assert [d for d, _r in rings] == [-1.5, -1.0, -0.5]
    radii = [r for _d, r in rings]
    assert radii == sorted(radii)
