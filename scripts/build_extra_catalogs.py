"""Acrescenta ao banco os catálogos LDN, Collinder, van den Bergh e Abell.

Fontes (VizieR, coordenadas J2000 computadas pelo CDS):
  LDN  — VII/7A   (Lynds, nebulosas escuras)
  Cr   — VizieR J/A+A/../ (Collinder via lista de aglomerados abertos)
  VdB  — VII/21   (van den Bergh, nebulosas de reflexão)
  Abell— VII/110A (aglomerados de galáxias de Abell)

Objetos que já existem no banco (mesma posição) recebem apenas a designação
nova; os demais são inseridos. Os catálogos novos entram DESABILITADOS por
padrão na visualização (o app trata isso pela lista de catálogos visíveis).

Uso:
    python scripts/build_extra_catalogs.py [--force]
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "processed" / "dso.sqlite"
VIZIER = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"

MATCH_ARCMIN = 3.0     # raio para considerar "mesmo objeto"

# (catálogo, fonte VizieR, colunas extras, tipo, classe, prefixo do nome)
SOURCES = [
    ("LDN", "VII/7A/ldn", ["LDN", "Area"], "DrkN", "DARK", "LDN"),
    ("VdB", "VII/21/catalog", ["VdB", "Vmag"], "RfN", "NEB", "vdB"),
    ("Abell", "VII/110A/table3", ["ACO", "Rich"], "GGroup", "GAL", "Abell"),
]

# Collinder não tem tabela VizieR com identificadores; usamos o SIMBAD TAP
# (mesma abordagem do Melotte, ver build_dso.py).
SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
COLLINDER_QUERY = (
    "SELECT i.id AS cr, basic.ra, basic.dec, basic.otype_txt,"
    " basic.galdim_majaxis"
    " FROM ident AS i JOIN basic ON i.oidref = basic.oid"
    " WHERE i.id LIKE 'Cl Collinder %'"
)


def vizier_tsv(source: str, columns: list[str], dest: Path,
               force: bool) -> list[dict]:
    params = {
        "-source": source,
        "-out.max": "unlimited",
        "-out.add": "_RAJ2000,_DEJ2000",
        "-out": ",".join(columns),
    }
    url = f"{VIZIER}?{urllib.parse.urlencode(params)}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or force:
        print(f"  [dl] {source}")
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    rows: list[dict] = []
    header: list[str] | None = None
    for line in dest.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if header is None:
            header = [p.strip() for p in parts]
            continue
        if set(line.replace("\t", "")) <= {"-", " "}:
            continue
        if len(parts) < len(header):
            continue
        rows.append({h: p.strip() for h, p in zip(header, parts)})
    return rows


def ffloat(text) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cx = sqlite3.connect(DB)
    cx.row_factory = sqlite3.Row

    # índice espacial simples dos objetos existentes
    cell = math.radians(MATCH_ARCMIN * 4 / 60.0)
    index: dict[tuple, list[tuple]] = {}
    for row in cx.execute("SELECT id, ra, dec FROM objects"):
        ra, dec = row["ra"], row["dec"]
        key = (int(dec // cell),
               int(ra // (cell / max(math.cos(dec), 1e-3))))
        index.setdefault(key, []).append((row["id"], ra, dec))
    tol = math.radians(MATCH_ARCMIN / 60.0)

    def find_existing(ra: float, dec: float):
        base = (int(dec // cell),
                int(ra // (cell / max(math.cos(dec), 1e-3))))
        for dd in (-1, 0, 1):
            for dr in (-1, 0, 1):
                for oid, ora, odec in index.get((base[0] + dd, base[1] + dr), ()):
                    if abs(odec - dec) > tol:
                        continue
                    dra = (ora - ra) * math.cos(dec)
                    if math.hypot(dra, odec - dec) <= tol:
                        return oid
        return None

    def register(cat: str, ident: str, ra: float, dec: float, otype: str,
                 klass: str, prefix: str, size=None, mag=None) -> str:
        """Liga a designação a um objeto existente ou cria um novo."""
        oid = find_existing(ra, dec)
        status = "linked"
        if oid is None:
            cur = cx.execute(
                "INSERT INTO objects (name, type, klass, ra, dec, mag,"
                " maj, min, enabled, user_added)"
                " VALUES (?,?,?,?,?,?,?,?,1,0)",
                (f"{prefix} {ident}", otype, klass, ra, dec, mag, size, size),
            )
            oid = cur.lastrowid
            key = (int(dec // cell),
                   int(ra // (cell / max(math.cos(dec), 1e-3))))
            index.setdefault(key, []).append((oid, ra, dec))
            status = "added"
        cx.execute(
            "INSERT OR IGNORE INTO designations VALUES (?,?,?)",
            (oid, cat, ident),
        )
        return status

    totals = {}
    for cat, source, columns, otype, klass, prefix in SOURCES:
        try:
            rows = vizier_tsv(source, columns, RAW / f"{cat.lower()}.tsv",
                              args.force)
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] {cat}: {exc}")
            continue
        ident_col = columns[0]
        added = linked = 0
        for r in rows:
            ident = (r.get(ident_col) or "").strip()
            ra_deg = ffloat(r.get("_RAJ2000"))
            dec_deg = ffloat(r.get("_DEJ2000"))
            if not ident or ra_deg is None or dec_deg is None:
                continue
            ident = ident.replace(" ", "")
            ra, dec = math.radians(ra_deg), math.radians(dec_deg)
            oid = find_existing(ra, dec)
            if oid is None:
                size = ffloat(r.get("Diam")) or ffloat(r.get("Area"))
                if size and cat == "LDN":      # Area vem em graus quadrados
                    size = math.sqrt(size) * 60.0
                mag = ffloat(r.get("Vmag"))
                cur = cx.execute(
                    "INSERT INTO objects (name, type, klass, ra, dec, mag,"
                    " maj, min, enabled, user_added)"
                    " VALUES (?,?,?,?,?,?,?,?,1,0)",
                    (f"{prefix} {ident}", otype, klass, ra, dec, mag,
                     size, size),
                )
                oid = cur.lastrowid
                key = (int(dec // cell),
                       int(ra // (cell / max(math.cos(dec), 1e-3))))
                index.setdefault(key, []).append((oid, ra, dec))
                added += 1
            else:
                linked += 1
            cx.execute(
                "INSERT OR IGNORE INTO designations VALUES (?,?,?)",
                (oid, cat, ident),
            )
        cx.commit()
        totals[cat] = (added, linked)
        print(f"  {cat}: {added} novos, {linked} ligados a objetos existentes")

    # --- Collinder via SIMBAD TAP ---
    try:
        import csv
        import io
        import re

        params = {"request": "doQuery", "lang": "adql", "format": "csv",
                  "query": COLLINDER_QUERY}
        dest = RAW / "collinder.csv"
        if not dest.exists() or args.force:
            print("  [dl] SIMBAD: Collinder")
            resp = requests.get(
                f"{SIMBAD_TAP}?{urllib.parse.urlencode(params)}", timeout=300
            )
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        added = linked = 0
        seen: set[str] = set()
        for r in csv.DictReader(io.StringIO(dest.read_text("utf-8"))):
            num = re.sub(r"^Cl Collinder\s+", "", r["cr"]).strip()
            if not re.fullmatch(r"\d+", num) or num in seen:
                continue          # ignora identificadores de estrelas soltas
            ra_deg, dec_deg = ffloat(r.get("ra")), ffloat(r.get("dec"))
            if ra_deg is None or dec_deg is None:
                continue
            seen.add(num)
            status = register(
                "Cr", num, math.radians(ra_deg), math.radians(dec_deg),
                (r.get("otype_txt") or "OpC").strip(), "OC", "Cr",
                size=ffloat(r.get("galdim_majaxis")),
            )
            added += status == "added"
            linked += status == "linked"
        cx.commit()
        totals["Cr"] = (added, linked)
        print(f"  Cr: {added} novos, {linked} ligados a objetos existentes")
    except Exception as exc:  # noqa: BLE001
        print(f"  [!] Collinder: {exc}")

    for cat in totals:
        n = cx.execute(
            "SELECT COUNT(DISTINCT object_id) c FROM designations"
            " WHERE catalog = ?", (cat,),
        ).fetchone()["c"]
        print(f"  total {cat}: {n}")
    print("total de objetos:",
          cx.execute("SELECT COUNT(*) c FROM objects").fetchone()["c"])
    cx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
