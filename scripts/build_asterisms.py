"""Asterismos e alinhamentos curados → ``data/processed/`` (v0.20 T3, v0.23).

Lê ``scripts/curated/asterisms.tsv`` (nomes próprios, Bayer ou HIP),
resolve cada estrela no catálogo HYG embarcado e grava as polilinhas como
números HIP. Falha (código 1) se alguma estrela não for encontrada — o
JSON embarcado nunca tem um traço quebrado.

Lê também ``scripts/curated/alignments.tsv`` — as "setas" para achar uma
estrela ou um ponto a partir de outras (braço do Cruzeiro × 4,5 até o polo,
Três Marias → Sirius…) — e grava ``alignments.json`` com os arcos já
calculados (vetores ICRS a cada ~1°) e os rótulos das pontas.

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
SRC_ALIGN = ROOT / "scripts" / "curated" / "alignments.tsv"
OUT_ALIGN = ROOT / "data" / "processed" / "alignments.json"


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


# ---------------------------------------------------------------------------
# Alinhamentos
# ---------------------------------------------------------------------------

def _unit(v):
    import numpy as np

    v = np.asarray(v, np.float64)
    return v / np.linalg.norm(v)


def _radec(ra_deg: float, dec_deg: float):
    import math

    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    return _unit([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


def _arc(a, b, step_deg: float = 1.0) -> list:
    """Pontos do arco de círculo máximo de ``a`` a ``b`` (slerp)."""
    import math

    import numpy as np

    ang = math.acos(max(-1.0, min(1.0, float(a @ b))))
    n = max(2, int(math.degrees(ang) / step_deg) + 2)
    if ang < 1e-9:
        return [a, b]
    out = []
    for k in range(n):
        t = k / (n - 1)
        out.append((math.sin((1 - t) * ang) * a + math.sin(t * ang) * b) / math.sin(ang))
    return [_unit(p) for p in out] if out else [a, b]


def _extend(a, b, k: float):
    """O ponto além de B, a ``k`` vezes a distância A-B (contada a partir de
    B) — "prolongue o braço maior quatro vezes e meia"."""
    import math

    import numpy as np

    ang = math.acos(max(-1.0, min(1.0, float(a @ b))))
    axis = _unit(np.cross(a, b))
    th = (1.0 + k) * ang
    # rotação de A em torno do eixo (Rodrigues)
    return _unit(a * math.cos(th) + np.cross(axis, a) * math.sin(th)
                 + axis * float(axis @ a) * (1 - math.cos(th)))


def parse_alignments(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("	")
        if len(parts) != 4:
            raise SystemExit(f"alinhamento com {len(parts)} colunas: {line[:60]}")
        key, name, segs, text = (p.strip() for p in parts)
        rows.append({"key": key, "name": name, "text": text,
                     "segments": [x.strip() for x in segs.split("|") if x.strip()]})
    return rows


def build_alignments() -> list[dict]:
    import re
    import sqlite3

    from carina.catalogs.stars import StarCatalog
    from carina.core.tours import Resolver

    data = ROOT / "data" / "processed"
    stars = StarCatalog(data)
    res = Resolver(stars, dso=None)
    cx = sqlite3.connect(f"file:{data / 'dso.sqlite'}?mode=ro", uri=True)
    errs: list[str] = []

    def star(spec: str, where: str):
        i = res.star_index(spec)
        if i is None:
            errs.append(f"{where}: estrela {spec!r}")
            return None
        return _unit(stars.xyz[i])

    def point(spec: str, where: str):
        spec = spec.strip()
        if spec == "polo_sul":
            return _unit([0.0, 0.0, -1.0])
        if spec == "polo_norte":
            return _unit([0.0, 0.0, 1.0])
        if spec.startswith("radec:"):
            ra, dec = (float(x) for x in spec[6:].split(","))
            return _radec(ra, dec)
        if spec.startswith("dso:"):
            row = cx.execute("SELECT ra, dec FROM objects WHERE name = ? COLLATE NOCASE",
                             (spec[4:].strip(),)).fetchone()
            if row is None:
                errs.append(f"{where}: objeto {spec!r}")
                return None
            import math

            return _radec(math.degrees(row[0]), math.degrees(row[1]))
        if spec.startswith("meio:"):
            a, b = (star(x, where) for x in spec[5:].split("+"))
            return None if a is None or b is None else _unit(a + b)
        return star(spec, where)

    out = []
    for al in parse_alignments(SRC_ALIGN):
        lines, labels = [], []
        for seg in al["segments"]:
            where = f"{al['key']} [{seg}]"
            label = ""
            if "@" in seg:
                seg, label = (x.strip() for x in seg.split("@", 1))
            m = re.fullmatch(r"(.+?)>(.+?)(?:\*([\d.]+))?", seg)
            if not m:
                errs.append(f"{where}: segmento ilegível")
                continue
            src, dst, k = m.group(1).strip(), m.group(2).strip(), m.group(3)
            if src.startswith("mediatriz:"):
                a, b = (star(x, where) for x in src[10:].split("+"))
                target = point(dst, where)
                if a is None or b is None or target is None:
                    continue
                import numpy as np

                n = _unit(a - b)                   # plano dos pontos equidistantes
                start = _unit(a + b)
                end = _unit(target - float(target @ n) * n)
            else:
                start, end = point(src, where), point(dst, where)
                if start is None or end is None:
                    continue
                if k:
                    end = _extend(start, end, float(k))
            pts = _arc(start, end)
            lines.append([[round(float(c), 6) for c in p] for p in pts])
            if label:
                labels.append({"text": label, "xyz": [round(float(c), 6) for c in end]})
        out.append({"key": al["key"], "name": al["name"], "text": al["text"],
                    "lines": lines, "labels": labels})
    if errs:
        raise SystemExit("alinhamentos com problemas:\n  " + "\n  ".join(errs))
    return out


def main() -> int:
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data)} asterismos → {OUT.relative_to(ROOT)}")
    if SRC_ALIGN.exists():
        al = build_alignments()
        OUT_ALIGN.write_text(json.dumps(al, ensure_ascii=False), encoding="utf-8")
        print(f"{len(al)} alinhamentos → {OUT_ALIGN.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
