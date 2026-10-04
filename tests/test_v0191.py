"""Correções da 0.19.1: setups, montagens inteligentes, subs com margem,
sugestões de alvos, gráfico de horas e rótulos com campo de visão (B-029)."""

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
UTC = dt.timezone.utc


def _vec(ra_h, dec_d):
    ra, dec = math.radians(ra_h * 15), math.radians(dec_d)
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


class FakeSettings:
    def __init__(self):
        self.d = {}

    def value(self, key, default, type_=None):
        return self.d.get(key, default)

    def set_value(self, key, value):
        self.d[key] = value


# --- margens e quantidade de subs ---------------------------------------

def test_margin_bands_inclusive():
    from carina.core.exposure import margin_for

    expected = {30: 10, 60: 10, 61: 15, 120: 15, 121: 20, 180: 20, 181: 25, 300: 25,
                301: 30, 900: 30}
    for sub, pct in expected.items():
        assert margin_for(sub) == pct, sub


def test_custom_margins_sorted_and_open_band():
    from carina.core.exposure import margin_for, normalize_margins

    table = normalize_margins([(240, 18), (30, 5), (None, 40)])
    assert table == [(30.0, 5.0), (240.0, 18.0), (None, 40.0)]
    assert margin_for(20, table) == 5 and margin_for(200, table) == 18
    assert margin_for(500, table) == 40
    # sem faixa aberta: a última fechada vale para o resto
    assert normalize_margins([(60, 10)])[-1] == (None, 10.0)


def test_subs_for_goal_and_night():
    from carina.core.exposure import subs_for, subs_in

    sp = subs_for(10, 120)                       # 10 h de subs de 2 min, 15%
    assert (sp.good, sp.total, sp.margin_pct) == (300, 345, 15.0)
    assert sp.shoot_hours == pytest.approx(11.5)
    shot, good = subs_in(2.0, 120)
    assert shot == 60 and good == 52


# --- montagens ------------------------------------------------------------

def test_smart_mount_kinds(tmp_path):
    from carina.catalogs.equipment import (EquipmentStore, Setup, mount_flips,
                                           mount_is_altaz)

    st = EquipmentStore(tmp_path / "eq.json")
    alt = Setup("a", "Seestar S50 (50/250)", mount="Telescópio inteligente (Alt-Az)")
    eq = Setup("b", "Seestar S50 (50/250)", mount="Telescópio inteligente (EQ, cunha)")
    bare = Setup("c", "Seestar S50 (50/250)")
    gem = Setup("d", "Refrator ED 80/600", mount="Equatorial EQ5/HEQ5")
    assert alt.mount_kind(st) == "smart-altaz" and alt.is_altaz(st)
    assert eq.mount_kind(st) == "smart-eq" and not eq.is_altaz(st)
    assert bare.mount_kind(st) == "smart-altaz"
    assert gem.mount_kind(st) == "equatorial"
    assert mount_flips("equatorial") and not mount_flips("smart-eq")
    assert mount_is_altaz("smart-altaz") and not mount_is_altaz("smart-eq")


def test_old_equipment_file_gets_smart_mounts(tmp_path):
    import json

    from carina.catalogs.equipment import EquipmentStore

    path = tmp_path / "eq.json"
    path.write_text(json.dumps({"version": 2, "mounts": [
        {"name": "Minha EQ", "kind": "equatorial", "payload_kg": 9}]}), encoding="utf-8")
    st = EquipmentStore(path)
    names = [m.name for m in st.items("mounts")]
    assert "Minha EQ" in names and "Telescópio inteligente (EQ, cunha)" in names


def test_smart_eq_has_no_meridian_cut(engine):
    from carina.core.session import SessionOptions, SessionTarget, plan_session

    # M 42 culmina perto da meia-noite em dezembro
    tg = [SessionTarget("M 42", _vec(5.588, -5.39), "M 42")]
    when = dt.datetime(2026, 12, 15, 3, tzinfo=UTC)
    gem = plan_session(engine, tg, when, SessionOptions(min_alt=25))
    fork = plan_session(engine, tg, when, SessionOptions(min_alt=25, meridian_flip=False))
    assert any(b.flip_after for b in gem.blocks)
    assert not any(b.flip_after for b in fork.blocks)
    assert fork.hours_for(0) > gem.hours_for(0)      # não perde a folga do meridiano
    assert len(fork.blocks) == 1


def test_smart_eq_sub_limit():
    from carina.catalogs.equipment import Camera, Telescope
    from carina.core.exposure import BORTLE_SQM, suggest_sub

    scope, cam = Telescope("S50", 50, 250), Camera("Seestar S50 — IMX462", 5.57, 3.13, 2.9)
    assert suggest_sub(BORTLE_SQM[1], scope, cam, mount="smart-altaz").sub_s <= 30
    assert suggest_sub(BORTLE_SQM[1], scope, cam, mount="smart-eq").sub_s <= 60
    assert suggest_sub(BORTLE_SQM[1], scope, cam, mount="smart-eq").sub_s > 30


# --- sugestões --------------------------------------------------------------

def test_rank_candidates(engine):
    from carina.core.session import SessionOptions, rank_candidates

    # dezembro no Rio: M 42 a noite toda; M 8 (Sagitário) já se pôs
    hours, altmax, q, times = rank_candidates(
        engine, [_vec(5.588, -5.39), _vec(18.06, -24.38)],
        dt.datetime(2026, 12, 15, 3, tzinfo=UTC), SessionOptions(min_alt=30))
    assert times
    assert hours[0] > 4 and hours[1] < 0.5
    assert altmax[0] > 60 and q[0] > q[1]


# --- campo de visão: salvar, lembrar, rótulos ----------------------------------

def test_fov_dialog_save_and_remember(tmp_path, isolated_userdata):
    from carina.catalogs.equipment import EquipmentStore, load_setup, setup_names
    from carina.ui.fov_dialog import FovDialog

    st = EquipmentStore(tmp_path / "eq.json")
    settings = FakeSettings()
    chosen = []
    d = FovDialog(st, settings=settings)
    d.setupChosen.connect(chosen.append)
    d.restore_last()                                  # nada guardado ainda
    d.cb_scope.setCurrentIndex(d.cb_scope.findText("Refrator ED 80/600"))
    d.cb_camera.setCurrentIndex(d.cb_camera.findText("ZWO ASI2600MC (APS-C)"))
    assert "Refrator ED 80/600" in settings.d["equipment/last_setup"]
    d._store_setup("80ED v0191")
    assert "80ED v0191" in setup_names(isolated_userdata)
    assert chosen == ["80ED v0191"] and "salvo" in d.lbl_saved.text()
    d.cb_camera.setCurrentIndex(d.cb_camera.findText("ZWO ASI533MC (1\")"))
    d._save_current()                                 # grava por cima, sem perguntar
    assert load_setup("80ED v0191", isolated_userdata).camera.startswith("ZWO ASI533MC")
    d.close()
    # reabrir: volta ao último setup, mesmo sem nome
    d2 = FovDialog(st, settings=settings)
    d2.restore_last()
    assert d2.cb_scope.currentText() == "Refrator ED 80/600"
    d2.close()


def test_fov_center_with_selection_and_frame_time(qt_app):
    """B-029: ``self._frame_t or …`` chamava bool() num Time do Skyfield e o
    erro derrubava o quadro antes dos rótulos."""
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    sky = win.sky
    t = sky.engine.time.current()
    m = sky.engine.horizontal_matrix(t).astype(np.float32)
    sky._frame_t = t
    sky.selection = ("star", 0)
    sky.fov_follow_selection = True
    u = np.asarray(sky._fov_center_vec(m), dtype=np.float64)
    assert u.shape == (3,) and abs(np.linalg.norm(u) - 1.0) < 1e-3
    win.close()


# --- gráfico de horas ---------------------------------------------------------

def test_year_chart_hover(qt_app):
    from types import SimpleNamespace

    from carina.ui.session_window import YearChart

    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=2 * k) for k in range(183)]
    img = SimpleNamespace(dates=dates, hours=np.linspace(0, 7.5, 183),
                          dark_hours=np.full(183, 9.0), best_months=lambda n: [1])
    ch = YearChart()
    ch.resize(600, 160)
    ch.set_data(img, "teste")
    ch.grab()                                          # desenha (geometria das barras)
    left, _top, w, _h, hmax = ch._geom
    assert hmax == 8.0
    k = ch.bar_at(left + w * 0.5 + 0.1)
    assert k == 91
    assert "h úteis" in ch.tooltip_text(k) and "9,0 h" in ch.tooltip_text(k)
    assert ch.bar_at(left - 5) == -1


def test_margins_dialog_roundtrip(qt_app):
    from carina.core.exposure import DEFAULT_MARGINS
    from carina.ui.session_window import MarginsDialog

    dlg = MarginsDialog(DEFAULT_MARGINS)
    assert dlg.table() == [(60.0, 10.0), (120.0, 15.0), (180.0, 20.0), (300.0, 25.0),
                           (None, 30.0)]
    dlg._add_new()                                     # nova faixa depois da maior fechada
    assert (360.0, 30.0) in dlg.table()
