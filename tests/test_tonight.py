"""Hoje à noite (v0.15 T11): conteúdo determinístico para uma data."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EPHEM = ROOT / "data" / "ephemeris"
DATA = ROOT / "data" / "processed"


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists() or not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs.dso import DsoCatalog
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    tmp = tmp_path_factory.mktemp("tonight")
    shutil.copy2(DATA / "dso.sqlite", tmp / "dso.sqlite")
    d = DsoCatalog(DATA / "dso.sqlite", tmp / "dso.sqlite")
    yield e, d
    d.cx.close()


def test_summary_is_deterministic(ctx):
    from carina.core.tonight import tonight_summary

    e, d = ctx
    ref = dt.datetime(2026, 10, 3, 1, tzinfo=dt.timezone.utc)
    a = tonight_summary(e, d, ref, bortle=5)
    b = tonight_summary(e, d, ref, bortle=5)
    assert [i.ident for i in a.best] == [i.ident for i in b.best]
    assert len(a.best) == 5 and all(i.score > 0 for i in a.best)
    assert [i.score for i in a.best] == sorted([i.score for i in a.best], reverse=True)
    assert len({i.ident for i in a.best}) == 5
    names = {i.ident for i in a.planets}
    assert "Saturno" in names and "Júpiter" not in names     # Júpiter só de madrugada baixa
    assert a.moon_phase in ("Quarto minguante", "Gibosa minguante")
    assert 0 < a.moonless_minutes <= a.dark_minutes


def test_new_moon_beats_full_moon_in_dark_hours(ctx):
    from carina.core.tonight import tonight_summary

    e, d = ctx
    new = tonight_summary(e, d, dt.datetime(2026, 12, 9, 3, tzinfo=dt.timezone.utc))
    full = tonight_summary(e, d, dt.datetime(2026, 12, 24, 3, tzinfo=dt.timezone.utc))
    assert new.moonless_minutes > full.moonless_minutes + 120
    assert "excelente" in new.verdict.lower() or "boa" in new.verdict.lower()
    assert full.moon_phase == "Cheia"


def test_panel_builds_and_emits(ctx):
    from carina.core.tonight import tonight_summary
    from carina.ui.tonight_panel import TonightPanel

    e, d = ctx
    s = tonight_summary(e, d, dt.datetime(2026, 10, 3, 1, tzinfo=dt.timezone.utc))
    panel = TonightPanel(s, "Rio")
    assert panel.best.rowCount() == 5 and panel.planets.rowCount() == len(s.planets)
    got = []
    panel.gotoAtTimeRequested.connect(lambda k, i, w: got.append((k, i, w)))
    panel._act("time")
    assert got and got[0][0] == "dso" and got[0][2] == s.best[0].best_utc
    panel.close()
