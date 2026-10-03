"""Texturas da Lua (v0.17): leitura dos JPEG embarcados como arrays.

Usadas pela esfera lunar do céu (GPU) e pela :class:`MoonWindow`, que
desenha na CPU. A leitura é feita uma vez e fica em memória (cor 8k ≈
100 MB; a janela usa a versão reduzida por padrão).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np


def qimage_rgb(path) -> np.ndarray | None:
    from PySide6.QtGui import QImage

    img = QImage(str(path))
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, img.bytesPerLine())
    return buf[:, : w * 3].reshape(h, w, 3).copy()


@lru_cache(maxsize=2)
def moon_arrays(reduce: int = 1) -> tuple[np.ndarray, np.ndarray] | None:
    """(cor, normais) como arrays uint8 (H, W, 3); ``reduce`` = passo de
    amostragem (2 → 4096 px na cor)."""
    from ..core.moon import data_dir

    d = data_dir()
    color = qimage_rgb(d / "moon_color.jpg")
    normal = qimage_rgb(d / "moon_normal.jpg")
    if color is None or normal is None:
        return None
    if reduce > 1:
        color = np.ascontiguousarray(color[::reduce, ::reduce])
        while normal.shape[1] > color.shape[1]:
            normal = np.ascontiguousarray(normal[::2, ::2])
    return color, normal


def available() -> bool:
    from ..core.moon import data_dir, kernels_available

    d = data_dir()
    return kernels_available() and (d / "moon_color.jpg").exists() and \
        (d / "moon_normal.jpg").exists()
