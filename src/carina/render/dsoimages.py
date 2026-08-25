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

MAX_TEXTURES = 40          # teto do cache de GPU
MIN_SIZE_PX = 26.0         # abaixo disso o objeto é pequeno demais na tela


def image_fov_deg(maj_arcmin: float | None) -> float:
    if not maj_arcmin:
        return FOV_MIN_DEG * 2
    return min(FOV_MAX_DEG, max(FOV_MIN_DEG, maj_arcmin * FOV_FACTOR / 60.0))


def prepare_rgb(rgb: np.ndarray, floor_percentile: float = 55.0,
                gain: float = 1.5) -> np.ndarray:
    """Remove o fundo do céu e realça o objeto, preservando as cores.

    O piso é o percentil do próprio recorte: como o céu ocupa a maior parte
    da área, subtraí-lo zera o fundo e só a nebulosa/galáxia sobra. As bordas
    recebem um desvanecimento radial suave para o recorte não terminar num
    corte reto (é o que denunciaria o retângulo da imagem).
    """
    a = rgb.astype(np.float32)
    base = np.percentile(a.reshape(-1, 3), floor_percentile, axis=0)
    a = np.clip(a - base[None, None, :], 0.0, None) * gain

    h, w, _ = a.shape
    yy = (np.arange(h) - (h - 1) / 2.0) / (h / 2.0)
    xx = (np.arange(w) - (w - 1) / 2.0) / (w / 2.0)
    r = np.hypot(yy[:, None], xx[None, :])
    # 1 no centro; cai a zero entre 0,72 e 1,0 do raio (janela suave)
    fade = np.clip((1.0 - r) / 0.28, 0.0, 1.0)
    fade = fade * fade * (3.0 - 2.0 * fade)      # smoothstep
    a *= fade[:, :, None]
    return np.clip(a, 0, 255).astype(np.uint8)


@dataclass
class _Entry:
    texture: int
    last_used: int


class DsoImageLayer:
    """Cache de texturas das imagens de céu profundo, por nome do objeto."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._missing: set[str] = set()
        self._tick = 0

    def clear(self, renderer) -> None:
        for entry in self._entries.values():
            renderer.delete_texture(entry.texture)
        self._entries.clear()

    def _texture_for(self, renderer, name: str) -> int | None:
        entry = self._entries.get(name)
        if entry is not None:
            entry.last_used = self._tick
            return entry.texture
        if name in self._missing:
            return None

        from PySide6.QtGui import QImage

        from ..catalogs import images as image_store

        path = image_store.image_path_for(name)
        if path is None:
            self._missing.add(name)
            return None
        img = QImage(str(path))
        if img.isNull():
            self._missing.add(name)
            return None
        img = img.convertToFormat(QImage.Format_RGB888)
        w, h = img.width(), img.height()
        buf = np.frombuffer(img.constBits(), dtype=np.uint8)
        rgb = buf.reshape(h, img.bytesPerLine())[:, : w * 3].reshape(h, w, 3)
        tex = renderer.create_texture(prepare_rgb(rgb.copy()))

        if len(self._entries) >= MAX_TEXTURES:
            oldest = min(self._entries.items(), key=lambda kv: kv[1].last_used)
            renderer.delete_texture(oldest[1].texture)
            del self._entries[oldest[0]]
        self._entries[name] = _Entry(tex, self._tick)
        return tex

    # ------------------------------------------------------------------
    def draw(self, renderer, camera, project, dso, rows, alpha: float) -> int:
        """Desenha as imagens dos objetos indicados.

        ``rows`` são índices no catálogo; ``project`` é a função de projeção
        do widget (aplica refração e câmera). Devolve quantas foram desenhadas.
        """
        self._tick += 1
        drawn = 0
        pole = np.array([0.0, 0.0, 1.0])
        for i in rows:
            name = dso.names[i]
            tex = self._texture_for(renderer, name)
            if tex is None:
                continue
            half = math.radians(image_fov_deg(float(dso.maj[i])) / 2.0)
            u = np.asarray(dso.xyz[i], dtype=np.float64)
            u /= np.linalg.norm(u)
            north = pole - np.dot(pole, u) * u
            if np.linalg.norm(north) < 1e-6:
                north = np.array([1.0, 0.0, 0.0])
            north /= np.linalg.norm(north)
            east = np.cross(pole, u)
            east /= max(np.linalg.norm(east), 1e-9)

            # grade 5×5 para acompanhar a curvatura da projeção
            n = 5
            ts = np.linspace(-1.0, 1.0, n)
            gx, gy = np.meshgrid(ts, ts)
            offs = (
                u[None, None, :]
                + np.tan(half) * gx[..., None] * east[None, None, :]
                - np.tan(half) * gy[..., None] * north[None, None, :]
            )
            offs /= np.linalg.norm(offs, axis=2, keepdims=True)
            pts = offs.reshape(-1, 3)
            x, y, _vis = project(pts, 1e9)
            screen = np.column_stack([x, y])
            uv = np.column_stack([
                ((gx + 1) / 2).ravel(), ((gy + 1) / 2).ravel(),
            ])

            idx = []
            for r in range(n - 1):
                for c in range(n - 1):
                    a0 = r * n + c
                    idx += [a0, a0 + 1, a0 + n, a0 + 1, a0 + n + 1, a0 + n]
            idx = np.asarray(idx, dtype=np.int64)
            span = np.hypot(
                screen[idx, 0].max() - screen[idx, 0].min(),
                screen[idx, 1].max() - screen[idx, 1].min(),
            )
            if span < MIN_SIZE_PX or span > 40.0 * max(camera.width,
                                                       camera.height):
                continue
            renderer.draw_textured_triangles(
                screen[idx], uv[idx], alpha, texture=tex, additive=True
            )
            drawn += 1
        return drawn
