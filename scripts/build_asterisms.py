"""Asterismos curados → ``data/processed/asterisms.json`` (v0.20 T3).

Lê ``scripts/curated/asterisms.tsv`` (nomes próprios, Bayer ou HIP),
resolve cada estrela no catálogo HYG embarcado e grava as polilinhas como
números HIP. Falha (código 1) se alguma estrela não for encontrada — o
JSON embarcado nunca tem um traço quebrado.

Uso:  python scripts/build_asterisms.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SRC = ROOT / "scripts" / "curated" / "asterisms.tsv"
OUT = ROOT / "data" / "processed" / "asterisms.json"


def parse(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            raise SystemExit(f"linha com {len(parts)} colunas: {line[:60]}")
        key, name, consts, lines, text = (p.strip() for p in parts)
        rows.append({"key": key, "name": name,
                     "const": [c.strip() for c in consts.split(",") if c.strip()],
                     "lines": [[s.strip() for s in pl.split(",")] for pl in lines.split("|")],
                     "text": text})
    return rows


def build() -> list[dict]:
    from carina.catalogs.stars import StarCatalog
    from carina.core.tours import Resolver

    stars = StarCatalog(ROOT / "data" / "processed")
    res = Resolver(stars, dso=None)
    out, missing = [], []
    for a in parse(SRC):
        lines = []
        for pl in a["lines"]:
            hips = []
            for spec in pl:
                i = res.star_index(spec)
                if i is None or not stars.hip[i]:
                    missing.append(f"{a['key']}: {spec}")
                    continue
                hips.append(int(stars.hip[i]))
            if len(hips) >= 2:
                lines.append(hips)
        out.append(dict(a, lines=lines))
    if missing:
        raise SystemExit("estrelas não encontradas:\n  " + "\n  ".join(missing))
    return out


def main() -> int:
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data)} asterismos → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
