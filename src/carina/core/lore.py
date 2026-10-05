"""Histórias das constelações (v0.20 T4).

Dados em ``data/processed/constellation_lore_pt.json`` (gerados por
``scripts/build_lore.py``): para cada sigla IAU, a origem histórica, a
história, como achar do Brasil e uma curiosidade. Usados na ficha (ao
identificar ou buscar uma constelação) e nos passos de tour
(``{lore:Ori}`` no texto).
"""

from __future__ import annotations

import html
import json
import re

_LORE: dict | None = None


def load() -> dict[str, dict]:
    global _LORE
    if _LORE is None:
        from ..config import package_data_dir

        path = package_data_dir() / "constellation_lore_pt.json"
        try:
            _LORE = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            _LORE = {}
    return _LORE


def get(cid: str) -> dict | None:
    return load().get(cid)


def as_markdown(cid: str, with_find: bool = True) -> str:
    """Texto pronto para um passo de tour ou para a ficha."""
    d = get(cid)
    if d is None:
        return ""
    parts = [d["history"]]
    if with_find:
        parts.append(f"**Como achar.** {d['find']}")
    parts.append(f"**Curiosidade.** {d['curiosity']}")
    parts.append(f"*{d['origin_text']}*")
    return "\n\n".join(parts)


def as_html(cid: str) -> str:
    d = get(cid)
    if d is None:
        return ""
    e = html.escape
    return (f"<p>{e(d['history'])}</p>"
            f"<p><b>Como achar.</b> {e(d['find'])}</p>"
            f"<p><b>Curiosidade.</b> {e(d['curiosity'])}</p>"
            f"<p style='color:#8a93a5'><i>{e(d['origin_text'])}</i></p>")


_PLACEHOLDER = re.compile(r"\{lore(?::(find|short))?:([A-Za-z]{3})\}")


def expand(text: str) -> str:
    """Substitui ``{lore:Ori}`` (história completa), ``{lore:short:Ori}`` (sem
    o "como achar") e ``{lore:find:Ori}`` (só como achar) num texto Markdown."""
    def repl(m: re.Match) -> str:
        mode, cid = m.group(1), m.group(2)
        d = get(cid)
        if d is None:
            return ""
        if mode == "find":
            return d["find"]
        return as_markdown(cid, with_find=mode != "short")

    return _PLACEHOLDER.sub(repl, text)
