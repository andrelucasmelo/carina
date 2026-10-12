"""Confere um tour autoral antes do build (v0.23).

Lê um ``scripts/curated/tours/**/<chave>.md``, valida o esquema, resolve os
alvos e prepara o tour para o Rio de Janeiro (ou a latitude dada), listando
cada passo com o instante, a altura do alvo, o número de palavras e o que
seria pulado — para o autor ver se a noite escolhida de cada passo serve.

Uso:  python scripts/check_tour.py <arquivo.md | chave> [--lat -30] [--today 2026-10-15]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

DATA = ROOT / "data" / "processed"
EPHEM = ROOT / "data" / "ephemeris"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tour")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--today", default="2026-10-15")
    args = ap.parse_args()

    from build_tours import SRC, _Dso, parse_markdown

    from carina.catalogs import skygeometry
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core import localtime, lore
    from carina.core.engine import SkyEngine
    from carina.core.tours import Resolver, Tour, TourRun, validate

    path = Path(args.tour)
    if not path.exists():
        hits = list(SRC.rglob(f"{args.tour}.md"))
        if not hits:
            print(f"tour não encontrado: {args.tour}")
            return 1
        path = hits[0]
    tour = Tour.from_dict(parse_markdown(path.read_text(encoding="utf-8")))
    errs = validate(tour)
    stars = StarCatalog(DATA)
    res = Resolver(stars, _Dso(DATA / "dso.sqlite"), skygeometry.load_constellation_info(DATA),
                   json.loads((DATA / "asterisms.json").read_text(encoding="utf-8")))
    errs += [f"alvo não encontrado: {t}" for t in res.unresolved(tour)]
    for i, s in enumerate(tour.steps, 1):
        for cid in re.findall(r"\{lore(?::\w+)?:([A-Za-z]{3})\}", s.text):
            if lore.get(cid) is None:
                errs.append(f"passo {i}: sem história para {cid}")
    eng = SkyEngine(EPHEM)
    loc = ObserverLocation()
    if args.lat is not None:
        loc.latitude = args.lat
    if args.lon is not None:
        loc.longitude = args.lon
    eng.set_location(loc)
    localtime.set_timezone(loc.timezone)
    today = dt.datetime.fromisoformat(args.today + "T20:00").replace(
        tzinfo=dt.timezone(dt.timedelta(hours=-3))).astimezone(dt.timezone.utc)
    run = TourRun(tour, eng, res, today, latitude=loc.latitude).prepare()
    print(f"{tour.key}: {tour.title} — {len(tour.steps)} passos, "
          f"{len(run.steps)} preparados, {len(run.skipped)} pulados (lat {loc.latitude:.1f})")
    for w in run.warnings:
        print(f"  aviso: {w}")
    for p in run.steps:
        words = len(re.findall(r"\w+", lore.expand(p.step.text)))
        alt = "" if p.alt is None else f"alt {p.alt:5.1f}°"
        lt = localtime.to_local(p.when)
        flag = "  <-- palavras" if not 15 <= words <= 190 else ""
        print(f"  {p.number:2d}. {lt:%d/%m %H:%M}  {alt:11s} {words:3d} pal.  "
              f"{p.step.title}{flag}")
    for sk in run.skipped:
        print(f"  PULADO {sk.number}: {sk.title} — {sk.reason}")
    for e in errs:
        print(f"  ERRO: {e}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
