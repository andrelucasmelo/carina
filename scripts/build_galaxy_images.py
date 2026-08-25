"""Baixa imagens DSS das galáxias NGC/IC até magnitude 11.

Acrescenta as entradas ao mesmo manifesto dos destaques
(featured_images.json), de modo que o runtime desenhe cada imagem com o
campo exato usado no download — é isso que garante o alinhamento com as
estrelas do catálogo (os recortes TAN do hips2fits são astrometricamente
corretos; ver ADR-026 e B-017).

Uso:
    python scripts/build_galaxy_images.py [--max-mag 11] [--force]
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


def fov_for(maj_arcmin: float | None) -> float:
    """Campo do recorte: 3× o eixo maior, com limites sensatos."""
    if not maj_arcmin:
        return 0.25
    return min(4.0, max(0.15, maj_arcmin * 3.0 / 60.0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-mag", type=float, default=11.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cx = sqlite3.connect(DB)
    cx.row_factory = sqlite3.Row
    IMAGES.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    rows = cx.execute(
        "SELECT DISTINCT o.name, o.ra, o.dec, o.maj, o.mag FROM objects o"
        " JOIN designations d ON d.object_id = o.id"
        " WHERE d.catalog IN ('NGC','IC') AND o.klass = 'GAL'"
        " AND o.mag IS NOT NULL AND o.mag <= ?"
        " ORDER BY o.mag", (args.max_mag,),
    ).fetchall()
    print(f"{len(rows)} galáxias NGC/IC com mag <= {args.max_mag}")

    ok = skip = fail = 0
    for row in rows:
        name = row["name"]
        dest = IMAGES / image_filename(name)
        fov = fov_for(row["maj"])
        if dest.exists() and not args.force:
            manifest.setdefault(name, {"fov": fov})
            skip += 1
            continue
        try:
            size = 768 if fov > 0.5 else 512
            data = fetch(math.degrees(row["ra"]), math.degrees(row["dec"]),
                         fov, size)
            dest.write_bytes(data)
            manifest[name] = {"fov": fov}
            ok += 1
            if ok % 20 == 0:
                print(f"  {ok} baixadas… (última: {name})", flush=True)
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
