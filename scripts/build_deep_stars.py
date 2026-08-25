"""Catálogo profundo de estrelas (Tycho-2 via ATHYG) até magnitude 12.

O HYG v4.1 é completo apenas até ~mag 9; este script acrescenta as estrelas
mais fracas a partir do ATHYG v3.2 (que incorpora o Tycho-2), removendo as
que já existem no HYG por proximidade angular.

Saída: data/processed/stars_deep.npz (xyz float32, mag float32, ci float32)

Uso:
    python scripts/build_deep_stars.py [--max-mag 12] [--force]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import math
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
# Subconjunto do ATHYG v3.2 limitado por magnitude (~mag 11-12), que
# incorpora o Tycho-2. O arquivo completo tem 200 MB e é desnecessário aqui.
SRC_URL = ("https://raw.githubusercontent.com/astronexus/ATHYG-Database/main/"
           "data/subsets/athyg_32_reduced_m11.csv.gz")
SRC = RAW / "athyg_32_reduced_m11.csv.gz"

DEDUPE_ARCSEC = 6.0     # raio de casamento com o HYG
MIN_MAG = 8.5           # abaixo disso o HYG já cobre bem


def download(force: bool) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    if SRC.exists() and not force:
        print(f"  [ok] {SRC.name} ({SRC.stat().st_size:,} bytes)")
        return SRC
    print(f"  [dl] {SRC_URL}")
    with requests.get(SRC_URL, stream=True, timeout=1800) as resp:
        resp.raise_for_status()
        total = 0
        with open(SRC, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                total += len(chunk)
                if total % (20 << 20) < (1 << 20):
                    print(f"       {total / 1e6:.0f} MB…", flush=True)
    print(f"       -> {SRC.name} ({SRC.stat().st_size:,} bytes)")
    return SRC


def cell_key(ra_rad: float, dec_rad: float, size_rad: float) -> tuple:
    """Célula da grade de dedupe (compensa a convergência dos meridianos)."""
    dec_i = int(math.floor(dec_rad / size_rad))
    cos_d = max(math.cos(dec_rad), 1e-3)
    ra_i = int(math.floor(ra_rad / (size_rad / cos_d)))
    return dec_i, ra_i


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-mag", type=float, default=12.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    path = download(args.force)

    # posições do HYG para dedupe
    hyg = np.load(OUT / "stars_hyg.npz")
    hyg_ra = hyg["ra"].astype(np.float64)
    hyg_dec = hyg["dec"].astype(np.float64)
    hyg_mag = hyg["mag"]
    cell = math.radians(DEDUPE_ARCSEC * 4 / 3600.0)
    index: dict[tuple, list[int]] = {}
    for i in range(len(hyg_ra)):
        index.setdefault(cell_key(hyg_ra[i], hyg_dec[i], cell), []).append(i)
    print(f"  HYG: {len(hyg_ra):,} estrelas indexadas para dedupe")

    tol = math.radians(DEDUPE_ARCSEC / 3600.0)
    xs, ys, zs, mags, cis = [], [], [], [], []
    n_read = n_dup = 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            n_read += 1
            try:
                mag = float(row["mag"])
            except (TypeError, ValueError, KeyError):
                continue
            if mag <= MIN_MAG or mag > args.max_mag:
                continue
            try:
                ra = float(row["ra"]) * math.pi / 12.0
                dec = float(row["dec"]) * math.pi / 180.0
            except (TypeError, ValueError, KeyError):
                continue

            # dedupe: procura vizinho do HYG nas 9 células ao redor
            dec_i, ra_i = cell_key(ra, dec, cell)
            found = False
            for dd in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    for j in index.get((dec_i + dd, ra_i + dr), ()):
                        if abs(hyg_dec[j] - dec) > tol:
                            continue
                        dra = (hyg_ra[j] - ra) * math.cos(dec)
                        if abs(dra) > tol:
                            continue
                        if math.hypot(dra, hyg_dec[j] - dec) <= tol:
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                n_dup += 1
                continue

            cd = math.cos(dec)
            xs.append(cd * math.cos(ra))
            ys.append(cd * math.sin(ra))
            zs.append(math.sin(dec))
            mags.append(mag)
            try:
                cis.append(float(row.get("ci") or 0.65))
            except ValueError:
                cis.append(0.65)
            if len(mags) % 250000 == 0:
                print(f"       {len(mags):,} aceitas ({n_read:,} lidas)…",
                      flush=True)

    mag_arr = np.asarray(mags, dtype=np.float32)
    order = np.argsort(mag_arr, kind="stable")
    xyz = np.stack(
        [np.asarray(xs, np.float32), np.asarray(ys, np.float32),
         np.asarray(zs, np.float32)], axis=1
    )[order]
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / "stars_deep.npz",
        xyz=xyz, mag=mag_arr[order],
        ci=np.asarray(cis, dtype=np.float32)[order],
    )
    size = (OUT / "stars_deep.npz").stat().st_size
    print(f"  lidas {n_read:,} · duplicadas do HYG {n_dup:,} · "
          f"gravadas {len(mag_arr):,}")
    print(f"  faixa de magnitude: {mag_arr.min():.2f} a {mag_arr.max():.2f}")
    print(f"  stars_deep.npz: {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
