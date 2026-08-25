"""Câmera e projeção estereográfica (a mesma projeção padrão do Stellarium).

Convenção do frame horizontal (topocêntrico): x = norte, y = leste, z = zênite.
Direção a partir de (az, alt), com azimute contado do norte para o leste:

    v = [cos(alt)·cos(az), cos(alt)·sin(az), sin(alt)]

A projeção é feita em torno do centro da câmera: um ponto a um ângulo θ do
centro cai no raio r = 2·tan(θ/2) do plano tangente, que é então escalado para
pixels a partir do campo de visão vertical.
"""

from __future__ import annotations

import math

import numpy as np

# Limites de campo de visão (radianos)
FOV_MIN = math.radians(0.25)
FOV_MAX = math.radians(100.0)   # limite de zoom out (pedido do usuário)


def altaz_to_vec(az: float, alt: float) -> np.ndarray:
    ca = math.cos(alt)
    return np.array([ca * math.cos(az), ca * math.sin(az), math.sin(alt)])


def vec_to_altaz(v: np.ndarray) -> tuple[float, float]:
    alt = math.asin(max(-1.0, min(1.0, float(v[2]))))
    az = math.atan2(float(v[1]), float(v[0])) % (2.0 * math.pi)
    return az, alt


class Camera:
    """Estado de visualização: direção do centro, campo de visão e viewport."""

    def __init__(self, az: float = 0.0, alt: float = math.radians(25.0),
                 fov: float = math.radians(90.0)) -> None:
        self.az = az
        self.alt = alt
        self.fov = fov          # campo de visão vertical, radianos
        self.width = 800
        self.height = 600
        self._update_basis()

    # -- estado ----------------------------------------------------------
    def set_viewport(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)

    def set_direction(self, az: float, alt: float) -> None:
        self.az = az % (2.0 * math.pi)
        self.alt = max(-math.pi / 2, min(math.pi / 2, alt))
        self._update_basis()

    def zoom(self, factor: float) -> None:
        self.fov = max(FOV_MIN, min(FOV_MAX, self.fov * factor))

    def _update_basis(self) -> None:
        f = altaz_to_vec(self.az, self.alt)
        # "direita" no céu: perpendicular ao forward e ao zênite; degenera no
        # zênite, então usamos a direção do azimute como referência.
        if abs(self.alt) > math.radians(89.9):
            r = altaz_to_vec(self.az + math.pi / 2, 0.0)
        else:
            r = np.cross(f, np.array([0.0, 0.0, 1.0]))
            r = -r / np.linalg.norm(r)
            # cross(f, up) aponta para a esquerda quando az cresce para leste;
            # negamos para "direita da tela" = leste ao olhar para o norte.
        u = np.cross(f, r)
        self._basis = np.stack([r, u, f])  # 3x3: linhas = right, up, forward

    # -- escala ----------------------------------------------------------
    @property
    def pixel_scale(self) -> float:
        """Pixels por unidade do plano estereográfico."""
        r_edge = 2.0 * math.tan(self.fov / 4.0)
        return (self.height / 2.0) / r_edge

    # -- projeção vetorizada ---------------------------------------------
    def project(self, vecs: np.ndarray, margin: float = 64.0):
        """Projeta vetores unitários (N,3) do frame horizontal para pixels.

        Retorna (x, y, visible): coordenadas em pixels e máscara booleana dos
        pontos dentro do viewport (com margem) e à frente do observador.
        """
        v = vecs @ self._basis.T           # (N,3) -> componentes right/up/forward
        zv = v[:, 2]
        denom = 1.0 + zv
        safe = denom > 1e-6
        k = np.where(safe, 2.0 / np.where(safe, denom, 1.0), 0.0)
        scale = self.pixel_scale
        x = self.width / 2.0 + v[:, 0] * k * scale
        y = self.height / 2.0 - v[:, 1] * k * scale
        visible = (
            safe
            & (zv > -0.5)
            & (x >= -margin) & (x <= self.width + margin)
            & (y >= -margin) & (y <= self.height + margin)
        )
        return x, y, visible

    def project_clamped(self, vecs: np.ndarray, r_max_px: float | None = None):
        """Como project(), mas nunca descarta pontos: direções atrás do
        observador são projetadas num raio grande e finito. Usado para
        preencher polígonos (Via Láctea, solo) sem buracos topológicos.
        """
        if r_max_px is None:
            r_max_px = 4.0 * max(self.width, self.height)
        v = vecs @ self._basis.T
        zv = v[:, 2]
        t = np.hypot(v[:, 0], v[:, 1])
        t = np.where(t < 1e-9, 1e-9, t)
        scale = self.pixel_scale
        with np.errstate(divide="ignore", invalid="ignore"):
            r = 2.0 * np.sin(np.arccos(np.clip(zv, -1, 1)) / 2.0) / np.cos(
                np.arccos(np.clip(zv, -1, 1)) / 2.0
            )
        r_px = np.minimum(r * scale, r_max_px)
        x = self.width / 2.0 + v[:, 0] / t * r_px
        y = self.height / 2.0 - v[:, 1] / t * r_px
        return x, y

    def forward_component(self, vecs: np.ndarray) -> np.ndarray:
        """Componente dos vetores ao longo da direção de visada (cos θ)."""
        return vecs @ self._basis[2]

    def unproject(self, sx: float, sy: float) -> np.ndarray:
        """Pixel -> vetor unitário no frame horizontal."""
        scale = self.pixel_scale
        px = (sx - self.width / 2.0) / scale
        py = (self.height / 2.0 - sy) / scale
        r2 = px * px + py * py
        cos_t = (4.0 - r2) / (4.0 + r2)
        k = 4.0 / (4.0 + r2)
        right, up, fwd = self._basis
        v = cos_t * fwd + k * (px * right + py * up)
        return v / np.linalg.norm(v)

    def screen_to_altaz(self, sx: float, sy: float) -> tuple[float, float]:
        return vec_to_altaz(self.unproject(sx, sy))
