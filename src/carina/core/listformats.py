"""Importar e exportar listas de observação (v0.22 T5).

Três formatos:

- **CSV do Carina** — ``nome;tipo;identidade;AR (graus);Dec (graus);nota``
  (separador ``;``, UTF-8 com BOM para o Excel brasileiro);
- **Telescopius** — o CSV das listas do site (colunas "Catalogue Entry",
  "Familiar Name", "Right Ascension", "Declination"…); na importação vale a
  primeira coluna reconhecida;
- **SkySafari** — o ``.skylist`` (``SkyObject=BeginObject`` …
  ``CatalogNumber=…`` … ``EndObject=SkyObject``).

Na importação os nomes são resolvidos pela mesma busca do programa
(``core.search``): "M 42", "NGC 253", "Sirius", "Plêiades"…
"""

from __future__ import annotations

import csv
import io
import math
import re

FORMATS = {"csv": "CSV do Carina (*.csv)", "telescopius": "Telescopius (*.csv)",
           "skylist": "SkySafari (*.skylist)"}


def _deg(rad) -> str:
    return "" if rad is None else f"{math.degrees(float(rad)):.5f}"


def _hms(ra_rad: float) -> str:
    h = (math.degrees(ra_rad) % 360.0) / 15.0
    hh = int(h)
    mm = int((h - hh) * 60)
    ss = ((h - hh) * 60 - mm) * 60
    return f"{hh:02d}h {mm:02d}m {ss:04.1f}s"


def _dms(dec_rad: float) -> str:
    d = math.degrees(dec_rad)
    s = "-" if d < 0 else "+"
    d = abs(d)
    dd = int(d)
    mm = int((d - dd) * 60)
    ss = ((d - dd) * 60 - mm) * 60
    return f"{s}{dd:02d}° {mm:02d}' {ss:04.1f}\""


def _designation(item: dict) -> str:
    """Designação curta para outros programas (sem o nome popular)."""
    name = item.get("ident") or item.get("name", "")
    if item.get("kind") == "star" and name.startswith("HIP "):
        return item.get("name", name).split(" — ")[0]
    return name


# -- exportar ---------------------------------------------------------------------

def export_csv(items: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["nome", "tipo", "identidade", "ar_graus", "dec_graus", "nota"])
    for it in items:
        w.writerow([it.get("name", ""), it.get("kind", ""), it.get("ident", ""),
                    _deg(it.get("ra")), _deg(it.get("dec")), it.get("note", "") or ""])
    return buf.getvalue()


def export_telescopius(items: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=",", lineterminator="\n")
    w.writerow(["Catalogue Entry", "Familiar Name", "Right Ascension", "Declination"])
    for it in items:
        name = it.get("name", "")
        common = name.split(" — ", 1)[1] if " — " in name else ""
        ra, dec = it.get("ra"), it.get("dec")
        w.writerow([_designation(it), common, _hms(ra) if ra is not None else "",
                    _dms(dec) if dec is not None else ""])
    return buf.getvalue()


def export_skylist(items: list[dict]) -> str:
    out = ["SkySafariObservingListVersion=3.0", "SortedBy=Default Order"]
    for it in items:
        code = "2" if it.get("kind") == "star" else "4"
        out += ["SkyObject=BeginObject", f"\tObjectID={code},-1,-1",
                f"\tCommonName={it.get('name', '').split(' — ')[-1]}",
                f"\tCatalogNumber={_designation(it)}", "EndObject=SkyObject"]
    return "\n".join(out) + "\n"


def export(fmt: str, items: list[dict]) -> str:
    return {"csv": export_csv, "telescopius": export_telescopius,
            "skylist": export_skylist}[fmt](items)


# -- importar ---------------------------------------------------------------------

def import_names(fmt: str, text: str) -> list[str]:
    """Os nomes/designações do arquivo, na ordem."""
    text = text.lstrip("﻿")
    if fmt == "skylist":
        names, cur = [], []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("SkyObject=BeginObject"):
                cur = []
            elif line.startswith("CatalogNumber=") or line.startswith("CommonName="):
                cur.append(line.split("=", 1)[1].strip())
            elif line.startswith("EndObject"):
                cat = [c for c in cur if re.match(r"^(M|NGC|IC|C|HIP|HD|Mel|Cr)\s*\d", c)]
                pick = (cat or cur)[:1]
                names += pick
        return [n for n in names if n]
    delim = ";" if fmt == "csv" or (text.count(";") > text.count(",")) else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    keys = ("identidade", "nome", "catalogue entry", "familiar name", "name", "object", "objeto")
    col = next((head.index(k) for k in keys if k in head), None)
    body = rows[1:] if col is not None else rows
    col = 0 if col is None else col
    alt = head.index("familiar name") if "familiar name" in head else None
    out = []
    for r in body:
        val = r[col].strip() if col < len(r) else ""
        if not val and alt is not None and alt < len(r):
            val = r[alt].strip()
        if val:
            out.append(val)
    return out


def resolve(names: list[str], stars, dso) -> tuple[list[dict], list[str]]:
    """Nomes → itens de lista (kind, ident, name, ra, dec); e os não achados."""
    from .objects import ObjectRef
    from .search import search

    found, missing = [], []
    for n in names:
        res = [r for r in search(n, stars, dso, limit=5) if r.kind in ("star", "dso", "body")]
        if not res:
            missing.append(n)
            continue
        ref = ObjectRef.resolve((res[0].kind, res[0].key), stars, dso)
        if ref is None:
            missing.append(n)
            continue
        rd = ref.ra_dec or (None, None)
        found.append({"kind": ref.kind, "ident": ref.ident, "name": ref.name,
                      "ra": rd[0], "dec": rd[1]})
    return found, missing
