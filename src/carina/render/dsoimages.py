"""Imagens de levantamento (DSS) desenhadas sobre o céu, estilo Stellarium.

Usa as imagens Messier/Caldwell embarcadas no instalador. O fundo do céu é
removido subtraindo um nível de base (percentil baixo de cada canal) e o
desenho usa **mistura aditiva**: onde a imagem é preta nada é somado, então
não aparece o retângulo do recorte — só a nebulosa/galáxia.

A camada é opcional e nunca entra no modo mapa para impressão.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Mesmo enquadramento usado ao baixar as imagens (scripts/build_images.py):
# fov = min(6°, max(0,25°, eixo_maior × 2,5))
FOV_FACTOR = 2.5
FOV_MIN_DEG = 0.25
FOV_MAX_DEG = 6.0

MAX_TEXTURES = 96          # teto do cache de GPU (~72 MB em recortes 512²)
MIN_SIZE_PX = 26.0         # abaixo disso o objeto é pequeno demais na tela
SUBMITS_PER_FRAME = 6      # decodificações enfileiradas por quadro (workers)
UPLOADS_PER_FRAME = 3      # texturas enviadas à GPU por quadro (~1 ms cada)


def image_fov_deg(maj_arcmin: float | None) -> float:
    """Campo do recorte em graus para um objeto sem entrada no manifesto
    (mesma fórmula dos scripts de download — precisa continuar igual)."""
    if not maj_arcmin:
        return FOV_MIN_DEG * 2
    return min(FOV_MAX_DEG, max(FOV_MIN_DEG, maj_arcmin * FOV_FACTOR / 60.0))


# Máscaras de desvanecimento radial por tamanho de imagem. Os recortes têm
# poucos tamanhos distintos (512² na maioria), então o cache evita recompor
# a mesma máscara a cada textura carregada.
_FADE_CACHE: dict[tuple[int, int], np.ndarray] = {}


def _radial_fade(h: int, w: int) -> np.ndarray:
    """Máscara de desvanecimento radial (cacheada por tamanho de imagem)."""
    fade = _FADE_CACHE.get((h, w))
    if fade is None:
        yy = (np.arange(h) - (h - 1) / 2.0) / (h / 2.0)
        xx = (np.arange(w) - (w - 1) / 2.0) / (w / 2.0)
        r = np.hypot(yy[:, None], xx[None, :])
        # 1 no centro; cai a zero entre 0,72 e 1,0 do raio (janela suave)
        fade = np.clip((1.0 - r) / 0.28, 0.0, 1.0)
        fade = fade * fade * (3.0 - 2.0 * fade)  # smoothstep
        fade = fade[:, :, None].astype(np.float32)
        if len(_FADE_CACHE) > 8:
            _FADE_CACHE.clear()
        _FADE_CACHE[(h, w)] = fade
    return fade


def prepare_rgb(rgb: np.ndarray, floor_percentile: float = 55.0,
                gain: float = 1.5, knee: float = 200.0) -> np.ndarray:
    """Remove o fundo do céu e realça o objeto, preservando as cores.

    O piso é o percentil do próprio recorte: como o céu ocupa a maior parte
    da área, subtraí-lo zera o fundo e só a nebulosa/galáxia sobra. As bordas
    recebem um desvanecimento radial suave para o recorte não terminar num
    corte reto (é o que denunciaria o retângulo da imagem).

    Desempenho: o percentil é estimado numa subamostra 1:4 em cada eixo
    (1/16 dos pixels). Para uma estatística de fundo isso é indistinguível
    do valor exato e corta o custo de ~40 ms para ~4 ms por imagem — era o
    soluço perceptível ao carregar texturas durante o zoom.
    """
    a = rgb.astype(np.float32)
    sample = a[::4, ::4].reshape(-1, 3)
    base = np.percentile(sample, floor_percentile, axis=0)
    a = np.clip(a - base[None, None, :], 0.0, None) * gain
    a = soft_highlights(a, knee)

    h, w, _ = a.shape
    a *= _radial_fade(h, w)
    return np.clip(a, 0, 255).astype(np.uint8)


def soft_highlights(a: np.ndarray, knee: float = 200.0) -> np.ndarray:
    """Comprime só as altas luzes que estourariam, preservando as cores.

    Depois do ganho, o núcleo de nebulosas brilhantes (M 42, M 8, M 20)
    passava de 255 e virava uma mancha branca sem estrutura (revisão
    2026-10, D9). Abaixo de ``knee`` nada muda; o intervalo
    ``[knee, máximo da imagem]`` é levado a ``[knee, 255]`` por uma curva
    asinh, de modo que o pixel mais brilhante fica exatamente em 255 e o
    gradiente do miolo sobrevive. Imagens que não estouram saem
    intocadas. O fator é calculado na luminância (máximo dos canais) e
    aplicado aos três — o matiz não muda.
    """
    lum = a.max(axis=2, keepdims=True)
    l_max = float(lum.max())
    if l_max <= 255.0:
        return a
    span = l_max - knee
    soft = span / 3.0
    excess = np.clip(lum - knee, 0.0, None)
    compressed = knee + (255.0 - knee) * np.arcsinh(excess / soft) / math.asinh(span / soft)
    with np.errstate(divide="ignore", invalid="ignore"):
        scale = np.where(lum > knee, compressed / lum, 1.0)
    return a * scale.astype(np.float32)
