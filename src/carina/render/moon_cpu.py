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
    h, w, _ = tex.shape
    x = u * w - 0.5
    y = np.clip(v * h - 0.5, 0, h - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]
    x0 %= w
    x1 = (x0 + 1) % w
    y1 = np.minimum(y0 + 1, h - 1)
    t = tex.astype(np.float32) if tex.dtype != np.float32 else tex
    c00 = t[y0, x0]
    c10 = t[y0, x1]
    c01 = t[y1, x0]
    c11 = t[y1, x1]
    return (c00 * (1 - fx) + c10 * fx) * (1 - fy) + (c01 * (1 - fx) + c11 * fx) * fy


def render(view: MoonView, v2b: np.ndarray, sun_body: np.ndarray,
           obs_body: np.ndarray, color: np.ndarray, normal: np.ndarray,
           illumination: float = 0.5, gain: float = 1.9, relief: float = 1.0,
           background=(8, 10, 16)) -> np.ndarray:
    """Imagem RGB uint8 (altura, largura, 3) da Lua na vista dada."""
    w, h = int(view.width), int(view.height)
    img = np.empty((h, w, 3), dtype=np.uint8)
    img[:] = background
    ys, xs = np.mgrid[0:h, 0:w]
    a, b = view.to_local(xs.ravel() + 0.5, ys.ravel() + 0.5)
    r2 = a * a + b * b
    inside = r2 < 1.0
    if not inside.any():
        return img
    a, b, r2 = a[inside], b[inside], r2[inside]
    c = np.sqrt(1.0 - r2)
    p = (v2b @ np.stack([a, b, c])).T                       # (N, 3) MOON_ME
    p /= np.linalg.norm(p, axis=1, keepdims=True)
    lon = np.arctan2(p[:, 1], p[:, 0])
    lat = np.arcsin(np.clip(p[:, 2], -1, 1))
    u = lon / (2 * np.pi) + 0.5
    v = 0.5 - lat / np.pi
    albedo = _bilinear(color, u, v) / 255.0
    ni = _bilinear(normal, u, v) / 127.5 - 1.0
    east = np.stack([-p[:, 1], p[:, 0], np.zeros(len(p))], axis=1)
    le = np.linalg.norm(east, axis=1, keepdims=True)
    east = np.where(le > 1e-5, east / np.maximum(le, 1e-12), [0.0, 1.0, 0.0])
    north = np.cross(p, east)
    n = ni[:, :1] * east + ni[:, 1:2] * north + ni[:, 2:3] * p
    n = p + (n - p) * relief
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    mu0 = np.maximum(n @ sun_body, 0.0)
    mu = np.maximum(n @ obs_body, 0.05)
    geo_dot = p @ sun_body
    geo = np.clip((geo_dot + 0.015) / 0.035, 0.0, 1.0)
    geo = geo * geo * (3 - 2 * geo)
    lit = np.minimum(2.0 * mu0 / (mu0 + mu), 1.25) * geo
    earthshine = 0.015 + 0.22 * (1.0 - illumination) ** 3
    col = albedo * (lit * gain + earthshine * (1.0 - geo))[:, None]
    # limbo suave
    edge = 1.0 - np.clip((r2 - 0.985) / 0.015, 0.0, 1.0)
    bg = np.asarray(background, dtype=np.float32) / 255.0
    col = col * edge[:, None] + bg * (1.0 - edge[:, None])
    flat = img.reshape(-1, 3)
    flat[np.nonzero(inside)[0]] = np.clip(col * 255.0, 0, 255).astype(np.uint8)
    return img
