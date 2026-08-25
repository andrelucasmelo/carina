"""Baixa imagens DSS para objetos grandes e para galáxias médias.

Critérios (pedido do usuário):
  - qualquer objeto de céu profundo com eixo maior > 30'
  - qualquer galáxia com eixo maior > 8'

Acrescenta ao manifesto featured_images.json, que o runtime usa para
desenhar cada imagem com o campo exato do download (garante o alinhamento).

Uso:
    python scripts/build_large_images.py [--min-size 30] [--galaxy-size 8]
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_images import fetch, image_filename  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "dso.sqlite"
IMAGES = ROOT / "data" / "processed" / "images"
MANIFEST = ROOT / "data" / "processed" / "featured_images.json"

# catálogos cujos objetos merecem imagem (evita as 2.710 entradas de Abell,
# que são aglomerados de galáxias distantes sem interesse visual)
CATALOGS = ("M", "C", "NGC", "IC", "SH2", "B", "Mel", "Cr", "VdB", "LDN")


def fov_for(maj_arcmin: float) -> float:
    """Campo do recorte: 2,5× o eixo maior, limitado a 8°."""
    return min(8.0, max(0.15, maj_arcmin * 2.5 / 60.0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-size", type=float, default=30.0,
                        help="eixo maior mínimo, em minutos de arco")
    parser.add_argument("--galaxy-size", type=float, default=8.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cx = sqlite3.connect(DB)
    cx.row_factory = sqlite3.Row
    IMAGES.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    marks = ",".join("?" * len(CATALOGS))
    rows = cx.execute(
        f"SELECT DISTINCT o.name, o.ra, o.dec, o.maj, o.klass FROM objects o"
        f" JOIN designations d ON d.object_id = o.id"
        f" WHERE d.catalog IN ({marks}) AND o.maj IS NOT NULL"
        f"   AND (o.maj > ? OR (o.klass = 'GAL' AND o.maj > ?))"
        f" ORDER BY o.maj DESC",
        (*CATALOGS, args.min_size, args.galaxy_size),
    ).fetchall()
    print(f"{len(rows)} objetos atendem aos critérios "
          f"(> {args.min_size}' ou galáxias > {args.galaxy_size}')")

    ok = skip = fail = 0
    for row in rows:
        name = row["name"]
        dest = IMAGES / image_filename(name)
        fov = fov_for(float(row["maj"]))
        if dest.exists() and not args.force:
            manifest.setdefault(name, {"fov": fov})
            skip += 1
            continue
        try:
            size = 1024 if fov > 3.0 else (768 if fov > 0.8 else 512)
            data = fetch(math.degrees(row["ra"]), math.degrees(row["dec"]),
                         fov, size)
            dest.write_bytes(data)
            manifest[name] = {"fov": fov}
            ok += 1
            if ok % 20 == 0:
                print(f"  {ok} baixadas… (última: {name}, {row['maj']:.0f}')",
                      flush=True)
                MANIFEST.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=1),
                    encoding="utf-8",
                )
            time.sleep(0.25)
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  [!] {name}: {exc}")

    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"novas {ok} · existentes {skip} · falhas {fail} · "
          f"manifesto com {len(manifest)} objetos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
