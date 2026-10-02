"""Limpeza de estrelas da textura da Via Láctea (pré-0.17): sem platôs
quadrados — o remendo é isotrópico e entra com borda suave."""

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location("build_mwtex", ROOT / "scripts" / "build_mwtex.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_star_removed_without_square_step():
    mod = _module()
    h, w = 120, 160
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = 40.0 + 0.4 * xx + 0.2 * yy                      # céu difuso em rampa
    star = 180.0 * np.exp(-((xx - 80) ** 2 + (yy - 60) ** 2) / (2 * 1.5 ** 2))
    img = np.repeat((base + star)[..., None], 3, axis=2)
    out = mod.remove_stars(img, window=17, sigma=0.0)[..., 0]
    assert out[60, 80] < base[60, 80] + 25                 # a estrela sumiu
    # a região remendada continua uma rampa suave: sem degraus de platô
    region = out[40:80, 60:100]
    step_x = np.abs(np.diff(region, axis=1)).max()
    step_y = np.abs(np.diff(region, axis=0)).max()
    assert step_x < 3.0 and step_y < 3.0
