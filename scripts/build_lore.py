"""Histórias das constelações → ``data/processed/constellation_lore_pt.json``
(v0.20 T4).

Lê ``scripts/curated/constellation_lore_pt.md`` (uma seção ``## Sigla``
por constelação, campos ``origem``, ``historia``, ``achar`` e
``curiosidade``) e confere: as 88 siglas IAU, nenhum campo vazio, origem
num conjunto fechado. Falha (código 1) se algo estiver errado.

Uso:  python scripts/build_lore.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "scripts" / "curated" / "constellation_lore_pt.md"
OUT = ROOT / "data" / "processed" / "constellation_lore_pt.json"

ORIGINS = {
    "ptolomeu": "Uma das 48 constelações do Almagesto de Ptolomeu (século II).",
    "argo": "Parte da antiga Argo Navis de Ptolomeu, dividida em três por Lacaille (1756).",
    "navegadores": "Criada com as observações dos navegadores holandeses Keyser e Houtman "
                   "(1595–1597) e publicada por Plancius e por Bayer (1603).",
    "plancius": "Introduzida pelo cartógrafo Petrus Plancius (fim do século XVI e "
                "começo do XVII).",
    "hevelius": "Introduzida por Johannes Hevelius no atlas Firmamentum Sobiescianum (1690).",
    "lacaille": "Introduzida por Nicolas-Louis de Lacaille, que mapeou o céu austral "
                "da Cidade do Cabo (1751–1752).",
    "renascimento": "Reconhecida como constelação no Renascimento (Vopel, 1536; Tycho "
                    "Brahe, 1602), com uma história já contada na Antiguidade.",
}
FIELDS = ("origem", "historia", "achar", "curiosidade")


def parse(text: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^##\s+([A-Za-z]{3})\s*$", line)
        if m:
            cur = m.group(1)
            if cur in out:
                raise SystemExit(f"sigla repetida: {cur}")
            out[cur] = {}
            continue
        m = re.match(r"^(origem|historia|achar|curiosidade):\s*(.*)$", line)
        if m and cur:
            out[cur][m.group(1)] = m.group(2).strip()
    return out


def build() -> dict[str, dict]:
    data = parse(SRC.read_text(encoding="utf-8"))
    ids = {c["id"] for c in json.loads(
        (ROOT / "data" / "processed" / "constellations.json").read_text(encoding="utf-8"))}
    errs = [f"falta {c}" for c in sorted(ids - set(data))]
    errs += [f"sigla desconhecida {c}" for c in sorted(set(data) - ids)]
    for cid, d in data.items():
        for f in FIELDS:
            if not d.get(f):
                errs.append(f"{cid}: campo vazio {f}")
        if d.get("origem") not in ORIGINS:
            errs.append(f"{cid}: origem {d.get('origem')!r}")
    if errs:
        raise SystemExit("problemas:\n  " + "\n  ".join(errs))
    return {cid: {"origin": d["origem"], "origin_text": ORIGINS[d["origem"]],
                  "history": d["historia"], "find": d["achar"],
                  "curiosity": d["curiosidade"]}
            for cid, d in sorted(data.items())}


def main() -> int:
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data)} constelações → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
