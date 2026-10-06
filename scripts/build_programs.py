"""Programas de observação → ``data/processed/programs/*.json`` (v0.22 T1).

- **Messier** (110) e **Caldwell** (109): pelas designações do banco de céu
  profundo embarcado;
- **Herschel 400**: ``scripts/curated/herschel400.txt`` (lista oficial da
  Astronomical League por número NGC), resolvida no banco;
- **Binóculo**: a lista curada dos tours (``scripts/curated/tours/_binoculo.tsv``).

Cada item guarda a identidade usada no diário (o nome do objeto no banco,
"M 31", "NGC 6543"…), para o progresso sair das observações. Falha se algum
item não for encontrado.

Uso:  python scripts/build_programs.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "dso.sqlite"
OUT = ROOT / "data" / "processed" / "programs"


def _row_by_designation(cx, catalog: str, ident: str):
    return cx.execute(
        "SELECT o.name, o.common, o.klass, o.type, o.con FROM designations d"
        " JOIN objects o ON o.id = d.object_id WHERE d.catalog = ? AND d.ident = ?",
        (catalog, ident)).fetchone()


def _item(number, row, label=None) -> dict:
    """``name`` é a designação; o nome popular vai cru (traduzido ao exibir)."""
    name, common, klass, typ, con = row
    return {"number": number, "kind": "dso", "ident": name, "name": label or name,
            "common": common or "", "group": klass or "", "type": typ or "",
            "con": con or ""}


def build() -> dict[str, dict]:
    cx = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    errs = []
    progs = {}

    for key, cat, n, title, source in (
            ("messier", "M", 110, "Messier", "Charles Messier (1771–1781)"),
            ("caldwell", "C", 109, "Caldwell", "Patrick Moore, Sky & Telescope (1995)")):
        items = []
        for i in range(1, n + 1):
            row = _row_by_designation(cx, cat, str(i))
            if row is None:
                errs.append(f"{key}: {cat} {i}")
                continue
            prefix = "M" if cat == "M" else "C"
            label = (row[0] if row[0].startswith(f"{prefix} ")
                     else f"{prefix} {i} ({row[0]})")
            items.append(_item(i, row, label))
        progs[key] = {"key": key, "title": title, "source": source, "items": items}

    h400 = [int(ln) for ln in (ROOT / "scripts/curated/herschel400.txt").read_text(
        encoding="utf-8").splitlines() if ln.strip().isdigit()]
    if len(h400) != 400:
        errs.append(f"herschel400: {len(h400)} números")
    items = []
    for k, ngc in enumerate(h400, 1):
        row = _row_by_designation(cx, "NGC", str(ngc))
        if row is None:
            errs.append(f"herschel400: NGC {ngc}")
            continue
        label = f"NGC {ngc}" + (f" ({row[0]})" if row[0] != f"NGC {ngc}" else "")
        items.append(_item(k, row, label))
    progs["herschel400"] = {"key": "herschel400", "title": "Herschel 400",
                            "source": "Astronomical League — Herschel 400 Observing Program",
                            "items": items}

    bino = []
    tsv = ROOT / "scripts/curated/tours/_binoculo.tsv"
    for line in tsv.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        spec = line.split("\t", 1)[0].strip()
        if not spec.startswith("dso:"):
            continue
        row = cx.execute("SELECT name, common, klass, type, con FROM objects WHERE name = ?",
                         (spec[4:],)).fetchone()
        if row is None:
            errs.append(f"binoculo: {spec}")
            continue
        bino.append(_item(len(bino) + 1, row))
    progs["binoculo"] = {"key": "binoculo", "title": "Céu ao binóculo",
                         "source": "Lista curada do Carina", "items": bino}
    if errs:
        raise SystemExit("não encontrados:\n  " + "\n  ".join(errs))
    return progs


def main() -> int:
    progs = build()
    OUT.mkdir(parents=True, exist_ok=True)
    for key, p in progs.items():
        (OUT / f"{key}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
        print(f"{p['title']}: {len(p['items'])} itens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
