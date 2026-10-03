"""Gera a base planetária embarcada (v0.18, ADR-048).

Fontes (baixadas para ``data/raw/planets``):

- **JPL/NAIF**, efemérides de satélites ``jup365.bsp`` e ``sat441.bsp``
  (domínio público). Só o trecho 2000–2060 é baixado, por requisições
  parciais (``python -m jplephem excerpt``), e as órbitas são reajustadas
  aqui em polinômios de Chebyshev compactos (float32), um segmento por
  período orbital: ~12 MB em vez de ~33 MB, com erro de algumas dezenas
  de km (o raio de Júpiter tem 71 492 km);
- **Solar System Scope** — texturas 2k dos planetas e o perfil dos anéis
  de Saturno (CC BY 4.0, baseadas em mosaicos da NASA);
- **JUPOS** (via a tabela de B. Gray/Project Pluto) — longitude da Grande
  Mancha Vermelha no Sistema II, 2010–2025.

Saída em ``data/processed/planets/``: ``moons_jupiter.npz``,
``moons_saturn.npz``, as texturas e ``grs.json``.

Uso:
    python scripts/build_planets.py [--download]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "planets"
OUT = ROOT / "data" / "processed" / "planets"

START, END = "2000/1/1", "2060/1/1"
NAIF_SAT = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/satellites/"
SSS = "https://www.solarsystemscope.com/textures/download/"

SYSTEMS = {
    # sistema: (arquivo NAIF, centro do planeta, luas [(id, nome, período d, grau)])
    "jupiter": ("jup365.bsp", 599, [
        (501, "Io", 1.769138, 10), (502, "Europa", 3.551181, 10),
        (503, "Ganimedes", 7.154553, 10), (504, "Calisto", 16.689018, 12)]),
    "saturn": ("sat441.bsp", 699, [
        (601, "Mimas", 0.942422, 10), (602, "Encélado", 1.370218, 10),
        (603, "Tétis", 1.887802, 10), (604, "Dione", 2.736915, 10),
        (605, "Reia", 4.517500, 10), (606, "Titã", 15.945421, 14),
        (607, "Hipérion", 21.276609, 14), (608, "Jápeto", 79.330183, 14)]),
}

TEXTURES = {
    "mercury.jpg": "2k_mercury.jpg", "venus.jpg": "2k_venus_atmosphere.jpg",
    "mars.jpg": "2k_mars.jpg", "jupiter.jpg": "2k_jupiter.jpg",
    "saturn.jpg": "2k_saturn.jpg", "saturn_ring.png": "2k_saturn_ring_alpha.png",
    "uranus.jpg": "2k_uranus.jpg", "neptune.jpg": "2k_neptune.jpg",
}

# Longitude (Sistema II, desenrolada) da GMV: JUPOS via Project Pluto
# (https://www.projectpluto.com/grs_lon.txt), 2010–2025
GRS_TABLE = [
    ("2010-10-10", 156), ("2011-02-01", 163), ("2011-08-01", 168), ("2012-01-01", 174),
    ("2012-08-01", 182), ("2013-10-01", 202), ("2014-02-01", 209), ("2014-04-01", 212),
    ("2014-09-01", 216), ("2015-01-01", 226), ("2015-05-01", 227), ("2015-12-01", 236),
    ("2016-04-01", 244), ("2016-09-01", 253), ("2016-12-01", 258), ("2017-08-01", 276),
    ("2017-10-01", 280), ("2018-04-01", 288), ("2018-06-01", 288), ("2018-11-01", 296),
    ("2019-01-01", 300), ("2019-05-01", 309), ("2019-07-01", 313), ("2019-09-01", 315),
    ("2019-11-01", 320), ("2020-04-01", 330), ("2020-08-01", 339), ("2020-12-01", 347),
    ("2021-04-01", 357), ("2021-09-01", 362), ("2021-12-01", 365), ("2022-05-01", 374),
    ("2022-11-01", 386), ("2024-01-01", 410), ("2024-10-01", 421), ("2025-12-01", 439),
]
GRS_DRIFT_DEG_YEAR = 16.0
# posição da GMV na textura (fração da largura), medida na imagem
GRS_TEXTURE_U = 0.3635
# raios (km) das bordas do perfil dos anéis: ajustados para que o início do
# anel C (74 658 km), a divisão de Cassini (~118 000) e a borda do anel A
# (136 775) caiam onde o perfil mostra
RING_INNER_KM, RING_OUTER_KM = 70517.0, 139536.0


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for system, (fname, center, moons) in SYSTEMS.items():
        out = RAW / f"{system}_2000_2060.bsp"
        if out.exists():
            continue
        targets = ",".join(str(m[0]) for m in moons) + f",{center}"
        subprocess.run([sys.executable, "-m", "jplephem", "excerpt", "--targets", targets,
                        START, END, NAIF_SAT + fname, str(out)], check=True)
    for src in TEXTURES.values():
        p = RAW / src
        if not p.exists():
            with urllib.request.urlopen(SSS + src) as resp:
                p.write_bytes(resp.read())


def fit_system(system: str) -> dict:
    from numpy.polynomial import chebyshev as C
    from jplephem.spk import SPK

    fname, center, moons = SYSTEMS[system]
    spk = SPK.open(str(RAW / f"{system}_2000_2060.bsp"))
    # o sat441 tem dois segmentos por lua (antes e depois de 2025); o
    # recorte rotula os dois com o mesmo intervalo, então a cobertura real
    # vem dos registros de cada um
    pieces: dict[int, list] = {}
    for sg in spk.segments:
        init, intlen, coeffs = sg.load_array()
        a_jd = float(init)                              # dias julianos (TDB)
        b_jd = a_jd + float(intlen) * coeffs.shape[1]
        pieces.setdefault(sg.target, []).append((a_jd, b_jd, sg))

    class _Seg:
        def __init__(self, parts):
            self.parts = parts

        def compute(self, t):
            t = np.asarray(t, dtype=np.float64)
            out = np.empty((3,) + t.shape)
            done = np.zeros(t.shape, bool)
            for a_jd, b_jd, sg in self.parts:
                m = (~done) & (t >= a_jd) & (t <= b_jd)
                if m.any():
                    out[:, m] = sg.compute(t[m])
                    done |= m
            assert done.all(), "instante fora da cobertura"
            return out

    seg = {k: _Seg(v) for k, v in pieces.items()}
    t_start = max(min(a for a, _b, _s in v) for v in pieces.values())
    t_end = min(max(b for _a, b, _s in v) for v in pieces.values())
    out = {"t_start": np.float64(t_start), "t_end": np.float64(t_end),
           "names": np.array([m[1] for m in moons]), "ids": np.array([m[0] for m in moons])}
    rng = np.random.default_rng(7)
    report = []
    for mid, name, period, deg in moons:
        L = period
        n = int((t_end - t_start) / L)
        nodes = np.cos(np.pi * (np.arange(deg + 1) + 0.5) / (deg + 1))
        tt = t_start + (np.arange(n)[:, None] + (nodes[None, :] + 1) / 2) * L
        flat = tt.ravel()
        pos = seg[mid].compute(flat) - seg[center].compute(flat)       # (3, n*(deg+1)) km
        pos = pos.reshape(3, n, deg + 1)
        # ajuste por mínimos quadrados exatos nos nós (= interpolação)
        V = C.chebvander(nodes, deg)                                      # (deg+1, deg+1)
        inv = np.linalg.inv(V)
        coef = np.einsum("kj,inj->nik", inv, pos).astype(np.float32)     # (n, 3, deg+1)
        out[f"coef_{mid}"] = coef
        out[f"len_{mid}"] = np.float64(L)
        # conferência em instantes aleatórios
        t = rng.uniform(t_start, t_start + n * L - 1e-6, 3000)
        i = ((t - t_start) / L).astype(int)
        x = 2 * ((t - t_start) / L - i) - 1
        T = C.chebvander(x, deg)                                          # (m, deg+1)
        fit = np.einsum("mk,mik->im", T, coef[i].astype(np.float64))
        true = seg[mid].compute(t) - seg[center].compute(t)
        err = float(np.abs(fit - true).max())
        report.append((name, err, coef.nbytes / 1e6))
        # 400 km = 0,006 raio de Júpiter ou 0,007 de Saturno: invisível
        assert err < 400.0, (name, err)
    return out, report


def build_textures() -> None:
    for dst, src in TEXTURES.items():
        shutil.copyfile(RAW / src, OUT / dst)


def build_grs() -> None:
    (OUT / "grs.json").write_text(json.dumps({
        "source": "JUPOS (jupos.privat.t-online.de) via projectpluto.com/grs_lon.txt",
        "system": "II",
        "table": GRS_TABLE,
        "drift_deg_per_year": GRS_DRIFT_DEG_YEAR,
        "texture_u": GRS_TEXTURE_U,
        "ring_inner_km": RING_INNER_KM, "ring_outer_km": RING_OUTER_KM,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()
    if args.download:
        download()
    OUT.mkdir(parents=True, exist_ok=True)
    for system in SYSTEMS:
        data, report = fit_system(system)
        np.savez_compressed(OUT / f"moons_{system}.npz", **data)
        for name, err, mb in report:
            print(f"  {name:10s} erro máx {err:7.1f} km  {mb:5.2f} MB")
    build_textures()
    build_grs()
    for p in sorted(OUT.iterdir()):
        print(f"{p.name}: {p.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
