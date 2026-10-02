"""Navegação: zoom ancorado no cursor e centralizar num pixel (revisão 2026-10)."""

import math

import numpy as np
import pytest

from carina.core.projection import FOV_MAX, FOV_MIN, Camera


@pytest.fixture
def camera():
    cam = Camera(az=math.radians(200.0), alt=math.radians(35.0),
                 fov=math.radians(60.0))
    cam.set_viewport(1600, 1000)
    return cam


@pytest.mark.parametrize("px,py", [(300.0, 200.0), (1500.0, 900.0), (800.0, 500.0), (100.0, 950.0)])
@pytest.mark.parametrize("factor", [0.82, 1.0 / 0.82, 0.5])
def test_zoom_at_keeps_point_under_cursor(camera, px, py, factor):
    before = camera.unproject(px, py)
    camera.zoom_at(factor, px, py)
    after = camera.unproject(px, py)
    sep = math.degrees(math.acos(float(np.clip(np.dot(before, after), -1, 1))))
    # erro angular pequeno frente ao passo de um pixel (~0,04°/px a 60°)
    assert sep < 0.05
    assert FOV_MIN <= camera.fov <= FOV_MAX


def test_zoom_at_center_equals_plain_zoom(camera):
    az0, alt0 = camera.az, camera.alt
    camera.zoom_at(0.7, 800.0, 500.0)
    assert abs(camera.az - az0) < 1e-6 and abs(camera.alt - alt0) < 1e-6
    assert abs(camera.fov - math.radians(42.0)) < 1e-9


def test_center_on_pixel_moves_point_to_center(camera):
    target = camera.unproject(1200.0, 300.0)
    camera.center_on_pixel(1200.0, 300.0)
    x, y, vis = camera.project(target[np.newaxis, :])
    assert vis[0]
    assert abs(x[0] - 800.0) < 0.5 and abs(y[0] - 500.0) < 0.5


def test_zoom_respects_limits(camera):
    for _ in range(80):
        camera.zoom_at(0.5, 400.0, 400.0)
    assert camera.fov == pytest.approx(FOV_MIN)
    for _ in range(80):
        camera.zoom_at(2.0, 400.0, 400.0)
    assert camera.fov == pytest.approx(FOV_MAX)
