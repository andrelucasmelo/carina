"""Pipeline de dados do AstroPlanetary.

Baixa os catálogos brutos para ``data/raw/`` (ignorado no git) e gera os
arquivos processados e compactos em ``data/processed/`` (versionados), que são
os únicos lidos pelo aplicativo em tempo de execução.

Fontes (ver docs/FONTES_DE_DADOS.md):
  - Estrelas: HYG v4.1 (astronexus/HYG-Database) — CC BY-SA
  - Linhas/fronteiras de constelações e Via Láctea: d3-celestial (BSD-3)

Uso:
    python scripts/build_data.py [--force]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

HYG_BASE = "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT"
HYG_CSV = f"{HYG_BASE}/hygdata_v41.csv"
HYG_LICENSE = f"{HYG_BASE}/LICENSE"

D3C_BASE = "https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data"
D3C_FILES = {
    "constellations.json": f"{D3C_BASE}/constellations.json",
    "constellations.lines.json": f"{D3C_BASE}/constellations.lines.json",
    "constellations.bounds.json": f"{D3C_BASE}/constellations.bounds.json",
    "mw.json": f"{D3C_BASE}/mw.json",
}


def download(url: str, dest: Path, force: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  [ok] {dest.name} já existe ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"  [dl] {url}")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"       -> {dest.name} ({len(resp.content):,} bytes)")
    return dest


# ---------------------------------------------------------------------------
# Estrelas (HYG)
# ---------------------------------------------------------------------------

def _open_maybe_gzip(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, "rt", encoding="utf-8", newline="")


def build_stars(force: bool) -> None:
    print("== Estrelas (HYG v4.1) ==")
    csv_path = download(HYG_CSV, RAW / "hygdata_v41.csv", force)
    download(HYG_LICENSE, RAW / "HYG_LICENSE.txt", force)

    ra = []          # radianos (ICRS J2000)
    dec = []         # radianos
    mag = []         # magnitude visual
    ci = []          # índice de cor B-V
    hip = []         # número Hipparcos (0 se ausente)
    names = {"proper": [], "bayer": [], "flam": [], "con": []}

    with _open_maybe_gzip(csv_path) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # O Sol aparece como registro id=0 no HYG; não é uma estrela do céu.
            if row.get("proper") == "Sol" or row.get("id") == "0":
                continue
            try:
                m = float(row["mag"])
                ra_rad = float(row["ra"]) * math.pi / 12.0   # horas -> rad
                dec_rad = float(row["dec"]) * math.pi / 180.0
            except (TypeError, ValueError):
                continue
            idx = len(ra)
            ra.append(ra_rad)
            dec.append(dec_rad)
            mag.append(m)
            try:
                ci.append(float(row["ci"]))
            except (TypeError, ValueError):
                ci.append(0.65)  # cor média quando desconhecida
            try:
                hip.append(int(row["hip"]))
            except (TypeError, ValueError):
                hip.append(0)
            if row.get("proper"):
                names["proper"].append([idx, row["proper"]])
            if row.get("bayer"):
                names["bayer"].append([idx, row["bayer"]])
            if row.get("flam"):
                names["flam"].append([idx, row["flam"]])
            if row.get("con"):
                names["con"].append([idx, row["con"]])

    ra = np.asarray(ra, dtype=np.float64)
    dec = np.asarray(dec, dtype=np.float64)
    mag = np.asarray(mag, dtype=np.float32)
    ci = np.asarray(ci, dtype=np.float32)
    hip = np.asarray(hip, dtype=np.int32)

    # Ordena por magnitude: em tempo de execução o corte por magnitude vira um
    # simples slice (np.searchsorted), sem máscaras por quadro.
    order = np.argsort(mag, kind="stable")
    inv = np.empty_like(order)
    inv[order] = np.arange(len(order))

    ra, dec, mag, ci, hip = ra[order], dec[order], mag[order], ci[order], hip[order]
    for key in names:
        names[key] = sorted([[int(inv[i]), v] for i, v in names[key]])

    # Vetores unitários ICRS (frame equatorial): x -> equinócio vernal.
    cos_dec = np.cos(dec)
    xyz = np.stack(
        [cos_dec * np.cos(ra), cos_dec * np.sin(ra), np.sin(dec)], axis=1
    ).astype(np.float32)

    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / "stars_hyg.npz",
        xyz=xyz, mag=mag, ci=ci, hip=hip,
        ra=ra.astype(np.float32), dec=dec.astype(np.float32),
    )
    (OUT / "star_names.json").write_text(
        json.dumps(names, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  {len(mag):,} estrelas | mag {mag.min():.1f} a {mag.max():.1f}")
    print(f"  nomes próprios: {len(names['proper'])} | bayer: {len(names['bayer'])}")


# ---------------------------------------------------------------------------
# Constelações e Via Láctea (d3-celestial)
# ---------------------------------------------------------------------------

def _radec_to_xyz(ra_deg: float, dec_deg: float) -> np.ndarray:
    ra = math.radians(ra_deg % 360.0)
    dec = math.radians(dec_deg)
    return np.array(
        [math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)]
    )


def _subdivide_great_circle(p0: np.ndarray, p1: np.ndarray, max_step_deg: float) -> list[np.ndarray]:
    """Subdivide o arco de círculo máximo entre dois vetores unitários (slerp)."""
    dot = float(np.clip(np.dot(p0, p1), -1.0, 1.0))
    angle = math.acos(dot)
    steps = max(1, math.ceil(math.degrees(angle) / max_step_deg))
    if angle < 1e-9:
        return [p1]
    sin_a = math.sin(angle)
    pts = []
    for k in range(1, steps + 1):
        t = k / steps
        p = (math.sin((1 - t) * angle) * p0 + math.sin(t * angle) * p1) / sin_a
        pts.append(p / np.linalg.norm(p))
    return pts


def _polylines_to_arrays(polylines: list[list[np.ndarray]]):
    """Concatena polilinhas em (verts float32, counts int32)."""
    counts = np.array([len(p) for p in polylines], dtype=np.int32)
    verts = np.concatenate([np.asarray(p, dtype=np.float32) for p in polylines])
    return verts, counts


def _geojson_polylines(feature_coll: dict, max_step_deg: float,
                       close_rings: bool = False) -> tuple[list, list]:
    """Extrai polilinhas subdivididas de um GeoJSON do d3-celestial.

    Retorna (polylines, ids): cada polilinha é uma lista de vetores unitários.
    """
    polylines: list[list[np.ndarray]] = []
    ids: list[str] = []
    for feat in feature_coll["features"]:
        fid = str(feat.get("id", ""))
        geom = feat["geometry"]
        gtype = geom["type"]
        if gtype == "MultiLineString":
            lines = geom["coordinates"]
        elif gtype == "LineString":
            lines = [geom["coordinates"]]
        elif gtype == "Polygon":
            lines = geom["coordinates"]
        elif gtype == "MultiPolygon":
            lines = [ring for poly in geom["coordinates"] for ring in poly]
        else:
            continue
        for line in lines:
            if len(line) < 2:
                continue
            if close_rings and line[0] != line[-1]:
                line = list(line) + [line[0]]
            pts = [_radec_to_xyz(*line[0])]
            for a, b in zip(line[:-1], line[1:]):
                pts.extend(
                    _subdivide_great_circle(_radec_to_xyz(*a), _radec_to_xyz(*b), max_step_deg)
                )
            polylines.append(pts)
            ids.append(fid)
    return polylines, ids


def build_constellations(force: bool) -> None:
    print("== Constelações e Via Láctea (d3-celestial) ==")
    paths = {name: download(url, RAW / name, force) for name, url in D3C_FILES.items()}

    # --- linhas (desenho tradicional) ---
    lines_geo = json.loads(paths["constellations.lines.json"].read_text(encoding="utf-8"))
    polys, ids = _geojson_polylines(lines_geo, max_step_deg=2.0)
    verts, counts = _polylines_to_arrays(polys)
    np.savez_compressed(OUT / "const_lines.npz", verts=verts, counts=counts)
    print(f"  linhas: {len(counts)} polilinhas, {len(verts):,} vértices")

    # --- fronteiras IAU ---
    bounds_geo = json.loads(paths["constellations.bounds.json"].read_text(encoding="utf-8"))
    polys, ids = _geojson_polylines(bounds_geo, max_step_deg=1.0, close_rings=True)
    verts, counts = _polylines_to_arrays(polys)
    np.savez_compressed(OUT / "const_bounds.npz", verts=verts, counts=counts)
    print(f"  fronteiras: {len(counts)} polilinhas, {len(verts):,} vértices")

    # --- nomes e centros das constelações ---
    const_geo = json.loads(paths["constellations.json"].read_text(encoding="utf-8"))
    const_info = []
    for feat in const_geo["features"]:
        props = feat.get("properties", {})
        center = props.get("display", feat["geometry"]["coordinates"])
        const_info.append(
            {
                "id": str(feat.get("id", "")),
                "name": props.get("name", ""),
                "gen": props.get("gen", ""),  # genitivo latino
                "ra": float(center[0]) % 360.0,
                "dec": float(center[1]),
                "rank": int(props.get("rank", 3)),
            }
        )
    (OUT / "constellations.json").write_text(
        json.dumps(const_info, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  constelações: {len(const_info)}")

    # --- Via Láctea: polígonos aninhados de isofotas (ol1..ol5) ---
    mw_geo = json.loads(paths["mw.json"].read_text(encoding="utf-8"))
    mw_layers: dict[str, list] = {}
    for feat in mw_geo["features"]:
        layer = str(feat.get("id", "mw"))
        geom = feat["geometry"]
        rings = []
        if geom["type"] == "MultiPolygon":
            rings = [ring for poly in geom["coordinates"] for ring in poly]
        elif geom["type"] == "Polygon":
            rings = geom["coordinates"]
        mw_layers.setdefault(layer, []).extend(rings)

    all_polys = []
    layer_of = []
    layer_names = sorted(mw_layers)
    for li, layer in enumerate(layer_names):
        for ring in mw_layers[layer]:
            if len(ring) < 3:
                continue
            pts = [_radec_to_xyz(*ring[0])]
            for a, b in zip(ring[:-1], ring[1:]):
                pts.extend(
                    _subdivide_great_circle(_radec_to_xyz(*a), _radec_to_xyz(*b), 3.0)
                )
            all_polys.append(pts)
            layer_of.append(li)
    verts, counts = _polylines_to_arrays(all_polys)
    np.savez_compressed(
        OUT / "milkyway.npz",
        verts=verts, counts=counts,
        layer=np.asarray(layer_of, dtype=np.int32),
        n_layers=np.int32(len(layer_names)),
    )
    print(f"  via láctea: {len(layer_names)} camadas, {len(counts)} polígonos, {len(verts):,} vértices")


def _even_odd_accumulate(inside: np.ndarray, pts: np.ndarray, ring: np.ndarray) -> None:
    """XOR de pertencimento (regra even-odd) dos pontos em relação a um anel 2D.

    Testa apenas os pontos dentro do bounding box do anel (vetorizado).
    """
    xmin, ymin = ring.min(axis=0)
    xmax, ymax = ring.max(axis=0)
    sel = (
        (pts[:, 0] >= xmin) & (pts[:, 0] <= xmax)
        & (pts[:, 1] >= ymin) & (pts[:, 1] <= ymax)
    )
    if not sel.any():
        return
    p = pts[sel]
    x, y = p[:, 0], p[:, 1]
    x0, y0 = ring[:-1, 0][:, None], ring[:-1, 1][:, None]
    x1, y1 = ring[1:, 0][:, None], ring[1:, 1][:, None]
    cond = ((y0 <= y) & (y1 > y)) | ((y1 <= y) & (y0 > y))
    with np.errstate(divide="ignore", invalid="ignore"):
        xin = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
    crossings = np.count_nonzero(cond & (x < xin), axis=0)
    inside[sel] ^= (crossings % 2).astype(bool)


def build_milkyway_points(force: bool) -> None:
    """Converte as isofotas da Via Láctea numa nuvem de pontos com peso.

    O preenchimento de polígonos esféricos côncavos na projeção é frágil
    (paridade quebra quando o anel cruza o antípoda da vista); uma nuvem de
    splats suaves ponderada pelo número de isofotas que contêm cada ponto é
    robusta e tem visual mais orgânico. Grade de 0,5° com jitter determinístico.
    """
    print("== Via Láctea: nuvem de pontos ==")
    path = RAW / "mw.json"
    if not path.exists():
        download(D3C_FILES["mw.json"], path, force)
    mw_geo = json.loads(path.read_text(encoding="utf-8"))

    layers: dict[str, list[np.ndarray]] = {}
    for feat in mw_geo["features"]:
        layer = str(feat.get("id", "mw"))
        geom = feat["geometry"]
        if geom["type"] == "MultiPolygon":
            rings = [ring for poly in geom["coordinates"] for ring in poly]
        elif geom["type"] == "Polygon":
            rings = geom["coordinates"]
        else:
            continue
        for ring in rings:
            if len(ring) >= 3:
                r = np.asarray(ring, dtype=np.float64)
                if not np.allclose(r[0], r[-1]):
                    r = np.vstack([r, r[0]])
                layers.setdefault(layer, []).append(r)

    step = 0.5
    rng = np.random.default_rng(20260824)
    lon = np.arange(-180.0, 180.0, step)
    lat = np.arange(-89.5, 89.5 + 1e-9, step)
    glon, glat = np.meshgrid(lon, lat)
    pts = np.column_stack([glon.ravel(), glat.ravel()])
    pts += rng.uniform(-step / 2, step / 2, size=pts.shape)

    weight = np.zeros(len(pts), dtype=np.uint8)
    for layer in sorted(layers):
        inside = np.zeros(len(pts), dtype=bool)
        for ring in layers[layer]:
            _even_odd_accumulate(inside, pts, ring)
        weight += inside.astype(np.uint8)

    keep = weight > 0
    pts, weight = pts[keep], weight[keep]
    ra = np.radians(np.mod(pts[:, 0], 360.0))
    dec = np.radians(pts[:, 1])
    cd = np.cos(dec)
    xyz = np.stack([cd * np.cos(ra), cd * np.sin(ra), np.sin(dec)], axis=1)
    np.savez_compressed(
        OUT / "milkyway_pts.npz",
        xyz=xyz.astype(np.float32), weight=weight,
    )
    print(f"  {len(pts):,} splats | pesos 1..{weight.max()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="baixa tudo novamente")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    build_stars(args.force)
    build_constellations(args.force)
    build_milkyway_points(args.force)
    print("Concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
