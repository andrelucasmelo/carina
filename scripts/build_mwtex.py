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


def build(out_w: int, out_h: int, flip_l: bool) -> None:
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
    img = array_to_qimage(np.clip(out, 0, 255).astype(np.uint8))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(OUT), "JPG", 88)
    print(f"gravado: {OUT} ({OUT.stat().st_size:,} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", default="4096x2048")
    parser.add_argument("--flip", action="store_true",
                        help="inverte o sentido da longitude galáctica")
    args = parser.parse_args()
    w, h = (int(v) for v in args.size.lower().split("x"))
    build(w, h, args.flip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
