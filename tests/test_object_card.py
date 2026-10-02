"""Ficha unificada do objeto (v0.15 T5)."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EPHEM = ROOT / "data" / "ephemeris"
DATA = ROOT / "data" / "processed"
REF = dt.datetime(2026, 10, 3, 1, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists() or not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine
    from carina.core.userdata import UserData
    from carina.ui.object_card import CardContext

    engine = SkyEngine(EPHEM)
    engine.set_location(ObserverLocation())
    engine.time.set_fixed(REF)
    tmp = tmp_path_factory.mktemp("card")
    shutil.copy2(DATA / "dso.sqlite", tmp / "dso.sqlite")
    dso = DsoCatalog(DATA / "dso.sqlite", tmp / "dso.sqlite")
    ud = UserData(tmp / "carina.sqlite")
    c = CardContext(engine=engine, stars=StarCatalog(DATA), dso=dso, userdata=ud,
                    bortle=lambda: 5)
    yield c
    dso.cx.close()
    ud.close()


def _dso_id(ctx, name):
    return ctx.dso.cx.execute("SELECT id FROM objects WHERE name = ?", (name,)).fetchone()[0]


def test_card_for_dso_matches_visibility(ctx):
    from carina.core.objects import ObjectRef
    from carina.core.visibility import visibility_of
    from carina.ui.object_card import ObjectCard

    sel = ("dso", _dso_id(ctx, "M 42"))
    card = ObjectCard(ctx)
    card.set_selection(sel)
    s = card.summary()
    vis = visibility_of(ctx.engine, ObjectRef.resolve(sel, ctx.stars, ctx.dso), REF)
    assert s["rise"] == vis.rise_utc and s["transit"] == vis.transit_utc
    assert abs(s["window_minutes"] - vis.window_minutes) < 1e-6
    assert s["score"] > 0 and s["verdict"]
    assert "Órion" in card.title.text()
    assert "Nasce" in card.today.text() and "Melhor hora" in card.today.text()
    assert "AR · Dec J2000" in card.position.text()
    # o cálculo da noite é reaproveitado
    first = card._tonight
    card.refresh()
    assert card._tonight is first


def test_card_for_star_and_body(ctx):
    from carina.ui.object_card import ObjectCard

    sirius = next(i for i, n in ctx.stars.proper.items() if n == "Sirius")
    card = ObjectCard(ctx)
    card.set_selection(("star", sirius))
    assert "anos-luz" in card.description.text()
    assert "8,6" in card.description.text()
    assert card.summary()["instrument"] == "olho"
    card.set_selection(("body", "Saturno"))
    assert card.summary()["score"] > 0
    assert "UA" in card.position.text()
    assert not card.buttons["details"].isEnabled()      # corpo: sem gráfico anual
    card.set_selection(None)
    assert card.title.text() == "Nenhum objeto"


def test_actions_emit_and_journal_shows(ctx):
    from carina.ui.object_card import ObjectCard

    sel = ("dso", _dso_id(ctx, "M 8"))
    card = ObjectCard(ctx)
    card.set_selection(sel)
    got = []
    card.actionRequested.connect(lambda k, s: got.append((k, s)))
    card.buttons["track"].click()
    card.buttons["copy"].click()
    assert got == [("track", sel), ("copy", sel)]
    assert card.copy_text().startswith("M 8") and "AR" in card.copy_text()
    assert card.journal.isHidden()
    ctx.userdata.add_observation("dso", "M 8", "M 8", REF, note="bela noite")
    lid = ctx.userdata.ensure_list()
    ctx.userdata.add_item(lid, "dso", "M 8", "M 8")
    card.set_selection(sel)
    assert "Observado 1×" in card.journal.text() and "bela noite" in card.journal.text()
    assert "Minha lista" in card.journal.text()


def test_invalidate_on_bortle_change(ctx):
    from carina.ui.object_card import CardContext, ObjectCard

    level = {"v": 1}
    c2 = CardContext(engine=ctx.engine, stars=ctx.stars, dso=ctx.dso,
                     userdata=ctx.userdata, bortle=lambda: level["v"])
    card = ObjectCard(c2)
    card.set_selection(("dso", _dso_id(ctx, "M 33")))
    dark = card.summary()["score"]
    level["v"] = 8
    card.refresh()                     # a chave mudou: recalcula sozinho
    assert card.summary()["score"] < dark


def test_instrument_uses_minor_axis(ctx):
    """M 8 (45′ × 30′) não é "difuso": continua alvo de binóculo."""
    from carina.ui.object_card import ObjectCard

    card = ObjectCard(ctx)
    card.set_selection(("dso", _dso_id(ctx, "M 8")))
    assert card.summary()["instrument"] == "binoculo"


def test_annual_chart_hides_below_horizon(monkeypatch):
    """Gráfico anual: 0° é a base; nada abaixo dele é desenhado."""
    import datetime as dt

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainter

    from carina.ui import object_window
    from carina.ui.object_window import AltitudeChart

    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=10 * i) for i in range(10)]
    mid = [-30, -10, 5, 20, 40, 60, 40, 10, -5, -40]
    chart = AltitudeChart(dates, mid, [v + 10 for v in mid])
    chart.resize(600, 300)
    lines = []

    class Rec(QPainter):
        def drawLine(self, *a):
            if len(a) == 2 and isinstance(a[0], QPointF):
                lines.append(a)
            return super().drawLine(*a)

    monkeypatch.setattr(object_window, "QPainter", Rec)
    chart.grab()
    plot = chart._plot_rect
    assert plot is not None
    curve = [ln for ln in lines if ln[1].x() > ln[0].x() + 1
             and abs(ln[1].y() - ln[0].y()) > 0.01]
    assert len(curve) >= 6
    # nenhum segmento desenhado fica inteiramente abaixo de 0° (a base)
    assert all(min(a.y(), b.y()) <= plot.bottom() + 0.5 for a, b in curve)
    # os dois segmentos totalmente negativos (início e fim) foram omitidos
    assert len(curve) <= 2 * (len(dates) - 1) - 2
