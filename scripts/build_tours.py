"""Tours autorais em Markdown → ``data/processed/tours/*.json`` (v0.20).

Cada arquivo ``scripts/curated/tours/<categoria>/<chave>.md`` é um tour:

    ---
    key: orion
    title: Órion, o caçador
    subtitle: A constelação mais fácil do verão
    category: iniciante
    level: 1
    minutes: 8
    when: data:01-15 hora:21:30
    lat_range: -40, 15
    tags: constelação, verão
    ---

    ## Título do passo
    @target: const:Ori
    @fov: 50
    @highlight: const:Ori, asterism:tres-marias
    @time: +1h
    @layers: const_names=1, asterisms=1
    @kind: highlight
    @optional: no
    @image: dss:M 42
    @skip_if_below: 10
    @time: data:07-15 hora:21:00   (outra noite do ano do tour)  ou  em:2026-11-03T20:15
    @fov_circle: 6                 (campo de binóculo desenhado)
    @setup_fov: sim                (campo do setup ativo desenhado no alvo)
    @finder: sim                   (acrescenta a rota a partir das estrelas)

    Texto do passo em Markdown. {lore:Ori} insere a história da constelação.

O build confere o esquema (``core.tours.validate``), resolve TODOS os alvos
no catálogo embarcado (estrelas, céu profundo, constelações, asterismos) e
falha (código 1) se algo não existir — um tour embarcado nunca aponta para
o vazio. ``--check`` só valida, sem gravar.

Uso:  python scripts/build_tours.py [--check]
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SRC = ROOT / "scripts" / "curated" / "tours"
DATA = ROOT / "data" / "processed"
OUT = DATA / "tours"


class _Dso:
    """O mínimo do DsoCatalog que o Resolver usa: a conexão ao banco."""

    def __init__(self, path: Path) -> None:
        self.cx = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.cx.row_factory = sqlite3.Row


def _value(raw: str):
    raw = raw.strip()
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw


def parse_markdown(text: str) -> dict:
    """Markdown de um tour → dicionário no esquema de ``core.tours.Tour``."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        raise ValueError("cabeçalho --- ausente")
    head, body = m.groups()
    tour: dict = {"steps": []}
    for line in head.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key == "lat_range":
            tour[key] = [float(x) for x in val.split(",")]
        elif key == "tags":
            tour[key] = [t.strip() for t in val.split(",") if t.strip()]
        else:
            tour[key] = _value(val)
    for block in re.split(r"^## ", body, flags=re.M)[1:]:
        lines = block.splitlines()
        step: dict = {"title": lines[0].strip()}
        text_lines = []
        for line in lines[1:]:
            am = re.match(r"^@(\w+):\s*(.*)$", line)
            if am and not text_lines:
                k, v = am.group(1), am.group(2).strip()
                if k == "highlight":
                    step[k] = [h.strip() for h in v.split(",") if h.strip()]
                elif k == "layers":
                    step[k] = {kv.split("=")[0].strip(): kv.split("=")[1].strip() in ("1", "sim", "on")
                               for kv in v.split(",") if "=" in kv}
                elif k == "optional":
                    step[k] = v.lower() not in ("no", "não", "nao", "0", "false")
                elif k in ("fov", "duration_s", "skip_if_below", "fov_circle"):
                    step[k] = float(v)
                elif k in ("setup_fov", "finder"):
                    step[k] = v.lower() in ("1", "sim", "yes", "true")
                elif k == "bortle":
                    step[k] = int(v)
                else:
                    step[k] = v
                continue
            if am is None or text_lines:
                text_lines.append(line)
        step["text"] = "\n".join(text_lines).strip()
        tour["steps"].append(step)
    return tour


def parse_texts(path: Path) -> dict[str, str]:
    """``_textos.md``: seções ``## chave`` com um parágrafo de texto cada."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
        lines = block.splitlines()
        out[lines[0].strip()] = "\n".join(lines[1:]).strip()
    return out


def parse_tsv(path: Path) -> list[tuple[str, str]]:
    """``_binoculo.tsv``: alvo e texto separados por tabulação."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            spec, _, text = line.partition("	")
            rows.append((spec.strip(), text.strip()))
    return rows


def build(check_only: bool = False) -> list[dict]:
    from carina.catalogs import skygeometry
    from carina.catalogs.stars import StarCatalog
    from carina.core import lore
    from carina.core.tours import Resolver, Tour, validate

    stars = StarCatalog(DATA)
    asterisms = json.loads((DATA / "asterisms.json").read_text(encoding="utf-8"))
    res = Resolver(stars, _Dso(DATA / "dso.sqlite"),
                   skygeometry.load_constellation_info(DATA), asterisms)
    out, errs = [], []
    keys: set[str] = set()
    texts = parse_texts(SRC / "_textos.md")
    bino = parse_tsv(SRC / "_binoculo.tsv")
    for spec, _txt in bino:
        if res.resolve(spec) is None:
            errs.append(f"_binoculo.tsv: alvo não encontrado {spec}")
    for key in texts:
        if key.startswith("estrela:") and res.star_index(key[8:]) is None:
            errs.append(f"_textos.md: estrela desconhecida {key[8:]}")
    for f in sorted(SRC.rglob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            d = parse_markdown(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            errs.append(f"{f.name}: {exc}")
            continue
        tour = Tour.from_dict(d)
        if tour.key in keys:
            errs.append(f"{f.name}: chave repetida {tour.key}")
        keys.add(tour.key)
        errs += [f"{f.name}: {e}" for e in validate(tour)]
        errs += [f"{f.name}: alvo não encontrado {t}" for t in res.unresolved(tour)]
        for i, s in enumerate(tour.steps, 1):
            for cid in re.findall(r"\{lore(?::\w+)?:([A-Za-z]{3})\}", s.text):
                if lore.get(cid) is None:
                    errs.append(f"{f.name} passo {i}: sem história para {cid}")
        out.append(d)
    if errs:
        raise SystemExit("problemas nos tours:\n  " + "\n  ".join(errs))
    if not check_only:
        OUT.mkdir(parents=True, exist_ok=True)
        for old in OUT.glob("*.json"):
            if not old.name.startswith("_"):
                old.unlink()
        for d in out:
            (OUT / f"{d['key']}.json").write_text(
                json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        (OUT / "_textos.json").write_text(json.dumps(texts, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
        (OUT / "_binoculo.json").write_text(
            json.dumps([{"target": t, "text": x} for t, x in bino], ensure_ascii=False,
                       indent=1), encoding="utf-8")
    return out


def main() -> int:
    tours = build(check_only="--check" in sys.argv)
    steps = sum(len(t["steps"]) for t in tours)
    print(f"{len(tours)} tours, {steps} passos" + ("" if "--check" in sys.argv
                                                    else f" → {OUT.relative_to(ROOT)}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
