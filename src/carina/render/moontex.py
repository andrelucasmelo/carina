"""Texturas da Lua (v0.17): leitura dos JPEG embarcados como arrays.

Dois consumidores, com necessidades diferentes:

- a esfera do céu (GPU) lê **uma vez**, numa thread em segundo plano
  (:func:`load_for_gpu`), sobe para a placa e descarta a cópia na memória;
- a :class:`MoonWindow` (CPU) usa uma **pirâmide** de resoluções
  (:func:`level`): 8192, 4096, 2048 e 1024 px na cor. Cada desenho escolhe
  o nível com cerca de um texel por pixel — mais rápido e sem serrilhado
  com a Lua inteira na janela. Os níveis são criados sob demanda.
"""

from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

COLOR_WIDTHS = (8192, 4096, 2048, 1024)
_lock = threading.Lock()


def qimage_rgb(path, width: int | None = None) -> np.ndarray | None:
    """JPEG → array RGB. Com ``width``, decodifica já reduzido (o
    decodificador JPEG escala na transformada: 8k → 2k em ~40 ms)."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage, QImageReader

    reader = QImageReader(str(path))
    if width is not None:
        size = reader.size()
        if size.isValid() and size.width() > width:
            reader.setScaledSize(QSize(width, max(1, size.height() * width // size.width())))
    img = reader.read()
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, img.bytesPerLine())
    return buf[:, : w * 3].reshape(h, w, 3).copy()


def _paths():
    from ..core.moon import data_dir

    d = data_dir()
    return d / "moon_color.jpg", d / "moon_normal.jpg"


def load_for_gpu() -> tuple[np.ndarray, np.ndarray] | None:
    """(cor, normais) em resolução cheia, sem cache — o chamador sobe para
    a GPU e solta os arrays. Seguro em thread (QImage não é widget)."""
    color_path, normal_path = _paths()
    color = qimage_rgb(color_path)
    normal = qimage_rgb(normal_path)
    if color is None or normal is None:
        return None
    return color, normal


def _halve(arr: np.ndarray) -> np.ndarray:
    """Reduz pela metade com média 2×2 (filtro de caixa)."""
    h, w = arr.shape[0] // 2 * 2, arr.shape[1] // 2 * 2
    a = arr[:h, :w].astype(np.uint16)
    out = (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2] + 2) // 4
    return out.astype(np.uint8)


def mip_chain(arr: np.ndarray, min_width: int = 16) -> list[np.ndarray]:
    """Cadeia de mipmaps (cada nível pela metade, média 2×2)."""
    out = [arr]
    while out[-1].shape[1] > min_width and out[-1].shape[0] > 1:
        out.append(_halve(out[-1]))
    return out


def gpu_upload_plan() -> list[tuple[str, list[np.ndarray]]] | None:
    """Etapas de envio à GPU, da mais barata à mais cara.

    1. prévia: cor de 2k e normais de 2k (≈10 ms) — o globo aparece já;
    2. normais completas (4k);
    3. cor completa (8k), sem ``glGenerateMipmap``.

    Tudo (decodificação e mipmaps) roda na thread de quem chama.
    """
    arrays = load_for_gpu()
    if arrays is None:
        return None
    color, normal = arrays
    # a cor de 8k fica de fora: só é lida quando a Lua passa de ~1100 px
    # de raio (load_color_full); até lá a de 4k sobra
    cchain = mip_chain(_halve(color) if color.shape[1] > 4096 else color)
    del color
    nchain = mip_chain(normal)
    preview_c = next(i for i, lv in enumerate(cchain) if lv.shape[1] <= 2048)
    preview_n = next(i for i, lv in enumerate(nchain) if lv.shape[1] <= 2048)
    return [("color", cchain[preview_c:]), ("normal", nchain[preview_n:]),
            ("normal", nchain), ("color", cchain)]


def load_color_full() -> list[np.ndarray] | None:
    """Cadeia completa da cor (8192 px no nível 0), para o zoom extremo."""
    color = qimage_rgb(_paths()[0])
    if color is None:
        return None
    return mip_chain(color)


@lru_cache(maxsize=1)
def _base() -> tuple[np.ndarray, np.ndarray] | None:
    return load_for_gpu()


_levels: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def level(index: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Nível ``index`` da pirâmide (0 = 8192 px … 3 = 1024 px).

    As normais acompanham até a metade da largura da cor (4096 px no
    máximo, a resolução da fonte).
    """
    index = max(0, min(index, len(COLOR_WIDTHS) - 1))
    with _lock:
        if index in _levels:
            return _levels[index]
        if index == 0:
            base = _base()
            if base is None:
                return None
            _levels[0] = base
            return base
    width = COLOR_WIDTHS[index]
    color_path, normal_path = _paths()
    color = qimage_rgb(color_path, width)
    normal = qimage_rgb(normal_path, max(width // 2, 1024))
    if color is None or normal is None:
        return None
    with _lock:
        _levels[index] = (color, normal)
    return _levels[index]


def level_for(texels_needed: float) -> int:
    """Nível cuja largura da cor cobre ``texels_needed`` (no equador)."""
    for i in range(len(COLOR_WIDTHS) - 1, -1, -1):
        if COLOR_WIDTHS[i] >= texels_needed:
            return i
    return 0


def release_cpu_levels() -> None:
    """Solta a pirâmide da CPU (chamado ao fechar a Janela da Lua)."""
    with _lock:
        _levels.clear()
    _base.cache_clear()


def moon_arrays(reduce: int = 1) -> tuple[np.ndarray, np.ndarray] | None:
    """Compatibilidade: ``reduce`` 1, 2, 4 ou 8 → nível da pirâmide."""
    return level({1: 0, 2: 1, 4: 2, 8: 3}.get(int(reduce), 0))


def available() -> bool:
    from ..core.moon import kernels_available

    color_path, normal_path = _paths()
    return kernels_available() and color_path.exists() and normal_path.exists()
