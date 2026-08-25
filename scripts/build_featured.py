"""Baixa imagens 'em destaque' para o céu: Nuvens de Magalhães e alvos
famosos de astrofotografia que não estão nos catálogos Messier/Caldwell.

Gera data/processed/images/<Nome>.jpg + o manifesto
data/processed/featured_images.json {nome: {"fov": graus}} — o runtime usa o
manifesto para saber quais objetos têm imagem destacada e com qual campo
desenhá-la (o mesmo campo usado no download, garantindo o alinhamento).

Uso:
    python scripts/build_featured.py [--force]
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

# (designação de busca, FOV em graus ou None = automático, tamanho px)
FEATURED = [
    # Nuvens de Magalhães (pedido do usuário)
    ("ESO056-115", 13.0, 1024),      # Grande Nuvem de Magalhães
    ("NGC 292", 8.0, 1024),          # Pequena Nuvem de Magalhães
    # nebulosas famosas fora de M/C
    ("IC 434", 1.6, 768),            # Cabeça de Cavalo
    ("IC 5070", 2.4, 768),           # Pelicano
    ("IC 1805", 3.2, 768),           # Coração
    ("IC 1848", 3.2, 768),           # Alma
    ("NGC 1499", 3.6, 768),          # Califórnia
    ("NGC 2264", 2.2, 768),          # Cone / Árvore de Natal
    ("NGC 281", 1.6, 768),           # Pacman
    ("NGC 2359", 1.1, 768),          # Elmo de Thor
    ("IC 443", 1.8, 768),            # Água-viva
    ("IC 410", 1.5, 768),            # Girinos
    ("IC 1396", 3.6, 768),           # Tromba de Elefante
    ("NGC 6334", 1.5, 768),          # Pata de Gato
    ("NGC 6357", 1.8, 768),          # Lagosta
    ("NGC 6188", 2.2, 768),          # Dragões de Ara
    ("SH2 101", 1.4, 768),           # Tulipa
    ("SH2 240", 4.2, 768),           # Espaguete (Simeis 147)
    ("IC 1318", 3.6, 768),           # Borboleta (Sadr)
    ("NGC 1977", 1.0, 768),          # Homem Correndo
    ("NGC 3628", 0.9, 768),          # Hambúrguer (Trio de Leão)
    ("NGC 1333", 1.2, 768),          # NGC 1333 (Perseus)
    ("IC 2118", 3.2, 768),           # Cabeça de Bruxa
    ("IC 4592", 3.4, 768),           # Cabeça de Cavalo Azul
    ("NGC 3324", 1.2, 768),          # Gabriela Mistral
    ("IC 4604", 3.0, 768),           # Rho Ophiuchi
    ("NGC 7822", 2.6, 768),          # NGC 7822 (Cefeu)
    ("NGC 2903", 0.7, 768),          # galáxia NGC 2903
]


def resolve(cx, query: str):
    """Encontra o objeto por designação ('IC 434', 'SH2 101') ou nome."""
    row = cx.execute(
        "SELECT o.id, o.name, o.ra, o.dec, o.maj FROM objects o"
        " JOIN designations d ON d.object_id = o.id"
        " WHERE (d.catalog || ' ' || d.ident) = ? LIMIT 1",
        (query,),
    ).fetchone()
    if row is None:
        row = cx.execute(
            "SELECT id, name, ra, dec, maj FROM objects WHERE name = ?"
            " LIMIT 1", (query,),
        ).fetchone()
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cx = sqlite3.connect(DB)
    cx.row_factory = sqlite3.Row
    IMAGES.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    if MANIFEST.exists() and not args.force:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    ok = fail = 0
    for query, fov, size in FEATURED:
        row = resolve(cx, query)
        if row is None:
            print(f"  [!] {query}: não encontrado no banco")
            fail += 1
            continue
        name = row["name"]
        fov_deg = fov or min(6.0, max(0.25, (row["maj"] or 10.0) * 2.5 / 60.0))
        dest = IMAGES / image_filename(name)
        if dest.exists() and name in manifest and not args.force:
            print(f"  [ok] {query} -> {name} (já existe)")
            manifest[name] = {"fov": fov_deg}
            continue
        try:
            data = fetch(
                math.degrees(row["ra"]), math.degrees(row["dec"]),
                fov_deg, size,
            )
            dest.write_bytes(data)
            manifest[name] = {"fov": fov_deg}
            ok += 1
            print(f"  [img] {query} -> {name}  fov={fov_deg}°  "
                  f"({len(data) // 1024} KB)")
            time.sleep(0.3)
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  [!] {query}: {exc}")

    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"manifesto: {len(manifest)} objetos · novas {ok} · falhas {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
