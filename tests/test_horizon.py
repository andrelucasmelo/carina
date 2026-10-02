"""Horizonte do quintal (v0.15 T4): interpolação circular, bloqueio, CSV."""

import numpy as np

from carina.core.horizon import PRESETS, HorizonProfile, preset_wall


def test_flat_blocks_nothing_above_zero():
    h = HorizonProfile()
    assert h.is_flat
    assert h.altitude_at(123.0) == 0.0
    assert not h.blocks(10.0, 1.0)


def test_circular_interpolation_across_north():
    h = HorizonProfile([(350.0, 10.0), (10.0, 30.0), (180.0, 0.0)])
    assert abs(h.altitude_at(0.0) - 20.0) < 1e-9          # meio do trecho 350→10
    assert abs(h.altitude_at(360.0) - 20.0) < 1e-9
    assert abs(h.altitude_at(355.0) - 15.0) < 1e-9
    arr = h.altitude_at(np.array([350.0, 10.0, -10.0]))
    assert np.allclose(arr, [10.0, 30.0, 10.0])


def test_blocks_vectorized():
    h = preset_wall(10.0)
    assert h.blocks(45.0, 5.0)
    assert not h.blocks(45.0, 15.0)
    res = h.blocks(np.array([0.0, 90.0]), np.array([9.0, 11.0]))
    assert list(res) == [True, False]


def test_csv_round_trip_and_excel_decimal():
    h = HorizonProfile([(0, 5), (90, 22.5), (270, 12)])
    back = HorizonProfile.from_csv(h.to_csv())
    assert back.points == h.points
    excel = "azimute;altitude\n0;5,5\n180;10,25\n"
    pts = HorizonProfile.from_csv(excel).points
    assert pts == [(0.0, 5.5), (180.0, 10.25)]


def test_normalization_and_presets():
    h = HorizonProfile([(370, 5), (10, 7), (-90, 100)])
    assert h.points == [(10.0, 7.0), (270.0, 89.0)]   # 370≡10, último vence
    for factory in PRESETS.values():
        p = factory()
        assert isinstance(p, HorizonProfile)
        assert 0.0 <= p.max_altitude() < 60.0


def test_ground_mesh_follows_profile():
    from carina.catalogs.skygeometry import build_ground, build_silhouette

    flat_v, flat_t = build_ground()
    prof = HorizonProfile([(150, 35), (210, 35), (240, 3), (120, 3)])
    v, t = build_ground(profile=prof)
    assert len(v) > len(flat_v) and t.max() < len(v)
    top_alt = np.degrees(np.arcsin(v[:360, 2]))
    assert abs(top_alt[180] - 35.0) < 0.01 and abs(top_alt[0] - 3.0) < 0.5
    sil = build_silhouette(prof)
    assert sil.shape == (361, 3)
    assert build_silhouette(HorizonProfile()) is None


def test_dialog_saves_and_emits(tmp_path):
    from pathlib import Path

    from carina.core.userdata import UserData

    ephem = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
    data = Path(__file__).resolve().parent.parent / "data" / "processed"
    if not (ephem / "de440s.bsp").exists():
        import pytest
        pytest.skip("efeméride ausente")
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine
    from carina.ui.horizon_dialog import HorizonDialog

    engine = SkyEngine(ephem)
    engine.set_location(ObserverLocation())
    ud = UserData(tmp_path / "c.sqlite")
    dlg = HorizonDialog(engine, StarCatalog(data), ud, "Rio")
    got = []
    dlg.profileApplied.connect(got.append)
    dlg.editor.set_profile(preset_wall(15.0))
    dlg.name.setText("Muro")
    dlg._save()
    assert got and got[-1].name == "Muro" and got[-1].max_altitude() == 15.0
    assert ud.active_horizon().name == "Muro"
    # editor: conversão pixel ↔ (az, alt) é inversa
    dlg.editor.resize(800, 300)
    pt = dlg.editor.to_px(123.0, 22.0)
    az, alt = dlg.editor.from_px(pt.x(), pt.y())
    assert abs(az - 123.0) < 0.01 and abs(alt - 22.0) < 0.01
    dlg.close()
    ud.close()
