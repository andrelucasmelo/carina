"""Verifica o alinhamento da textura da Via Láctea contra o catálogo HYG.

Para cada estrela brilhante do NOSSO mapa, procura o pico de brilho na
textura CRUA (sem remoção de estrelas) ao redor da posição esperada e mede o
desvio em minutos de arco. Desvio sistemático => erro na conversão
galáctico→equatorial; desvios ~0 => textura alinhada com o catálogo.

Uso:
    python scripts/check_mwtex_alignment.py <textura_crua.jpg>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_mwtex import qimage_to_array  # noqa: E402

STARS = [
    "Antares", "Altair", "Deneb", "Vega", "Sirius", "Canopus", "Acrux",
    "Rigil Kentaurus", "Betelgeuse", "Achernar", "Fomalhaut", "Spica",
    "Procyon", "Capella", "Hadar", "Atria", "Alnair", "Peacock", "Rigel",
    "Aldebaran", "Pollux", "Regulus", "Arcturus", "Mimosa", "Adhara",
    "Shaula", "Alioth", "Dubhe", "Alkaid", "Menkent", "Alhena", "Castor",
    "Mirfak", "Polaris", "Diphda", "Alphard", "Hamal", "Algieba",
]

WINDOW_DEG = 0.75    # meia-janela de busca do pico

# Matriz ICRS -> galáctico (mesma do build)
ICRS_TO_GAL = np.array([
    [-0.0548755604, -0.8734370902, -0.4838350155],
    [+0.4941094279, -0.4448296300, +0.7469822445],
    [-0.8676661490, -0.1980763734, +0.4559837762],
])


def centroid_peak(win: np.ndarray):
    """(y, x) do pico com centroide 5×5 subpixel; None se ambíguo/fraco."""
    peak = float(win.max())
    if peak < 55:
        return None
    py, px = np.unravel_index(int(np.argmax(win)), win.shape)
    if (py < 2 or px < 2 or py >= win.shape[0] - 2
            or px >= win.shape[1] - 2):
        return None
    sub = win[py - 2:py + 3, px - 2:px + 3].astype(np.float64)
    sub = np.clip(sub - np.median(win), 0.0, None)
    total = sub.sum()
    if total <= 0:
        return None
    ys, xs = np.mgrid[-2:3, -2:3]
    return (py + (ys * sub).sum() / total, px + (xs * sub).sum() / total)


def main() -> int:
    tex_path = Path(sys.argv[1])
    tex = qimage_to_array(QImage(str(tex_path))).astype(np.float32)
    lum = tex.mean(axis=2)
    h, w = lum.shape
    px_deg = 360.0 / w

    npz = np.load(ROOT / "data" / "processed" / "stars_hyg.npz")
    names = json.loads(
        (ROOT / "data" / "processed" / "star_names.json").read_text("utf-8")
    )
    proper = {name: idx for idx, name in names["proper"]}
    ra_all, dec_all = npz["ra"], npz["dec"]

    half = int(round(WINDOW_DEG / px_deg))
    rows = []
    print(f"janela de busca: ±{WINDOW_DEG}° ({half} px, {px_deg*60:.1f}'/px)")
    print(f"{'estrela':16s} {'l':>6s} {'b':>6s} {'dl·cosb′':>9s} {'db′':>7s}")
    for name in STARS:
        idx = proper.get(name)
        if idx is None:
            continue
        ra = math.degrees(float(ra_all[idx])) % 360.0
        dec = math.degrees(float(dec_all[idx]))
        x0 = ra / 360.0 * w - 0.5
        y0 = (90.0 - dec) / 180.0 * h - 0.5
        xi, yi = int(round(x0)), int(round(y0))
        ys = slice(max(half, yi - half), min(h - half, yi + half + 1))
        if ys.start >= ys.stop:
            continue
        win = np.take(
            lum[ys], np.arange(xi - half, xi + half + 1) % w, axis=1
        )
        res = centroid_peak(win)
        if res is None:
            continue
        cy, cx = res
        d_dec = -((ys.start + cy) - y0) * px_deg * 60.0
        d_ra = ((xi - half + cx) - x0) * px_deg * 60.0 * math.cos(
            math.radians(dec)
        )
        if math.hypot(d_ra, d_dec) > 45.0:
            continue  # provavelmente casou com outra fonte

        # converte o desvio para o frame galáctico (jacobiano local)
        v = np.array([
            math.cos(math.radians(dec)) * math.cos(math.radians(ra)),
            math.cos(math.radians(dec)) * math.sin(math.radians(ra)),
            math.sin(math.radians(dec)),
        ])
        g = ICRS_TO_GAL @ v
        lon = math.atan2(g[1], g[0])
        lat = math.asin(max(-1.0, min(1.0, g[2])))
        # bases tangentes: leste/norte equatorial e galáctico
        e_eq = np.array([-math.sin(math.radians(ra)),
                         math.cos(math.radians(ra)), 0.0])
        n_eq = np.cross(v, e_eq)
        e_g_icrs = ICRS_TO_GAL.T @ np.array([-math.sin(lon), math.cos(lon), 0])
        n_g_icrs = np.cross(v, e_g_icrs)
        d_vec = d_ra * e_eq + d_dec * n_eq
        dl_cosb = float(np.dot(d_vec, e_g_icrs))
        db = float(np.dot(d_vec, n_g_icrs))
        rows.append((math.degrees(lon) % 360.0, math.degrees(lat),
                     dl_cosb, db, name))
        print(f"{name:16s} {math.degrees(lon)%360:6.1f} "
              f"{math.degrees(lat):6.1f} {dl_cosb:9.1f} {db:7.1f}")

    if len(rows) < 6:
        print("estrelas de referência insuficientes")
        return 1
    arr = np.asarray([(r[0], r[1], r[2], r[3]) for r in rows])
    lon_r = np.radians(arr[:, 0])
    # modelo de registro: db = db0 + ex·sin l − ey·cos l
    #                     dl·cosb = dl0·cos b + ex·cos l·sin b + ey·sin l·sin b
    lat_r = np.radians(arr[:, 1])
    A_db = np.column_stack(
        [np.ones_like(lon_r), np.sin(lon_r), -np.cos(lon_r)]
    )
    sol_db, *_ = np.linalg.lstsq(A_db, arr[:, 3], rcond=None)
    db0, ex, ey = sol_db
    A_dl = np.column_stack([
        np.cos(lat_r), np.cos(lon_r) * np.sin(lat_r),
        np.sin(lon_r) * np.sin(lat_r),
    ])
    sol_dl, *_ = np.linalg.lstsq(
        A_dl, arr[:, 2] - ex * np.cos(lon_r) * np.sin(lat_r)
        - ey * np.sin(lon_r) * np.sin(lat_r), rcond=None,
    )
    dl0 = sol_dl[0]

    resid_db = arr[:, 3] - A_db @ sol_db
    print(f"\nmedidas usadas: {len(rows)}")
    print(f"mediana bruta: dl·cosb = {np.median(arr[:,2]):+.1f}'  "
          f"db = {np.median(arr[:,3]):+.1f}'")
    print(f"ajuste: db0 = {db0:+.1f}'  ex = {ex:+.1f}'  ey = {ey:+.1f}'  "
          f"dl0 = {dl0:+.1f}'")
    print(f"resíduo db após ajuste: ±{np.median(np.abs(resid_db)):.1f}'")
    print(
        "\nparâmetro p/ build_mwtex.py:  --align "
        f"\"{dl0/60:.4f},{db0/60:.4f},{ex/60:.4f},{ey/60:.4f}\"  (graus)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
