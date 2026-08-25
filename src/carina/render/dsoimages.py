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
    if not maj_arcmin:
        return FOV_MIN_DEG * 2
    return min(FOV_MAX_DEG, max(FOV_MIN_DEG, maj_arcmin * FOV_FACTOR / 60.0))


# Máscaras de desvanecimento radial por tamanho de imagem. Os recortes têm
# poucos tamanhos distintos (512² na maioria), então o cache evita recompor
# a mesma máscara a cada textura carregada.
_FADE_CACHE: dict[tuple[int, int], np.ndarray] = {}


def _radial_fade(h: int, w: int) -> np.ndarray:
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
                gain: float = 1.5) -> np.ndarray:
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

    h, w, _ = a.shape
    a *= _radial_fade(h, w)
    return np.clip(a, 0, 255).astype(np.uint8)


@dataclass
class _Entry:
    texture: int
    last_used: int


class DsoImageLayer:
    """Cache de texturas das imagens de céu profundo, por nome do objeto."""

    def __init__(self, fov_map: dict[str, float] | None = None) -> None:
        self._entries: dict[str, _Entry] = {}
        self._missing: set[str] = set()
        self._tick = 0
        # campos por objeto do manifesto de destaques (mesmo FOV do download)
        self.fov_map: dict[str, float] = dict(fov_map or {})
        # decodificação assíncrona: o PNG é lido e preparado num worker
        # (o GIL é liberado no I/O e nas ufuncs grandes do NumPy); só o
        # upload da textura — ~1 ms — acontece no quadro de renderização.
        # Sem isso, cada textura nova custava ~45 ms DENTRO do quadro.
        self._pool = None
        self._pending: dict[str, object] = {}   # name -> Future

    def fov_for(self, name: str, maj_arcmin: float | None) -> float:
        return self.fov_map.get(name) or image_fov_deg(maj_arcmin)

    def loading(self) -> bool:
        """Há decodificações em andamento/prontas aguardando upload?

        O SkyWidget usa isto para agendar uma repintura curta: sem ela, as
        imagens só apareceriam no próximo tique do relógio (1 s).
        """
        return bool(self._pending)

    def clear(self, renderer) -> None:
        for entry in self._entries.values():
            renderer.delete_texture(entry.texture)
        self._entries.clear()

    @staticmethod
    def _decode(path: str, floor: float) -> np.ndarray | None:
        """Lê e prepara o RGB de um recorte — roda num worker, fora do quadro."""
        from PySide6.QtGui import QImage

        img = QImage(path)
        if img.isNull():
            return None
        img = img.convertToFormat(QImage.Format_RGB888)
        w, h = img.width(), img.height()
        buf = np.frombuffer(img.constBits(), dtype=np.uint8)
        rgb = buf.reshape(h, img.bytesPerLine())[:, : w * 3].reshape(h, w, 3)
        return prepare_rgb(rgb.copy(), floor_percentile=floor)

    def _texture_for(self, renderer, name: str) -> int | None:
        """Textura do objeto: do cache, ou agenda a decodificação.

        Retorna ``None`` enquanto a imagem ainda não está pronta — o objeto
        simplesmente aparece um ou dois quadros depois, sem travar nada.
        """
        entry = self._entries.get(name)
        if entry is not None:
            entry.last_used = self._tick
            return entry.texture
        if name in self._missing:
            return None

        # decodificação pronta? faz só o upload (barato) e entra no cache
        fut = self._pending.get(name)
        if fut is not None:
            if not fut.done():
                return None
            del self._pending[name]
            rgb = fut.result()
            if rgb is None:
                self._missing.add(name)
                return None
            tex = renderer.create_texture(rgb)
            if len(self._entries) >= MAX_TEXTURES:
                oldest = min(self._entries.items(),
                             key=lambda kv: kv[1].last_used)
                renderer.delete_texture(oldest[1].texture)
                del self._entries[oldest[0]]
            self._entries[name] = _Entry(tex, self._tick)
            return tex

        from ..catalogs import images as image_store

        path = image_store.image_path_for(name)
        if path is None:
            self._missing.add(name)
            return None
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor

            self._pool = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="dsoimg"
            )
        # campos grandes (Nuvens de Magalhães): o objeto ocupa boa parte do
        # recorte, então o piso de fundo precisa ser mais baixo
        fov = self.fov_map.get(name, 0.0)
        floor = 30.0 if fov > 6.0 else 55.0
        self._pending[name] = self._pool.submit(self._decode, str(path), floor)
        return None

    # índices dos triângulos de uma grade 5×5 (fixos — computados uma vez)
    _GRID_N = 5
    _GRID_IDX = None

    @classmethod
    def _grid_indices(cls) -> np.ndarray:
        if cls._GRID_IDX is None:
            n = cls._GRID_N
            idx = []
            for r in range(n - 1):
                for c in range(n - 1):
                    a0 = r * n + c
                    idx += [a0, a0 + 1, a0 + n, a0 + 1, a0 + n + 1, a0 + n]
            cls._GRID_IDX = np.asarray(idx, dtype=np.int64)
        return cls._GRID_IDX

    # ------------------------------------------------------------------
    def draw(self, renderer, camera, project, dso, rows, alpha: float) -> int:
        """Desenha as imagens dos objetos indicados.

        ``rows`` são índices no catálogo; ``project`` é a função de projeção
        do widget (aplica refração e câmera). Devolve quantas foram desenhadas.

        Duas decisões de desempenho:

        * no máximo :data:`LOADS_PER_FRAME` texturas novas são decodificadas
          por quadro — as demais entram nos quadros seguintes. Sem isso, um
          zoom que revela dezenas de imagens travava a interface por
          centenas de ms de uma vez;
        * as grades 5×5 de TODOS os objetos são projetadas numa única
          chamada (o custo fixo de cada chamada pequena de projeção/refração
          dominava o tempo com muitos objetos na tela).
        """
        self._tick += 1
        pole = np.array([0.0, 0.0, 1.0])
        n = self._GRID_N
        tri = self._grid_indices()
        submits_left = SUBMITS_PER_FRAME
        uploads_left = UPLOADS_PER_FRAME

        # 1) resolve texturas respeitando os orçamentos do quadro: novas
        #    decodificações vão para os workers; uploads prontos são caros
        #    o suficiente (~1 ms) para também serem limitados
        chosen: list[tuple[int, int]] = []      # (índice no catálogo, textura)
        for i in rows:
            name = dso.names[i]
            if self._entries.get(name) is None:
                if name in self._missing:
                    continue
                fut = self._pending.get(name)
                if fut is None:
                    if submits_left <= 0:
                        continue
                    submits_left -= 1
                elif fut.done():
                    if uploads_left <= 0:
                        continue
                    uploads_left -= 1
                else:
                    continue                     # worker ainda decodificando
            tex = self._texture_for(renderer, name)
            if tex is not None:
                chosen.append((int(i), tex))
        if not chosen:
            return 0

        # 2) monta todas as grades (M,25,3) por broadcasting
        ts = np.linspace(-1.0, 1.0, n)
        gx, gy = np.meshgrid(ts, ts)
        gxf = gx.ravel()[None, :, None]          # (1,25,1)
        gyf = gy.ravel()[None, :, None]
        uv = np.column_stack([((gx + 1) / 2).ravel(),
                              ((gy + 1) / 2).ravel()])

        sel = np.array([i for i, _ in chosen], dtype=np.int64)
        U = np.asarray(dso.xyz[sel], dtype=np.float64)
        U /= np.linalg.norm(U, axis=1, keepdims=True)
        north = pole[None, :] - U * (U @ pole)[:, None]
        nn = np.linalg.norm(north, axis=1, keepdims=True)
        north = np.where(nn > 1e-6, north / np.maximum(nn, 1e-9),
                         np.array([1.0, 0.0, 0.0])[None, :])
        east = np.cross(np.broadcast_to(pole, U.shape), U)
        east /= np.maximum(np.linalg.norm(east, axis=1, keepdims=True), 1e-9)
        halfs = np.array([
            math.tan(math.radians(
                self.fov_for(dso.names[i], float(dso.maj[i])) / 2.0
            )) for i, _ in chosen
        ])[:, None, None]

        # Convenção do recorte (hips2fits/TAN): norte em cima e LESTE À
        # ESQUERDA — logo a borda esquerda da textura (gx=-1) precisa cair
        # no lado LESTE do céu (sinal negativo no termo leste).
        offs = (
            U[:, None, :]
            - halfs * gxf * east[:, None, :]
            - halfs * gyf * north[:, None, :]
        )
        offs /= np.linalg.norm(offs, axis=2, keepdims=True)

        # 3) UMA projeção para todos os vértices de todas as grades
        x, y, _vis = project(offs.reshape(-1, 3), 1e9)
        screen_all = np.column_stack([x, y]).reshape(len(chosen), n * n, 2)

        # 4) um draw call por textura (inevitável), com dados já prontos
        drawn = 0
        max_span = 40.0 * max(camera.width, camera.height)
        for k, (_i, tex) in enumerate(chosen):
            screen = screen_all[k]
            span = np.hypot(
                screen[:, 0].max() - screen[:, 0].min(),
                screen[:, 1].max() - screen[:, 1].min(),
            )
            # pequeno demais não aparece; grande demais é a grade quebrada
            # atravessando o polo da projeção (descarta para não riscar a tela)
            if span < MIN_SIZE_PX or span > max_span:
                continue
            renderer.draw_textured_triangles(
                screen[tri], uv[tri], alpha, texture=tex, additive=True
            )
            drawn += 1
        return drawn
