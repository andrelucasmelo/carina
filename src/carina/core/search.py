"""Busca de objetos (v0.15 T6): a lógica, separada do diálogo.

Entende:

* nomes próprios e comuns ("Antares", "lagoa", "Andrômeda");
* designações de catálogo ("m42", "NGC 7000", "sh2-155", "b33", "c14",
  "hip 32349");
* **Bayer**: "alpha ori", "α Ori", "alf Ori", "alfa órion", "beta1 sco",
  "alpha orionis" (letra grega por extenso, abreviada, em português ou o
  próprio caractere; constelação pela sigla, pelo latim, pelo genitivo ou
  pelo nome em português);
* **constelações**: "órion", "orion", "ori", "cruzeiro" — o resultado leva
  ao centro da constelação e a destaca;
* corpos do Sistema Solar ("lua", "júpiter").

:func:`search` devolve :class:`Result` já ordenados: coincidências exatas
primeiro, depois corpos, estrelas, céu profundo e constelações parciais.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ..catalogs import names
from ..catalogs.constnames import CONSTELLATIONS
from ..catalogs.stars import GENITIVE, GREEK, GREEK_FULL, bayer_display

CATALOG_PREFIX = {
    "m": "M", "ngc": "NGC", "ic": "IC", "sh2": "SH2", "sh": "SH2", "b": "B",
    "mel": "Mel", "c": "C", "cr": "Cr", "col": "Cr", "ldn": "LDN", "vdb": "VdB",
    "abell": "Abell", "pk": "PK",
}

# letra grega -> código do HYG ("Alp"); por extenso, abreviado, em PT e o caractere
_GREEK_PT = {
    "alfa": "Alp", "gama": "Gam", "epsilon": "Eps", "teta": "The", "capa": "Kap",
    "mi": "Mu", "ni": "Nu", "csi": "Xi", "omicron": "Omi", "ro": "Rho",
    "ipsilon": "Ups", "fi": "Phi", "qui": "Chi", "omega": "Ome", "alf": "Alp",
}


def fold(text: str) -> str:
    """Minúsculas sem acentos (comparações tolerantes)."""
    norm = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in norm if not unicodedata.combining(c)).strip()


def _greek_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for code, char in GREEK.items():
        out[fold(code)] = code
        out[char] = code
        out[fold(GREEK_FULL[code])] = code
    for alias, code in _GREEK_PT.items():
        out[alias] = code
    return out


def _const_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for abbr, (latin, pt) in CONSTELLATIONS.items():
        out[fold(abbr)] = abbr
        out[fold(latin)] = abbr
        out[fold(pt)] = abbr
        if abbr in GENITIVE:
            out[fold(GENITIVE[abbr])] = abbr
    out["orion"] = "Ori"
    out["serpente"] = "Ser"
    return out


GREEK_ALIASES = _greek_aliases()
CONST_ALIASES = _const_aliases()


@dataclass
class Result:
    kind: str            # 'star' | 'dso' | 'body' | 'const'
    key: object
    label: str
    detail: str
    sort: tuple

    @property
    def selection(self) -> tuple:
        return (self.kind, self.key)


def parse_bayer(text: str) -> tuple[str, str, str] | None:
    """"alpha1 ori" → ("Alp", "1", "Ori"); None se não for Bayer."""
    t = fold(text)
    m = re.match(r"^([^\W\d_]+|[α-ω])\s*([0-9])?\s+(.+)$", t)
    if not m:
        # caractere grego colado: "αori", "α1 cen"
        m = re.match(r"^([α-ω])([0-9])?\s*(.+)$", t)
        if not m:
            return None
    letter, sub, con_text = m.group(1), m.group(2) or "", m.group(3).strip()
    con_text = re.sub(r"^(do|da|de|dos|das)\s+", "", con_text)
    code = GREEK_ALIASES.get(letter)
    con = CONST_ALIASES.get(con_text)
    if con is None and len(con_text) >= 3:
        # prefixo único: "alfa do cruzeiro" → Cruzeiro do Sul
        hits = {a for alias, a in CONST_ALIASES.items() if alias.startswith(con_text)}
        con = hits.pop() if len(hits) == 1 else None
    if code is None or con is None:
        return None
    return code, sub, con


def bayer_index(stars) -> dict[tuple[str, str, str], int]:
    """(código, sub, constelação) → índice da estrela (cacheado)."""
    cached = getattr(stars, "_bayer_index_cache", None)
    if cached is None:
        cached = {}
        for idx, code in stars.bayer.items():
            con = stars.con.get(idx)
            if not con:
                continue
            base, _, sub = code.partition("-")
            cached.setdefault((base, sub, con), idx)
            cached.setdefault((base, "", con), idx)   # "alpha cen" acha α¹
        stars._bayer_index_cache = cached
    return cached


def _dso_label(r) -> tuple[str, str]:
    from ..catalogs.dso import type_label

    label = r["name"]
    common = names.common_label(r["common"]) if r["common"] else ""
    if common:
        label += f" — {common}"
    return label, type_label(r["type"])


def search(text: str, stars, dso, limit: int = 40) -> list[Result]:
    """Resultados ordenados para a consulta (vazio com menos de 2 letras)."""
    from .engine import _BODIES

    text = text.strip()
    if len(text) < 2:
        return []
    tl = fold(text)
    out: list[Result] = []
    seen: set = set()

    def add(kind, key, label, detail, sort):
        if (kind, key) in seen:
            return
        seen.add((kind, key))
        out.append(Result(kind, key, label, detail, sort))

    # 1) Bayer exata: "alpha ori", "α Cen", "alfa do cruzeiro"…
    bay = parse_bayer(text)
    if bay is not None:
        idx = bayer_index(stars).get(bay)
        if idx is not None:
            mag = float(stars.mag[idx])
            name = stars.proper.get(idx)
            code = stars.bayer[idx]
            label = bayer_display(code, stars.con.get(idx))
            if name:
                label += f" — {name}"
            add("star", idx, label, f"estrela, mag {mag:.1f}", (0, mag))

    # 2) designação direta
    mm = re.match(r"^([a-z]+)[\s\-]*([0-9].*)$", tl)
    if mm:
        prefix, ident = mm.group(1), mm.group(2).strip()
        if prefix == "hip" and ident.isdigit():
            import numpy as np

            hits = np.nonzero(stars.hip == int(ident))[0]
            if len(hits):
                idx = int(hits[0])
                add("star", idx, f"HIP {int(ident)} — {stars.full_designation(idx)}",
                    f"estrela, mag {float(stars.mag[idx]):.1f}",
                    (0, float(stars.mag[idx])))
        cat = CATALOG_PREFIX.get(prefix)
        if cat:
            rows = dso.cx.execute(
                "SELECT o.id, o.name, o.type, o.mag, o.common, d.ident"
                " FROM designations d JOIN objects o ON o.id = d.object_id"
                " WHERE d.catalog = ? AND d.ident LIKE ?"
                " ORDER BY LENGTH(d.ident), d.ident LIMIT 12",
                (cat, ident + "%"),
            ).fetchall()
            for r in rows:
                label, detail = _dso_label(r)
                exact = fold(str(r["ident"])) == ident
                add("dso", int(r["id"]), label, detail,
                    (0 if exact else 3, r["mag"] if r["mag"] is not None else 99.0))

    # 3) constelação pelo nome inteiro (sigla, latim, genitivo, português)
    abbr = CONST_ALIASES.get(tl)
    if abbr is not None:
        latin, pt = CONSTELLATIONS[abbr]
        add("const", abbr, f"{pt} ({latin})", "constelação", (0, 0.0))

    # 4) corpos do Sistema Solar
    for name, _key, _color in _BODIES:
        if tl in fold(name):
            add("body", name, name, "Sistema Solar", (1, 0.0))

    # 5) estrelas por nome próprio
    for idx, nm in stars.proper.items():
        if tl in fold(nm):
            mag = float(stars.mag[idx])
            exact = fold(nm) == tl
            add("star", int(idx), nm, f"estrela, mag {mag:.1f}", (0 if exact else 2, mag))

    # 6) céu profundo por nome / nome comum (e nomes traduzidos)
    for r in dso.search(text=text, limit=25):
        label, detail = _dso_label(r)
        add("dso", int(r["id"]), label, detail,
            (4, r["mag"] if r["mag"] is not None else 99.0))
    for original in names.search_translations(text)[:10]:
        for r in dso.search(text=original, limit=3):
            label, detail = _dso_label(r)
            add("dso", int(r["id"]), label, detail,
                (4, r["mag"] if r["mag"] is not None else 99.0))

    # 7) constelações parciais ("cruz" → Cruzeiro do Sul)
    if len(tl) >= 3:
        for abbr, (latin, pt) in CONSTELLATIONS.items():
            if tl in fold(pt) or tl in fold(latin):
                add("const", abbr, f"{pt} ({latin})", "constelação", (5, 0.0))

    out.sort(key=lambda r: r.sort)
    return out[:limit]
