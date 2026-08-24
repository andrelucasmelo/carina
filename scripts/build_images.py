"""Pré-baixa imagens dos objetos Messier e Caldwell para o pacote (ADR-012).

Gera data/processed/images/<NomeSemEspaço>.jpg usando o serviço hips2fits do
CDS (recortes do survey DSS2 color). Esses ~215 arquivos são embarcados na
instalação; para os demais objetos o aplicativo baixa sob demanda e guarda em
cache local (mesma URL), de modo que tudo que já foi visto funciona offline.

Uso:
    python scripts/build_images.py [--force] [--size 512]
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "dso.sqlite"
OUT = ROOT / "data" / "processed" / "images"

# Mirror primeiro: o servidor principal (alasky.cds) costuma estrangular.
HIPS2FITS_SERVERS = [
    "https://alaskybis.unistra.fr/hips-image-services/hips2fits",
    "https://alasky.cds.unistra.fr/hips-image-services/hips2fits",
]
SURVEY = "CDS/P/DSS2/color"


def image_filename(name: str) -> str:
    return name.replace(" ", "").replace("/", "_") + ".jpg"


def fov_for(maj_arcmin: float | None) -> float:
    """Campo do recorte (graus) a partir do tamanho do objeto."""
    if not maj_arcmin:
        return 0.5
    return min(6.0, max(0.25, maj_arcmin * 2.5 / 60.0))


def fetch(ra_deg: float, dec_deg: float, fov_deg: float, size: int) -> bytes:
    params = {
        "hips": SURVEY,
        "ra": f"{ra_deg:.6f}",
        "dec": f"{dec_deg:.6f}",
        "fov": f"{fov_deg:.4f}",
        "width": str(size),
        "height": str(size),
        "projection": "TAN",
        "format": "jpg",
    }
    last_exc: Exception | None = None
    for server in HIPS2FITS_SERVERS:
        url = f"{server}?{urllib.parse.urlencode(params)}"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            last_exc = exc
    raise last_exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(DB)
    rows = cx.execute(
        "SELECT DISTINCT o.name, o.ra, o.dec, o.maj FROM objects o"
        " JOIN designations d ON d.object_id = o.id"
        " WHERE d.catalog IN ('M', 'C') ORDER BY o.name"
    ).fetchall()
    cx.close()

    ok = skip = fail = 0
    for name, ra, dec, maj in rows:
        dest = OUT / image_filename(name)
        if dest.exists() and not args.force:
            skip += 1
            continue
        try:
            data = fetch(math.degrees(ra), math.degrees(dec), fov_for(maj), args.size)
            dest.write_bytes(data)
            ok += 1
            print(f"  [img] {name} ({len(data) // 1024} KB)")
            time.sleep(0.3)  # cortesia com o serviço do CDS
        except Exception as exc:
            fail += 1
            print(f"  [!] {name}: {exc}")
    total_mb = sum(f.stat().st_size for f in OUT.glob('*.jpg')) / 1e6
    print(f"Baixadas {ok}, existentes {skip}, falhas {fail} · {total_mb:.1f} MB em {OUT}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
