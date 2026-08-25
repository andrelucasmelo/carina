"""Extrai contornos reais de nebulosas a partir das imagens DSS embarcadas.

Para cada objeto de uma lista curada: limiar de brilho sobre a imagem
suavizada, seleção da componente conectada dominante, extração da borda por
marching squares, simplificação (Douglas-Peucker) e conversão de pixel para
coordenadas equatoriais pela projeção gnomônica do recorte.

Saída: data/processed/outlines.json  {nome: [[ [ra,dec], ... ], ...]}

Uso:
    python scripts/build_outlines.py [--only M42] [--preview DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "data" / "processed" / "images"
DB = ROOT / "data" / "processed" / "dso.sqlite"
OUT = ROOT / "data" / "processed" / "outlines.json"

# (designação, percentil do limiar) — ajustado por objeto quando necessário
CURATED = [
    ("M 42", 82.0), ("M 8", 80.0), ("M 20", 85.0), ("M 16", 85.0),
    ("M 17", 85.0), ("M 27", 90.0), ("M 57", 93.0), ("M 76", 93.0),
    ("M 97", 93.0), ("M 1", 88.0), ("M 78", 90.0), ("M 43", 88.0),
    ("C 33", 88.0), ("C 34", 88.0),        # Véu leste e oeste
    ("C 20", 85.0),                        # América do Norte
    ("C 49", 85.0),                        # Roseta
    ("C 63", 90.0),                        # Helix
    ("C 11", 90.0),                        # Bolha
    ("C 27", 88.0),                        # Crescente
    ("C 9", 86.0),                         # Caverna (Sh2-155)
    ("C 46", 90.0),                        # Nebulosa de Hubble
    ("C 4", 88.0),                         # Íris
]

MIN_AREA_FRAC = 0.004      # ignora manchas menores que isso da imagem
SIMPLIFY_PX = 2.2          # tolerância do Douglas-Peucker, em pixels


def load_gray(path: Path) -> np.ndarray:
    img = QImage(str(path)).convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8)
    rgb = buf.reshape(h, img.bytesPerLine())[:, : w * 3].reshape(h, w, 3)
    return rgb.astype(np.float32).mean(axis=2)


def box_blur(a: np.ndarray, radius: int) -> np.ndarray:
    if radius < 1:
        return a
    k = 2 * radius + 1
    pad = np.pad(a, radius, mode="edge")
    cs = np.cumsum(pad, axis=1, dtype=np.float64)
    cs = np.concatenate([np.zeros((cs.shape[0], 1)), cs], axis=1)
    a2 = (cs[:, k:] - cs[:, :-k]) / k
    cs = np.cumsum(a2, axis=0, dtype=np.float64)
    cs = np.concatenate([np.zeros((1, cs.shape[1])), cs], axis=0)
    out = (cs[k:, :] - cs[:-k, :]) / k
    return out.astype(np.float32)


def dominant_component(mask: np.ndarray) -> np.ndarray:
    """Mantém a maior componente conectada (4-vizinhança)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []
    for sy in range(0, h, 3):
        for sx in range(0, w, 3):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            comp = []
            queue = deque([(sy, sx)])
            seen[sy, sx] = True
            while queue:
                y, x = queue.popleft()
                comp.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < h and 0 <= nx < w and mask[ny, nx]
                            and not seen[ny, nx]):
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            if len(comp) > len(best):
                best = comp
    out = np.zeros_like(mask)
    if best:
        ys, xs = zip(*best)
        out[np.asarray(ys), np.asarray(xs)] = True
    return out


def marching_squares(mask: np.ndarray) -> list[list[tuple[float, float]]]:
    """Contornos da máscara binária como polilinhas fechadas (em pixels)."""
    h, w = mask.shape
    m = mask.astype(np.uint8)
    segs: dict[tuple[float, float], list[tuple[float, float]]] = {}

    def add(p0, p1):
        segs.setdefault(p0, []).append(p1)

    for y in range(h - 1):
        for x in range(w - 1):
            idx = (m[y, x] << 3) | (m[y, x + 1] << 2) | \
                  (m[y + 1, x + 1] << 1) | m[y + 1, x]
            if idx in (0, 15):
                continue
            top = (x + 0.5, float(y))
            right = (float(x + 1), y + 0.5)
            bottom = (x + 0.5, float(y + 1))
            left = (float(x), y + 0.5)
            table = {
                1: [(left, bottom)], 2: [(bottom, right)],
                3: [(left, right)], 4: [(right, top)],
                5: [(left, top), (bottom, right)], 6: [(bottom, top)],
                7: [(left, top)], 8: [(top, left)], 9: [(top, bottom)],
                10: [(top, right), (bottom, left)], 11: [(top, right)],
                12: [(right, left)], 13: [(right, bottom)],
                14: [(bottom, left)],
            }
            for p0, p1 in table.get(idx, []):
                add(p0, p1)

    contours = []
    while segs:
        start = next(iter(segs))
        path = [start]
        current = start
        while True:
            nexts = segs.get(current)
            if not nexts:
                break
            nxt = nexts.pop()
            if not nexts:
                segs.pop(current, None)
            path.append(nxt)
            current = nxt
            if current == start:
                break
        if len(path) > 12:
            contours.append(path)
    return contours


def simplify(points: list[tuple[float, float]], tol: float) -> list:
    """Douglas-Peucker iterativo."""
    if len(points) < 3:
        return points
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    pts = np.asarray(points, dtype=np.float64)
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        a, b = pts[i0], pts[i1]
        ab = b - a
        norm = math.hypot(*ab)
        seg = pts[i0 + 1:i1]
        if norm < 1e-9:
            d = np.linalg.norm(seg - a, axis=1)
        else:
            rel = seg - a
            # produto vetorial 2D (np.cross deixou de aceitar 2 dimensões)
            d = np.abs(ab[0] * rel[:, 1] - ab[1] * rel[:, 0]) / norm
        k = int(np.argmax(d))
        if d[k] > tol:
            idx = i0 + 1 + k
            keep[idx] = True
            stack += [(i0, idx), (idx, i1)]
    return [tuple(p) for p in pts[keep]]


def pixels_to_radec(points, ra0: float, dec0: float, fov_deg: float,
                    size: int) -> list[list[float]]:
    """Projeção gnomônica inversa (TAN), como no recorte do hips2fits."""
    scale = math.radians(fov_deg) / size
    out = []
    for px, py in points:
        # x cresce para o oeste (RA cresce para a esquerda na imagem)
        dx = -(px - size / 2.0) * scale
        dy = -(py - size / 2.0) * scale
        denom = math.cos(dec0) - dy * math.sin(dec0)
        ra = ra0 + math.atan2(dx, denom)
        dec = math.atan(
            (math.sin(dec0) + dy * math.cos(dec0))
            / math.hypot(dx, denom)
        )
        out.append([round(math.degrees(ra) % 360.0, 5),
                    round(math.degrees(dec), 5)])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default=None)
    parser.add_argument("--preview", default=None)
    args = parser.parse_args()

    import sqlite3

    cx = sqlite3.connect(DB)
    cx.row_factory = sqlite3.Row
    result: dict[str, list] = {}

    for name, percentile in CURATED:
        if args.only and args.only.replace(" ", "") != name.replace(" ", ""):
            continue
        row = cx.execute(
            "SELECT o.name, o.ra, o.dec, o.maj FROM objects o"
            " JOIN designations d ON d.object_id = o.id"
            " WHERE (d.catalog || ' ' || d.ident) = ?"
            " OR o.name = ? LIMIT 1",
            (name, name),
        ).fetchone()
        if row is None:
            print(f"  [!] {name}: não encontrado no banco")
            continue
        img_path = IMAGES / (row["name"].replace(" ", "") + ".jpg")
        if not img_path.exists():
            print(f"  [!] {name}: imagem ausente ({img_path.name})")
            continue

        gray = load_gray(img_path)
        size = gray.shape[0]
        smooth = box_blur(gray, 3)
        thr = np.percentile(smooth, percentile)
        mask = smooth >= thr
        mask = dominant_component(mask)
        if mask.sum() < MIN_AREA_FRAC * mask.size:
            print(f"  [!] {name}: região dominante pequena demais")
            continue

        contours = marching_squares(mask)
        if not contours:
            print(f"  [!] {name}: sem contorno")
            continue
        contours.sort(key=len, reverse=True)
        fov = min(6.0, max(0.25, (row["maj"] or 10.0) * 2.5 / 60.0))
        polys = []
        for c in contours[:3]:
            pts = simplify(c, SIMPLIFY_PX)
            if len(pts) >= 8:
                polys.append(
                    pixels_to_radec(pts, row["ra"], row["dec"], fov, size)
                )
        if not polys:
            continue
        result[row["name"]] = polys
        print(f"  [ok] {name} ({row['name']}): {len(polys)} contorno(s), "
              f"{sum(len(p) for p in polys)} vértices")

        if args.preview:
            prev = Path(args.preview)
            prev.mkdir(parents=True, exist_ok=True)
            rgb = np.stack([gray] * 3, axis=2).astype(np.uint8)
            for c in contours[:3]:
                for px, py in simplify(c, SIMPLIFY_PX):
                    xi, yi = int(px), int(py)
                    if 0 <= yi < size and 0 <= xi < size:
                        rgb[max(0, yi - 1):yi + 2, max(0, xi - 1):xi + 2] = (
                            (255, 60, 60)
                        )
            img = QImage(
                np.ascontiguousarray(rgb).data, size, size, size * 3,
                QImage.Format_RGB888,
            )
            img.copy().save(str(prev / f"outline_{row['name'].replace(' ', '')}.png"))

    OUT.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"gravado: {OUT.name} — {len(result)} objetos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
