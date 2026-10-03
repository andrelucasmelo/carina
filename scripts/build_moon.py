"""Gera a base lunar embarcada (v0.17, ADR-046).

Fontes (todas baixadas para ``data/raw/moon`` e ``data/ephemeris``):

- NASA SVS *CGI Moon Kit* (domínio público): mosaico de cor LROC WAC
  ``lroc_color_poles_8k.tif`` (8192×4096) e relevo LOLA ``ldem_16.tif``
  (16 px/grau, alturas em km sobre 1737,4 km);
- IAU/USGS *Gazetteer of Planetary Nomenclature* — pontos centrais das
  formações lunares (``MOON_nomenclature_center_pts.zip``, shapefile);
- NAIF/JPL: ``moon_pa_de421_1900-2050.bpc``, ``moon_080317.tf`` e
  ``pck00008.tpc`` — orientação da Lua (libração física);
- curadoria própria: ``scripts/curated/lunar100.tsv`` (lista de Charles
  Wood com descrições em português) e ``scripts/curated/meteors.tsv``
  (lista de trabalho da IMO).

Saída em ``data/processed/moon/``:

- ``moon_color.jpg`` — 8192×4096, equirretangular, longitude −180..180 da
  esquerda para a direita, norte em cima;
- ``moon_normal.jpg`` — 4096×2048, normais no referencial local
  (leste, norte, para cima) codificadas em RGB, relevo exagerado 4×;
- ``moon_features.json`` — formações da face visível e das bordas;
- ``lunar100.json`` e ``meteors.json`` (este em ``data/processed``).

Uso:
    python scripts/build_moon.py [--download] [--skip-textures]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "moon"
EPH = ROOT / "data" / "ephemeris"
OUT = ROOT / "data" / "processed" / "moon"
CURATED = Path(__file__).resolve().parent / "curated"

SVS = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/"
NAIF = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/"
DOWNLOADS = {
    RAW / "lroc_color_poles_8k.tif": SVS + "lroc_color_poles_8k.tif",
    RAW / "ldem_16.tif": SVS + "ldem_16.tif",
    RAW / "MOON_nomenclature_center_pts.zip":
        "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/"
        "MOON_nomenclature_center_pts.zip",
    EPH / "moon_pa_de421_1900-2050.bpc": NAIF + "pck/moon_pa_de421_1900-2050.bpc",
    EPH / "moon_080317.tf": NAIF + "fk/satellites/moon_080317.tf",
    EPH / "pck00008.tpc": NAIF + "pck/a_old_versions/pck00008.tpc",
}

MOON_RADIUS_KM = 1737.4
RELIEF_EXAGGERATION = 4.0
NORMAL_SIZE = (4096, 2048)

# tipo do Gazetteer -> chave interna
TYPE_KEYS = {
    "Crater, craters": "crater",
    "Mare, maria": "mare",
    "Oceanus, oceani": "mare",
    "Lacus, lacūs": "lacus",
    "Sinus, sinūs": "sinus",
    "Palus, paludes": "palus",
    "Mons, montes": "mons",
    "Rupes, rupēs": "rupes",
    "Vallis, valles": "vallis",
    "Rima, rimae": "rima",
    "Dorsum, dorsa": "dorsum",
    "Promontorium, promontoria": "promontorium",
    "Catena, catenae": "catena",
}
# diâmetro mínimo (km) por tipo para entrar na base
MIN_DIAM = {
    "crater": 20.0, "mare": 0.0, "lacus": 0.0, "sinus": 0.0, "palus": 0.0,
    "mons": 20.0, "rupes": 0.0, "vallis": 0.0, "rima": 60.0,
    "dorsum": 120.0, "promontorium": 0.0, "catena": 60.0,
}
MAX_ABS_LON = 100.0   # face visível + bordas alcançadas pela libração

# nomes populares em português (mares, lagos, baías e pântanos)
PT_NAMES = {
    "Oceanus Procellarum": "Oceano das Tempestades",
    "Mare Imbrium": "Mar das Chuvas",
    "Mare Serenitatis": "Mar da Serenidade",
    "Mare Tranquillitatis": "Mar da Tranquilidade",
    "Mare Crisium": "Mar das Crises",
    "Mare Fecunditatis": "Mar da Fecundidade",
    "Mare Nectaris": "Mar do Néctar",
    "Mare Nubium": "Mar das Nuvens",
    "Mare Humorum": "Mar dos Humores",
    "Mare Frigoris": "Mar do Frio",
    "Mare Vaporum": "Mar dos Vapores",
    "Mare Cognitum": "Mar Conhecido",
    "Mare Insularum": "Mar das Ilhas",
    "Mare Spumans": "Mar Espumante",
    "Mare Undarum": "Mar das Ondas",
    "Mare Anguis": "Mar da Serpente",
    "Mare Marginis": "Mar da Borda",
    "Mare Smythii": "Mar de Smyth",
    "Mare Australe": "Mar Austral",
    "Mare Orientale": "Mar Oriental",
    "Mare Humboldtianum": "Mar de Humboldt",
    "Mare Ingenii": "Mar do Engenho",
    "Mare Moscoviense": "Mar de Moscou",
    "Sinus Iridum": "Baía do Arco-Íris",
    "Sinus Medii": "Baía Central",
    "Sinus Aestuum": "Baía dos Calores",
    "Sinus Roris": "Baía do Orvalho",
    "Sinus Asperitatis": "Baía da Aspereza",
    "Sinus Concordiae": "Baía da Concórdia",
    "Sinus Amoris": "Baía do Amor",
    "Sinus Honoris": "Baía da Honra",
    "Sinus Lunicus": "Baía Lunar",
    "Sinus Successus": "Baía do Sucesso",
    "Lacus Somniorum": "Lago dos Sonhos",
    "Lacus Mortis": "Lago da Morte",
    "Lacus Excellentiae": "Lago da Excelência",
    "Lacus Felicitatis": "Lago da Felicidade",
    "Lacus Temporis": "Lago do Tempo",
    "Lacus Veris": "Lago da Primavera",
    "Lacus Autumni": "Lago do Outono",
    "Palus Putredinis": "Pântano da Putrefação",
    "Palus Somni": "Pântano do Sono",
    "Palus Epidemiarum": "Pântano das Epidemias",
    "Montes Apenninus": "Montes Apeninos",
    "Montes Alpes": "Alpes lunares",
    "Montes Caucasus": "Montes Cáucaso",
    "Montes Carpatus": "Montes Cárpatos",
    "Montes Jura": "Montes Jura",
    "Montes Haemus": "Montes Hemo",
    "Vallis Alpes": "Vale dos Alpes",
    "Vallis Schröteri": "Vale de Schröter",
    "Rupes Recta": "Muro Reto",
    "Rupes Altai": "Escarpa de Altai",
}


def download(force: bool = False) -> None:
    for path, url in DOWNLOADS.items():
        if path.exists() and not force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        print("baixando", url)
        with urllib.request.urlopen(url) as resp:
            path.write_bytes(resp.read())


# --------------------------------------------------------------------------
# texturas
def build_color() -> None:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(RAW / "lroc_color_poles_8k.tif").convert("RGB")
    arr = np.asarray(img)
    # conferência do referencial: o Mare Crisium (17°N, 59°L) é escuro e
    # fica à DIREITA do centro (longitude leste cresce para a direita)
    h, w, _ = arr.shape
    def lum(lat, lon):
        x = int((lon + 180.0) / 360.0 * w) % w
        y = int((90.0 - lat) / 180.0 * h)
        return float(arr[y - 8:y + 8, x - 8:x + 8].mean())
    crisium, east_highland = lum(17.0, 59.0), lum(17.0, 80.0)
    assert crisium < east_highland, "longitudes invertidas na textura de cor"
    img.save(OUT / "moon_color.jpg", quality=86, optimize=True)


def build_normals() -> None:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    dem = Image.open(RAW / "ldem_16.tif")
    dem = dem.resize(NORMAL_SIZE, Image.Resampling.BOX)
    h_km = np.asarray(dem, dtype=np.float64)
    hh, ww = h_km.shape
    lat = np.radians(90.0 - (np.arange(hh) + 0.5) / hh * 180.0)
    dx_km = 2.0 * np.pi * MOON_RADIUS_KM * np.maximum(np.cos(lat), 0.05) / ww
    dy_km = np.pi * MOON_RADIUS_KM / hh
    # derivadas centrais; em longitude a imagem dá a volta
    dh_e = (np.roll(h_km, -1, axis=1) - np.roll(h_km, 1, axis=1)) / (2.0 * dx_km[:, None])
    up = np.vstack([h_km[:1], h_km[:-1]])
    dn = np.vstack([h_km[1:], h_km[-1:]])
    dh_n = (up - dn) / (2.0 * dy_km)
    k = RELIEF_EXAGGERATION
    n = np.stack([-k * dh_e, -k * dh_n, np.ones_like(h_km)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    rgb = np.clip(np.round(n * 127.5 + 127.5), 0, 255).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(OUT / "moon_normal.jpg", quality=92, optimize=True)


# --------------------------------------------------------------------------
# nomenclatura
def _read_dbf(data: bytes) -> list[dict]:
    n, hlen, rlen = struct.unpack("<IHH", data[4:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        d = data[pos:pos + 32]
        fields.append((d[:11].split(b"\0")[0].decode(), d[16]))
        pos += 32
    out = []
    for i in range(n):
        rec = data[hlen + i * rlen: hlen + (i + 1) * rlen]
        if rec[:1] == b"*":       # registro apagado
            continue
        o, row = 1, {}
        for name, ln in fields:
            row[name] = rec[o:o + ln].decode("utf-8", "replace").strip()
            o += ln
        out.append(row)
    return out


def load_lunar100() -> list[dict]:
    items = []
    for line in (CURATED / "lunar100.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        num, name, lat, lon, kind, desc = line.split("\t")
        items.append({
            "n": int(num), "name": name,
            "lat": None if lat == "-" else float(lat),
            "lon": None if lon == "-" else float(lon),
            "type": kind, "desc": desc,
        })
    assert len(items) == 100 and [i["n"] for i in items] == list(range(1, 101))
    return items


def build_features(lunar100: list[dict]) -> int:
    with zipfile.ZipFile(RAW / "MOON_nomenclature_center_pts.zip") as zf:
        name = next(n for n in zf.namelist() if n.endswith(".dbf"))
        rows = _read_dbf(zf.read(name))
    feats = []
    for r in rows:
        key = TYPE_KEYS.get(r["type"])
        if key is None or not r["diameter"]:
            continue
        diam = float(r["diameter"])
        lon = (float(r["center_lon"]) + 180.0) % 360.0 - 180.0
        lat = float(r["center_lat"])
        if abs(lon) > MAX_ABS_LON or diam < MIN_DIAM[key]:
            continue
        feats.append({
            "name": r["clean_name"] or r["name"],
            "pt": PT_NAMES.get(r["clean_name"] or r["name"], ""),
            "type": key,
            "lat": round(lat, 3), "lon": round(lon, 3),
            "diam": round(diam, 1),
        })
    feats.sort(key=lambda f: -f["diam"])
    # liga as formações à Lunar 100 pelo nome exato, quando ele existe
    l100 = {}
    for item in lunar100:
        l100[item["name"].split(" (")[0]] = item["n"]
    for f in feats:
        n = l100.get(f["name"])
        if n:
            f["l100"] = n
    meta = {
        "source": "IAU/USGS Gazetteer of Planetary Nomenclature",
        "radius_km": MOON_RADIUS_KM,
        "count": len(feats),
    }
    (OUT / "moon_features.json").write_text(
        json.dumps({"meta": meta, "features": feats}, ensure_ascii=False,
                   separators=(",", ":")), encoding="utf-8")
    return len(feats)


def build_lunar100(lunar100: list[dict]) -> None:
    (OUT / "lunar100.json").write_text(
        json.dumps({"source": "Lunar 100 — Charles A. Wood (Sky & Telescope, 2004)",
                    "items": lunar100}, ensure_ascii=False, indent=1),
        encoding="utf-8")


def build_meteors() -> int:
    showers = []
    for line in (CURATED / "meteors.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        code, name, beg, peak, end, zhr, ra, dec, v, r, note = line.split("\t")
        showers.append({
            "code": code, "name": name,
            "begin": float(beg), "peak": float(peak), "end": float(end),
            "zhr": int(zhr), "ra": float(ra), "dec": float(dec),
            "v": float(v), "r": float(r), "note": note,
        })
    (ROOT / "data" / "processed" / "meteors.json").write_text(
        json.dumps({"source": "IMO Meteor Shower Working List",
                    "showers": showers}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return len(showers)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--download", action="store_true", help="baixa as fontes que faltarem")
    ap.add_argument("--skip-textures", action="store_true")
    args = ap.parse_args()
    if args.download:
        download()
    OUT.mkdir(parents=True, exist_ok=True)
    lunar100 = load_lunar100()
    if not args.skip_textures:
        build_color()
        build_normals()
    n = build_features(lunar100)
    build_lunar100(lunar100)
    m = build_meteors()
    print(f"formações: {n} · Lunar 100: 100 · chuvas de meteoros: {m}")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}: {p.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
