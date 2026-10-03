"""Desenho da Lua na CPU (v0.17): a vista da :class:`MoonWindow`.

Mesmo modelo da esfera do céu (shader ``_MOON_FS``), em numpy: para cada
pixel, o ponto local (a, b) do disco vira um ponto da esfera, que é levado
ao referencial MOON_ME, amostrado nas texturas e sombreado pela direção do
Sol. Fica na CPU para a janela funcionar em qualquer placa e para os
testes rodarem sem OpenGL; ~0,1 s por quadro de 700×700.

A transformação de tela é explícita (:class:`MoonView`): leste celeste à
esquerda e norte em cima, depois espelho (diagonal) e rotação — o mesmo
caminho serve para desenhar os rótulos e para achar a formação clicada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class MoonView:
    width: int
    height: int
    zoom: float = 1.0          # 1 = disco inteiro com margem
    pan_a: float = 0.0         # centro da vista em coordenadas locais
    pan_b: float = 0.0
    rotation: float = 0.0      # graus, anti-horário na tela
    mirror: bool = False       # imagem espelhada (refrator com diagonal)

    @property
    def scale(self) -> float:
        """Pixels por unidade de raio lunar."""
        return self.zoom * min(self.width, self.height) * 0.46

    def to_screen(self, a, b):
        """(a, b) locais → (x, y) em pixels."""
        a = np.asarray(a, dtype=np.float64) - self.pan_a
        b = np.asarray(b, dtype=np.float64) - self.pan_b
        x, y = -a, -b                     # leste à esquerda, norte em cima
        if self.mirror:
            x = -x
        th = math.radians(self.rotation)
        # rotação anti-horária na tela (y para baixo)
        xr = x * math.cos(th) + y * math.sin(th)
        yr = -x * math.sin(th) + y * math.cos(th)
        return self.width / 2.0 + xr * self.scale, self.height / 2.0 + yr * self.scale

    def to_local(self, x, y):
        """(x, y) em pixels → (a, b) locais (inversa de :meth:`to_screen`)."""
        xr = (np.asarray(x, dtype=np.float64) - self.width / 2.0) / self.scale
        yr = (np.asarray(y, dtype=np.float64) - self.height / 2.0) / self.scale
        th = math.radians(self.rotation)
        xx = xr * math.cos(th) - yr * math.sin(th)
        yy = xr * math.sin(th) + yr * math.cos(th)
        if self.mirror:
            xx = -xx
        return -xx + self.pan_a, -yy + self.pan_b


def _bilinear(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Interpolação bilinear só nos texels amostrados (float32).

    Converter a textura inteira para ponto flutuante a cada quadro — 400 MB
    na cor de 8k — era 75% do tempo do desenho.
    """
    h, w, _ = tex.shape
    x = u * np.float32(w) - np.float32(0.5)
    y = np.clip(v * np.float32(h) - np.float32(0.5), 0, h - 1.001)
    x0f = np.floor(x)
    y0f = np.floor(y)
    fx = (x - x0f)[:, None]
    fy = (y - y0f)[:, None]
    x0 = x0f.astype(np.int64) % w
    y0 = y0f.astype(np.int64)
    x1 = x0 + 1
    x1[x1 == w] = 0
    y1 = np.minimum(y0 + 1, h - 1)
    top = tex[y0, x0].astype(np.float32)
    top += (tex[y0, x1].astype(np.float32) - top) * fx
    bot = tex[y1, x0].astype(np.float32)
    bot += (tex[y1, x1].astype(np.float32) - bot) * fx
    return top + (bot - top) * fy


def texture_width_for(view: "MoonView") -> float:
    """Largura de textura com ~1 texel por pixel no centro do disco."""
    return 2.0 * np.pi * view.scale


def render(view: MoonView, v2b: np.ndarray, sun_body: np.ndarray,
           obs_body: np.ndarray, color: np.ndarray, normal: np.ndarray,
           illumination: float = 0.5, gain: float = 1.9, relief: float = 1.0,
           background=(8, 10, 16)) -> np.ndarray:
    """Imagem RGB uint8 (altura, largura, 3) da Lua na vista dada.

    Só os pixels da caixa que contém o disco (recortada à tela) são
    calculados — com zoom alto é a tela inteira, com a Lua inteira na
    janela é menos da metade.
    """
    w, h = int(view.width), int(view.height)
    img = np.empty((h, w, 3), dtype=np.uint8)
    img[:] = background
    cx, cy = view.to_screen(0.0, 0.0)
    r = view.scale * 1.01
    x0, x1 = max(0, int(cx - r)), min(w, int(cx + r) + 2)
    y0, y1 = max(0, int(cy - r)), min(h, int(cy + r) + 2)
    if x0 >= x1 or y0 >= y1:
        return img
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    a, b = view.to_local(xs.ravel() + 0.5, ys.ravel() + 0.5)
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    r2 = a * a + b * b
    inside = r2 < 1.0
    if not inside.any():
        return img
    a, b, r2 = a[inside], b[inside], r2[inside]
    c = np.sqrt(1.0 - r2)
    m = np.asarray(v2b, dtype=np.float32)
    p = np.stack([a, b, c], axis=1) @ m.T                   # (N, 3) MOON_ME
    p /= np.linalg.norm(p, axis=1, keepdims=True)
    lon = np.arctan2(p[:, 1], p[:, 0])
    lat = np.arcsin(np.clip(p[:, 2], -1, 1))
    u = lon * np.float32(1 / (2 * np.pi)) + np.float32(0.5)
    v = np.float32(0.5) - lat * np.float32(1 / np.pi)
    albedo = _bilinear(color, u, v)
    albedo *= np.float32(1 / 255.0)
    ni = _bilinear(normal, u, v)
    ni *= np.float32(1 / 127.5)
    ni -= np.float32(1.0)
    le = np.sqrt(p[:, 0] ** 2 + p[:, 1] ** 2)
    le = np.maximum(le, np.float32(1e-5))
    ex, ey = -p[:, 1] / le, p[:, 0] / le                   # leste (z = 0)
    # norte = p × leste
    nx = -p[:, 2] * ey
    ny = p[:, 2] * ex
    nz = p[:, 0] * ey - p[:, 1] * ex
    n = np.empty_like(p)
    n[:, 0] = ni[:, 0] * ex + ni[:, 1] * nx + ni[:, 2] * p[:, 0]
    n[:, 1] = ni[:, 0] * ey + ni[:, 1] * ny + ni[:, 2] * p[:, 1]
    n[:, 2] = ni[:, 1] * nz + ni[:, 2] * p[:, 2]
    if relief != 1.0:
        n = p + (n - p) * np.float32(relief)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    sun = np.asarray(sun_body, dtype=np.float32)
    obs = np.asarray(obs_body, dtype=np.float32)
    mu0 = np.maximum(n @ sun, 0.0)
    mu = np.maximum(n @ obs, 0.05)
    geo = np.clip((p @ sun + np.float32(0.015)) / np.float32(0.035), 0.0, 1.0)
    geo = geo * geo * (3 - 2 * geo)
    lit = np.minimum(2.0 * mu0 / (mu0 + mu), 1.25) * geo
    earthshine = np.float32(0.015 + 0.22 * (1.0 - illumination) ** 3)
    col = albedo * (lit * np.float32(gain) + earthshine * (1.0 - geo))[:, None]
    # limbo suave
    edge = (1.0 - np.clip((r2 - 0.985) / 0.015, 0.0, 1.0))[:, None]
    bg = np.asarray(background, dtype=np.float32) / 255.0
    col = col * edge + bg * (1.0 - edge)
    sub = img[y0:y1, x0:x1].reshape(-1, 3)
    sub[np.nonzero(inside)[0]] = np.clip(col * 255.0, 0, 255).astype(np.uint8)
    img[y0:y1, x0:x1] = sub.reshape(y1 - y0, x1 - x0, 3)
    return img
