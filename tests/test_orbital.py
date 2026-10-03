"""ISS e satélites com TLE fixo (v0.19 T7)."""

import datetime as dt
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
UTC = dt.timezone.utc

# TLE da ISS do exemplo da documentação do Skyfield (janeiro de 2014)
ISS_TLE = """ISS (ZARYA)
1 25544U 98067A   14020.93268519  .00009878  00000-0  18200-3 0  5082
2 25544  51.6498 109.4756 0003572  55.9686 274.8005 15.49815350868473
"""


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    # Bluffton, Ohio — o local do exemplo da documentação
    e.set_location(ObserverLocation("Bluffton", 40.8939, -83.8917, 250.0, "America/New_York"))
    return e


def test_parse_and_checksum(tmp_path):
    from carina.core.orbital import parse_tle, save, load_saved, iss

    tles = parse_tle(ISS_TLE)
    assert len(tles) == 1 and tles[0].norad == 25544 and tles[0].name == "ISS (ZARYA)"
    assert tles[0].epoch.date() == dt.date(2014, 1, 20)
    broken = ISS_TLE.replace("5082", "5083")
    assert parse_tle(broken) == []
    path = tmp_path / "s.tle"
    save(ISS_TLE + "\nlixo\n", path)
    assert iss(load_saved(path)).norad == 25544


def test_known_passes(engine):
    """Documentação do Skyfield: acima de 30° em 23/01/2014, culminações
    às 06:26:58 e 12:56:27 UTC."""
    from carina.core.orbital import parse_tle, passes

    tle = parse_tle(ISS_TLE)[0]
    ps = passes(engine, tle, dt.datetime(2014, 1, 23, tzinfo=UTC), days=1, min_alt=30)
    culms = [p.culminate for p in ps]
    for want in (dt.datetime(2014, 1, 23, 6, 26, 58, tzinfo=UTC),
                 dt.datetime(2014, 1, 23, 12, 56, 27, tzinfo=UTC)):
        assert min(abs((c - want).total_seconds()) for c in culms) < 60
    for p in ps:
        assert p.rise < p.culminate < p.set and p.max_alt >= 30
        if p.visible:
            assert p.visible_from is not None and p.rise <= p.visible_from <= p.set


def test_track(engine):
    from carina.core.orbital import parse_tle, passes, track

    tle = parse_tle(ISS_TLE)[0]
    p = passes(engine, tle, dt.datetime(2014, 1, 23, tzinfo=UTC), days=1, min_alt=10)[0]
    pts = track(engine, tle, p.rise, p.set, 15)
    assert len(pts) > 5
    alts = [float(v[2]) for _, v in pts]
    assert max(alts) > min(alts)


def test_dialog_and_sky_track(tmp_path, monkeypatch, engine):
    from carina.core import orbital as O
    from carina.ui.satellites_dialog import SatellitesDialog

    monkeypatch.setattr(O, "tle_path", lambda: tmp_path / "s.tle")
    engine.time.set_fixed(dt.datetime(2014, 1, 23, tzinfo=UTC))
    dlg = SatellitesDialog(engine)
    assert dlg.list.count() == 0
    assert dlg.import_text(ISS_TLE) == 1
    assert dlg.table.rowCount() > 2
    assert "antigos" not in dlg.lbl_age.text()          # elementos de 2 dias
    got = []
    dlg.showPass.connect(lambda t, p: got.append((t, p)))
    dlg._show(0)
    assert got and got[0][0].norad == 25544
    dlg.close()
    engine.time.set_fixed(None)
