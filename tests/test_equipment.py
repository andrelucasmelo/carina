"""Testes do simulador de campo de visão (item 7)."""

import math

import pytest

from carina.catalogs.equipment import (
    Accessory, Camera, EquipmentStore, Eyepiece, Telescope,
    compute_camera_fov, compute_eyepiece_fov,
)


def test_camera_fov_ed80_asi2600():
    scope = Telescope("ED 80/600", aperture_mm=80, focal_mm=600)
    cam = Camera("ASI2600MC", width_mm=23.5, height_mm=15.7, pixel_um=3.76,
                 width_px=6248, height_px=4176)
    shape = compute_camera_fov(scope, cam)
    assert shape.kind == "rect"
    # 2·atan(23,5 / 1200) = 2,244°
    assert math.degrees(shape.width) == pytest.approx(2.244, abs=0.005)
    assert math.degrees(shape.height) == pytest.approx(1.499, abs=0.005)
    details = dict(shape.details)
    assert "1.29″/px" in details["Escala de placa"]  # 206,265·3,76/600
    assert details["Amostragem"] == "adequada"


def test_barlow_doubles_focal_and_halves_field():
    scope = Telescope("Newton 200/1000", aperture_mm=200, focal_mm=1000)
    cam = Camera("ASI533MC", width_mm=11.31, height_mm=11.31, pixel_um=3.76)
    plain = compute_camera_fov(scope, cam)
    doubled = compute_camera_fov(scope, cam, Accessory("Barlow 2×", 2.0))
    # campos pequenos: o ângulo cai praticamente pela metade
    assert doubled.width == pytest.approx(plain.width / 2, rel=0.01)
    assert "Barlow" in doubled.label


def test_reducer_widens_field():
    scope = Telescope("SC 8\"", aperture_mm=203, focal_mm=2032)
    cam = Camera("APS-C", width_mm=23.5, height_mm=15.7)
    plain = compute_camera_fov(scope, cam)
    reduced = compute_camera_fov(scope, cam, Accessory("Redutor 0,63×", 0.63))
    assert reduced.width > plain.width


def test_eyepiece_magnification_and_exit_pupil():
    scope = Telescope("Newton 200/1000", aperture_mm=200, focal_mm=1000)
    eye = Eyepiece("Plössl 25 mm", focal_mm=25, afov_deg=52)
    shape = compute_eyepiece_fov(scope, eye)
    assert shape.kind == "circle"
    details = dict(shape.details)
    assert details["Ampliação"] == "40×"          # 1000/25
    assert details["Pupila de saída"] == "5.0 mm"  # 200/40
    # campo real = 52 / 40 = 1,3°
    assert math.degrees(shape.width) == pytest.approx(1.3, abs=0.01)


def test_store_roundtrip_and_defaults(tmp_path):
    path = tmp_path / "equipamentos.json"
    store = EquipmentStore(path)
    assert len(store.items("telescopes")) >= 8
    assert len(store.items("cameras")) >= 6

    store.add("telescopes", Telescope("Meu tubo", 114, 900))
    reloaded = EquipmentStore(path)
    assert reloaded.find("telescopes", "Meu tubo") is not None

    reloaded.restore_defaults()
    assert reloaded.find("telescopes", "Meu tubo") is None


def test_telescope_focal_ratio():
    assert Telescope("t", aperture_mm=200, focal_mm=1000).ratio == 5.0
