"""Gera a textura da Via Láctea (mecanismo do Stellarium: textura na esfera).

Fonte: panorâmica ESO/S. Brunier (eso0932a, CC BY 4.0 — crédito obrigatório),
equirretangular em coordenadas GALÁCTICAS com o centro galáctico no meio e
longitude crescendo para a ESQUERDA (convenção de mapas celestes).

Saída: data/processed/milkyway_tex.jpg — equirretangular em coordenadas
EQUATORIAIS J2000 (AR 0..24h da esquerda p/ direita? NÃO: u cresce com AR;
o renderizador usa u = AR/2π, v = (90°−Dec)/180°).

Uso:
    python scripts/build_mwtex.py [--size 4096x2048] [--flip]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "eso0932a.jpg"
OUT = ROOT / "data" / "processed" / "milkyway_tex.jpg"

# Matriz ICRS(J2000) -> galáctico (linhas = eixos galácticos em ICRS).
ICRS_TO_GAL = np.array([
    [-0.0548755604, -0.8734370902, -0.4838350155],
    [+0.4941094279, -0.4448296300, +0.7469822445],
    [-0.8676661490, -0.1980763734, +0.4559837762],
])


def qimage_to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, img.bytesPerLine())
    return arr[:, : w * 3].reshape(h, w, 3).copy()


def array_to_qimage(arr: np.ndarray) -> QImage:
    h, w, _ = arr.shape
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    img = QImage(arr.data, w, h, w * 3, QImage.Format_RGB888)
    return img.copy()  # desacopla do buffer numpy


def _rank_filter(a: np.ndarray, k: int, op) -> np.ndarray:
    """Mínimo/máximo local separável (janela k×k).

    Longitude é periódica (roll); latitude usa roll também — aceitável aqui
    porque as bordas polares da textura são regiões escuras e uniformes.
    """
    r = k // 2
    out = a
    for axis in (1, 0):
        acc = out
        for s in range(1, r + 1):
            acc = op(acc, np.roll(out, s, axis=axis))
            acc = op(acc, np.roll(out, -s, axis=axis))
        out = acc
    return out


def _min_filter(a: np.ndarray, k: int) -> np.ndarray:
    return _rank_filter(a, k, np.minimum)


def _max_filter(a: np.ndarray, k: int) -> np.ndarray:
    return _rank_filter(a, k, np.maximum)


def _box_blur(a: np.ndarray, radius: int) -> np.ndarray:
    """Box blur separável via soma acumulada (wrap em X, clamp em Y)."""
    if radius < 1:
        return a
    k = 2 * radius + 1
    # eixo X (longitude): periódico
    pad = np.concatenate([a[:, -radius:], a, a[:, :radius]], axis=1)
    cs = np.cumsum(pad, axis=1, dtype=np.float32)
    cs = np.concatenate([np.zeros((a.shape[0], 1, a.shape[2]), np.float32), cs],
                        axis=1)
    a = (cs[:, k:, :] - cs[:, :-k, :]) / k
    # eixo Y (latitude): replica as bordas
    pad = np.concatenate(
        [np.repeat(a[:1], radius, axis=0), a,
         np.repeat(a[-1:], radius, axis=0)], axis=0
    )
    cs = np.cumsum(pad, axis=0, dtype=np.float32)
    cs = np.concatenate([np.zeros((1, a.shape[1], a.shape[2]), np.float32), cs],
                        axis=0)
    return (cs[k:, :, :] - cs[:-k, :, :]) / k


def gaussian_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussiano aproximado por três box blurs (teorema do limite central)."""
    radius = max(1, int(round(sigma * 3 / 2)))
    out = a.astype(np.float32)
    for _ in range(3):
        out = _box_blur(out, radius)
    return out


def remove_stars(rgb: np.ndarray, window: int = 17,
                 sigma: float = 0.9) -> np.ndarray:
    """Remove fontes pontuais (estrelas do levantamento) preservando o difuso.

    Em vez de aplicar a abertura morfológica na imagem inteira (que borrava
    toda a estrutura — reclamação do usuário), ela é usada apenas para
    DETECTAR os pixels estelares: onde o original excede o fundo aberto, o
    pixel é substituído pelo fundo suavizado; todo o resto mantém o detalhe
    original. Um gaussiano bem leve dá coesão ao conjunto.
    """
    a = rgb.astype(np.float32)
    opened = _max_filter(_min_filter(a, window), window)
    opened = np.minimum(opened, a)          # fundo sem os picos
    residual = (a - opened).max(axis=2)     # o que "sobra" = estrelas
    mask = residual > 16.0
    # dilata a máscara p/ cobrir halos e espículas de difração
    mask = _max_filter(mask.astype(np.float32)[..., None], 7)[..., 0] > 0.5
    patch = gaussian_blur(opened, 1.2)      # remendo discreto nos buracos
    out = np.where(mask[..., None], patch, a)
    return gaussian_blur(out, sigma) if sigma > 0 else out


def build(out_w: int, out_h: int, flip_l: bool, clean: bool = True,
          sigma: float = 0.9, window: int = 17,
          out_path: Path | None = None, lon_shift_deg: float = 0.0) -> None:
    if not SRC.exists():
        raise SystemExit(f"Panorâmica não encontrada: {SRC}")
    src = qimage_to_array(QImage(str(SRC)))
    in_h, in_w, _ = src.shape
    print(f"origem: {in_w}x{in_h}  ->  destino: {out_w}x{out_h}")

    # coordenadas equatoriais de cada pixel de saída
    x = (np.arange(out_w) + 0.5) / out_w
    y = (np.arange(out_h) + 0.5) / out_h
    ra = x * 2.0 * np.pi                      # u = AR/2π
    dec = np.pi / 2.0 - y * np.pi             # v: topo = +90°
    ra_g, dec_g = np.meshgrid(ra, dec)
    cd = np.cos(dec_g)
    v = np.stack(
        [cd * np.cos(ra_g), cd * np.sin(ra_g), np.sin(dec_g)], axis=-1
    )
    g = v @ ICRS_TO_GAL.T                     # ICRS -> galáctico
    lon = np.arctan2(g[..., 1], g[..., 0])    # l em (-π, π]
    lat = np.arcsin(np.clip(g[..., 2], -1.0, 1.0))

    sign = -1.0 if flip_l else 1.0
    # centro galáctico no meio; l positivo para a ESQUERDA por padrão
    lon = lon + math.radians(lon_shift_deg)
    xin = (0.5 - sign * lon / (2.0 * np.pi)) * in_w - 0.5
    yin = (0.5 - lat / np.pi) * in_h - 0.5
    xin = np.mod(xin, in_w)
    yin = np.clip(yin, 0.0, in_h - 1.001)

    # bilinear
    x0 = np.floor(xin).astype(np.int64)
    y0 = np.floor(yin).astype(np.int64)
    x1 = (x0 + 1) % in_w
    y1 = np.minimum(y0 + 1, in_h - 1)
    fx = (xin - x0)[..., None]
    fy = (yin - y0)[..., None]
    s = src.astype(np.float32)
    out = (
        s[y0, x0] * (1 - fx) * (1 - fy)
        + s[y0, x1] * fx * (1 - fy)
        + s[y1, x0] * (1 - fx) * fy
        + s[y1, x1] * fx * fy
    )
    out = np.clip(out, 0, 255)
    if clean:
        before = out.mean(axis=2)
        out = remove_stars(out, window=window, sigma=sigma)
        after = out.mean(axis=2)
        print(
            f"limpeza: janela={window}px sigma={sigma} · "
            f"pico {before.max():.0f} -> {after.max():.0f} · "
            f"média {before.mean():.1f} -> {after.mean():.1f}"
        )
    dest = out_path or OUT
    img = array_to_qimage(np.clip(out, 0, 255).astype(np.uint8))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dest), "JPG", 90)
    print(f"gravado: {dest} ({dest.stat().st_size:,} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", default="4096x2048")
    parser.add_argument("--flip", action="store_true",
                        help="inverte o sentido da longitude galáctica")
    parser.add_argument("--raw", action="store_true",
                        help="não remove estrelas nem suaviza")
    parser.add_argument("--sigma", type=float, default=0.9)
    parser.add_argument("--window", type=int, default=17)
    parser.add_argument("--out", default=None,
                        help="caminho de saída alternativo")
    parser.add_argument("--lon-shift", type=float, default=0.0,
                        help="deslocamento de longitude galáctica (graus)")
    args = parser.parse_args()
    w, h = (int(v) for v in args.size.lower().split("x"))
    build(w, h, args.flip, clean=not args.raw, sigma=args.sigma,
          window=args.window,
          out_path=Path(args.out) if args.out else None,
          lon_shift_deg=args.lon_shift)
    return 0


if __name__ == "__main__":
    sys.exit(main())
