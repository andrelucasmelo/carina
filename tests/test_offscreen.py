"""Render fora da tela (v0.16 T1): tamanho, tema e camadas, sem mexer na
vista do usuário. Precisa de OpenGL real: roda o Carina num subprocesso
(como o teste de fumaça). ``CARINA_SKIP_GUI=1`` pula."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(os.environ.get("CARINA_SKIP_GUI") == "1",
                                reason="sem GUI")
ALL_LAYERS = ["stars", "dso", "dso_images", "milkyway", "const_lines", "const_bounds",
              "grid_altaz", "grid_eq", "equator", "ecliptic", "meridian", "planets",
              "ground", "horizon", "cardinals", "atmosphere", "moon_zone"]


def _run(tmp_path, name, *extra):
    out = tmp_path / f"{name}.png"
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
    env.pop("QT_QPA_PLATFORM", None)
    proc = subprocess.run(
        [sys.executable, "-m", "carina", "--screenshot", str(tmp_path / "tela.png"),
         "--size", "640x480", "--at", "2026-10-03T01:00:00Z", "--look", "225,45",
         "--fov", "70", "--offscreen", str(out), "--offscreen-size", "400x300",
         *extra],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "estado_preservado=True" in proc.stdout
    from PySide6.QtGui import QImage

    img = QImage(str(out))
    assert not img.isNull()
    return img


def _channels(img, step=4):
    reds = greens = blues = lit = 0
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            c = img.pixelColor(x, y)
            greens = max(greens, c.green())
            blues = max(blues, c.blue())
            reds = max(reds, c.red())
            lit += c.lightness() > 40
    return reds, greens, blues, lit


def test_size_and_red_theme(tmp_path):
    img = _run(tmp_path, "red", "--offscreen-theme", "red", "--offscreen-scale", "2")
    assert (img.width(), img.height()) == (800, 600)
    r, g, b, _lit = _channels(img)
    assert r > 100 and g == 0 and b == 0


def test_light_theme_is_paper(tmp_path):
    img = _run(tmp_path, "light", "--offscreen-theme", "light", "--offscreen-scale", "1.5")
    assert (img.width(), img.height()) == (600, 450)
    corner = img.pixelColor(5, 5)
    assert corner.lightness() > 230


def test_layers_off_leave_empty_sky(tmp_path):
    args = []
    for layer in ALL_LAYERS:
        args += ["--offscreen-off", layer]
    img = _run(tmp_path, "vazio", "--offscreen-theme", "dark", *args)
    _r, _g, _b, lit = _channels(img)
    total = (img.width() // 4) * (img.height() // 4)
    assert lit / total < 0.01
