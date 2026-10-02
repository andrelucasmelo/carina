"""Imagens de levantamento: compressão suave das altas luzes (D9)."""

import numpy as np

from carina.render.dsoimages import prepare_rgb, soft_highlights


def _synthetic(peak: float) -> np.ndarray:
    """Fundo uniforme (40) com um núcleo gaussiano de pico ``peak``."""
    yy, xx = np.mgrid[0:64, 0:64]
    r2 = (yy - 32) ** 2 + (xx - 32) ** 2
    core = peak * np.exp(-r2 / 60.0)
    img = np.stack([40 + core, 40 + 0.8 * core, 40 + 0.6 * core], axis=2)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_bright_core_is_not_a_flat_white_blob():
    out = prepare_rgb(_synthetic(215.0))
    centre = out[28:36, 28:36, 0].astype(int)
    assert out.max() <= 255
    # gradiente preservado: o pixel central é mais brilhante que a borda do
    # miolo e os valores não colapsam num platô de 255
    assert centre[4, 4] > centre[0, 0] + 8
    assert (out[:, :, 0] == 255).sum() < 10


def test_faint_image_is_barely_changed():
    a = np.full((8, 8, 3), 60.0, dtype=np.float32)
    out = soft_highlights(a)
    assert np.allclose(out, a, rtol=0.0, atol=10.0)


def test_hue_is_preserved():
    a = np.zeros((4, 4, 3), dtype=np.float32)
    a[..., 0], a[..., 1], a[..., 2] = 600.0, 300.0, 150.0   # bem acima de 255
    out = soft_highlights(a)
    ratio = out[0, 0] / out[0, 0, 0]
    assert np.allclose(ratio, [1.0, 0.5, 0.25], atol=1e-5)
    assert abs(out[0, 0, 0] - 255.0) < 1e-3
