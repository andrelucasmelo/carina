"""Alinhamento de uma foto do usuário ao céu por duas estrelas (v0.19 T4).

Duas estrelas marcadas na foto e identificadas no catálogo fixam uma
**transformação de similaridade** (escala, rotação e translação; espelho
opcional) entre os pixels da imagem e o **plano tangente** do céu
(projeção gnomônica no ponto médio das duas estrelas). Em números
complexos é uma reta: w = a·z + b, com z = pixel e w = (ξ, η) no plano
tangente — a encode escala e rotação, b a translação.

É o mesmo modelo de quem "resolve" uma foto à mão: vale para campos de
até algumas dezenas de graus (distorção de lentes grande-angulares não é
modelada).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def _basis(t: np.ndarray):
    t = t / np.linalg.norm(t)
    pole = np.array([0.0, 0.0, 1.0])
    n = pole - (pole @ t) * t
    if np.linalg.norm(n) < 1e-9:
        n = np.array([1.0, 0.0, 0.0]) - t[0] * t
    n /= np.linalg.norm(n)
    e = np.cross(pole, t)
    if np.linalg.norm(e) < 1e-9:
        e = np.cross(n, t)
    e /= np.linalg.norm(e)
    return t, e, n


def gnomonic(v: np.ndarray, t: np.ndarray, e: np.ndarray, n: np.ndarray) -> complex:
    """Direção → plano tangente, em radianos: parte real para **oeste**,
    imaginária para norte. Assim uma foto comum (norte em cima, leste à
    esquerda, como o céu visto daqui) é uma similaridade sem espelho."""
    d = float(v @ t)
    return complex(-float(v @ e) / d, float(v @ n) / d)


@dataclass
class PhotoAlignment:
    a: complex
    b: complex
    tangent: np.ndarray = field(repr=False)
    east: np.ndarray = field(repr=False)
    north: np.ndarray = field(repr=False)
    mirror: bool = False

    def _z(self, x, y):
        # pixels: y cresce para baixo; espelho = imagem invertida lateralmente
        z = np.asarray(x, dtype=np.float64) - 1j * np.asarray(y, dtype=np.float64)
        return np.conj(z) if self.mirror else z

    def pixel_to_icrs(self, x, y) -> np.ndarray:
        w = self.a * self._z(x, y) + self.b
        v = (self.tangent[None, :] - np.real(w).reshape(-1, 1) * self.east[None, :]
             + np.imag(w).reshape(-1, 1) * self.north[None, :])
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        return v[0] if np.ndim(x) == 0 else v

    def icrs_to_pixel(self, v: np.ndarray) -> tuple[float, float]:
        w = gnomonic(np.asarray(v, np.float64), self.tangent, self.east, self.north)
        z = (w - self.b) / self.a
        if self.mirror:
            z = np.conj(z)
        return float(z.real), float(-z.imag)

    @property
    def scale_arcsec(self) -> float:
        """Segundos de arco por pixel."""
        return math.degrees(abs(self.a)) * 3600.0

    @property
    def rotation_deg(self) -> float:
        """Ângulo de posição do "para cima" da foto (graus, do norte para leste)."""
        # um passo "para cima" na foto é dz = +i (ou −i, depois do espelho);
        # a parte real de w aponta para oeste, daí o sinal no leste
        up = self.a * (-1j if self.mirror else 1j)
        return math.degrees(math.atan2(-up.real, up.imag)) % 360.0

    def grid(self, width: int, height: int, n: int = 5) -> tuple[np.ndarray, np.ndarray]:
        """Grade n×n de vértices (ICRS) e coordenadas de textura (u, v)."""
        ts = np.linspace(0.0, 1.0, n)
        gu, gv = np.meshgrid(ts, ts)
        xs = gu.ravel() * width
        ys = gv.ravel() * height
        return self.pixel_to_icrs(xs, ys), np.column_stack([gu.ravel(), gv.ravel()])

    def to_dict(self) -> dict:
        return {"a": [self.a.real, self.a.imag], "b": [self.b.real, self.b.imag],
                "tangent": list(map(float, self.tangent)), "mirror": self.mirror}

    @classmethod
    def from_dict(cls, d: dict) -> "PhotoAlignment":
        t, e, n = _basis(np.asarray(d["tangent"], np.float64))
        return cls(complex(*d["a"]), complex(*d["b"]), t, e, n, bool(d.get("mirror")))


def solve(p1: tuple[float, float], p2: tuple[float, float], v1: np.ndarray,
          v2: np.ndarray, mirror: bool = False,
          center: tuple[float, float] | None = None) -> PhotoAlignment:
    """Transformação a partir de dois pares (pixel, direção ICRS).

    ``center``: pixel do centro óptico (o centro da imagem). A foto é uma
    projeção gnomônica em torno dele; a primeira solução usa o ponto médio
    das estrelas e a segunda refaz tudo com o plano tangente no centro.
    """
    v1 = np.asarray(v1, np.float64) / np.linalg.norm(v1)
    v2 = np.asarray(v2, np.float64) / np.linalg.norm(v2)
    first = _solve_at(p1, p2, v1, v2, mirror, v1 + v2)
    if center is None:
        return first
    for _ in range(2):
        first = _solve_at(p1, p2, v1, v2, mirror, first.pixel_to_icrs(*center))
    return first


def _solve_at(p1, p2, v1, v2, mirror, tangent) -> PhotoAlignment:
    t, e, n = _basis(np.asarray(tangent, np.float64))
    w1, w2 = gnomonic(v1, t, e, n), gnomonic(v2, t, e, n)
    z1 = complex(p1[0], -p1[1])
    z2 = complex(p2[0], -p2[1])
    if mirror:
        z1, z2 = z1.conjugate(), z2.conjugate()
    if abs(z2 - z1) < 1e-9:
        raise ValueError("as duas estrelas precisam estar em pontos diferentes da foto")
    a = (w2 - w1) / (z2 - z1)
    b = w1 - a * z1
    return PhotoAlignment(a, b, t, e, n, mirror)
