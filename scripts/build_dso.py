"""Constrói o banco local de céu profundo (data/processed/dso.sqlite).

Diretriz do projeto (ADR-012): todo dado baixado vira base LOCAL embarcada na
instalação — o aplicativo nunca depende de internet para exibir o mapa.

Fontes (dev-docs/FONTES_DE_DADOS.md):
  - OpenNGC (NGC/IC + cruzamento Messier, tipos, tamanhos, PA)  CC BY-SA 4.0
  - Lista Caldwell: mapeamento C1–C109 embutido neste script (auditar!)
  - Sharpless SH2: VizieR VII/20 (coordenadas J2000 computadas pelo CDS)
  - Barnard (nebulosas escuras): VizieR VII/220A (idem)
  - Melotte: SIMBAD TAP (identificadores 'Cl Melotte N')

Uso:
    python scripts/build_dso.py [--force]
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
DB = OUT / "dso.sqlite"

OPENNGC_BASE = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files"
VIZIER = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"

# Tipo OpenNGC/SIMBAD -> classe de símbolo do Carina
KLASS = {
    "G": "GAL", "GPair": "GAL", "GTrpl": "GAL", "GGroup": "GAL",
    "OCl": "OC", "GCl": "GC", "PN": "PN",
    "HII": "NEB", "EmN": "NEB", "Neb": "NEB", "RfN": "NEB", "SNR": "NEB",
    "Cl+N": "NEB", "DrkN": "DARK",
    # SIMBAD otypes (Melotte)
    "OpC": "OC", "GlC": "GC", "As*": "OC", "Cl*": "OC",
}

# --- Lista Caldwell (C -> designação OpenNGC). ---------------------------
# ATENÇÃO: compilada de conhecimento geral; pendência de auditoria item a item
# contra fonte publicada (ver PENDENCIAS.md). C99 (Saco de Carvão) não tem
# NGC e é adicionada à parte; C9 aponta para Sh2-155; C41 = Melotte 25.
CALDWELL = {
    1: "NGC0188", 2: "NGC0040", 3: "NGC4236", 4: "NGC7023", 5: "IC0342",
    6: "NGC6543", 7: "NGC2403", 8: "NGC0559", 10: "NGC0663",
    11: "NGC7635", 12: "NGC6946", 13: "NGC0457", 14: "NGC0869",
    15: "NGC6826", 16: "NGC7243", 17: "NGC0147", 18: "NGC0185",
    19: "IC5146", 20: "NGC7000", 21: "NGC4449", 22: "NGC7662",
    23: "NGC0891", 24: "NGC1275", 25: "NGC2419", 26: "NGC4244",
    27: "NGC6888", 28: "NGC0752", 29: "NGC5005", 30: "NGC7331",
    31: "IC0405", 32: "NGC4631", 33: "NGC6992", 34: "NGC6960",
    35: "NGC4889", 36: "NGC4559", 37: "NGC6885", 38: "NGC4565",
    39: "NGC2392", 40: "NGC3626", 42: "NGC7006", 43: "NGC7814",
    44: "NGC7479", 45: "NGC5248", 46: "NGC2261", 47: "NGC6934",
    48: "NGC2775", 49: "NGC2237", 50: "NGC2244", 51: "IC1613",
    52: "NGC4697", 53: "NGC3115", 54: "NGC2506", 55: "NGC7009",
    56: "NGC0246", 57: "NGC6822", 58: "NGC2360", 59: "NGC3242",
    60: "NGC4038", 61: "NGC4039", 62: "NGC0247", 63: "NGC7293",
    64: "NGC2362", 65: "NGC0253", 66: "NGC5694", 67: "NGC1097",
    68: "NGC6729", 69: "NGC6302", 70: "NGC0300", 71: "NGC2477",
    72: "NGC0055", 73: "NGC1851", 74: "NGC3132", 75: "NGC6124",
    76: "NGC6231", 77: "NGC5128", 78: "NGC6541", 79: "NGC3201",
    80: "NGC5139", 81: "NGC6352", 82: "NGC6193", 83: "NGC4945",
    84: "NGC5286", 85: "IC2391", 86: "NGC6397", 87: "NGC1261",
    88: "NGC5823", 89: "NGC6087", 90: "NGC2867", 91: "NGC3532",
    92: "NGC3372", 93: "NGC6752", 94: "NGC4755", 95: "NGC6025",
    96: "NGC2516", 97: "NGC3766", 98: "NGC4609", 100: "IC2944",
    101: "NGC6744", 102: "IC2602", 103: "NGC2070", 104: "NGC0362",
    105: "NGC4833", 106: "NGC0104", 107: "NGC6101", 108: "NGC4372",
    109: "NGC3195",
}
CALDWELL_SH2 = {9: "Sh2-155"}
CALDWELL_MEL = {41: "Mel 25"}
# C99: Saco de Carvão — nebulosa escura sem entrada em catálogo clássico.
COALSACK = {
    "name": "C 99", "type": "DrkN", "klass": "DARK",
    "ra_h": 12.52, "dec_deg": -62.5, "maj": 420.0, "min": 300.0,
    "common": "Saco de Carvão (Coalsack)", "con": "Cru",
}


def download(url: str, dest: Path, force: bool) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  [ok] {dest.name}")
        return dest
    print(f"  [dl] {url[:110]}")
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"       -> {dest.name} ({len(resp.content):,} bytes)")
    return dest


def hms_to_rad(text: str) -> float | None:
    m = re.match(r"^\s*(\d+):(\d+):([\d.]+)", text or "")
    if not m:
        return None
    h, mi, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
    return (h + mi / 60 + s / 3600) * math.pi / 12.0


def dms_to_rad(text: str) -> float | None:
    m = re.match(r"^\s*([+-]?)(\d+):(\d+):([\d.]+)", text or "")
    if not m:
        return None
    sign = -1.0 if m.group(1) == "-" else 1.0
    d, mi, s = float(m.group(2)), float(m.group(3)), float(m.group(4))
    return sign * (d + mi / 60 + s / 3600) * math.pi / 180.0


def ffloat(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def pretty_ngc(name: str) -> tuple[str, str] | None:
    """'NGC0001'/'IC0342' -> ('NGC', '1')  (mantém sufixos como 'NGC0554A')."""
    m = re.match(r"^(NGC|IC)(\d+)(.*)$", name or "")
    if not m:
        return None
    return m.group(1), str(int(m.group(2))) + (m.group(3) or "").strip()


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE objects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    klass TEXT NOT NULL,
    ra REAL NOT NULL,
    dec REAL NOT NULL,
    mag REAL,
    maj REAL,
    min REAL,
    pa REAL,
    con TEXT,
    common TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    user_added INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE TABLE designations (
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    catalog TEXT NOT NULL,
    ident TEXT NOT NULL,
    PRIMARY KEY (object_id, catalog, ident)
);
CREATE INDEX idx_desig_cat ON designations(catalog, ident);
CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE object_categories (
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (object_id, category_id)
);
"""


class Builder:
    def __init__(self) -> None:
        if DB.exists():
            DB.unlink()
        self.cx = sqlite3.connect(DB)
        self.cx.executescript(SCHEMA)
        self.by_ngc: dict[str, int] = {}   # 'NGC0001' -> object_id
        self.dup_map: dict[str, str] = {}  # duplicata -> nome canônico

    def add_object(self, **kw) -> int:
        cur = self.cx.execute(
            "INSERT INTO objects (name, type, klass, ra, dec, mag, maj, min,"
            " pa, con, common, enabled, user_added, notes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,1,0,?)",
            (
                kw["name"], kw["type"], kw["klass"], kw["ra"], kw["dec"],
                kw.get("mag"), kw.get("maj"), kw.get("min"), kw.get("pa"),
                kw.get("con"), kw.get("common"), kw.get("notes"),
            ),
        )
        return cur.lastrowid

    def add_desig(self, oid: int, catalog: str, ident: str) -> None:
        self.cx.execute(
            "INSERT OR IGNORE INTO designations VALUES (?,?,?)",
            (oid, catalog, ident),
        )


# ---------------------------------------------------------------------------
# OpenNGC (NGC/IC/Messier)
# ---------------------------------------------------------------------------

def load_openngc(b: Builder, force: bool) -> None:
    print("== OpenNGC (NGC/IC/Messier) ==")
    main_csv = download(f"{OPENNGC_BASE}/NGC.csv", RAW / "OpenNGC.csv", force)
    add_csv = download(
        f"{OPENNGC_BASE}/addendum.csv", RAW / "OpenNGC_addendum.csv", force
    )
    n_obj = n_m = 0
    for path in (main_csv, add_csv):
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                name = (row.get("Name") or "").strip()
                typ = (row.get("Type") or "").strip()
                if typ == "Dup":
                    # guarda o alvo canônico para resolver referências depois
                    for col, cat in (("NGC", "NGC"), ("IC", "IC")):
                        target = (row.get(col) or "").split(",")[0].strip()
                        if not target:
                            continue
                        full = target if target.startswith(("NGC", "IC")) \
                            else f"{cat}{target}"
                        m = re.match(r"^(NGC|IC)0*(\d+)(.*)$", full)
                        if m:
                            b.dup_map[name] = (
                                f"{m.group(1)}{int(m.group(2)):04d}{m.group(3).strip()}"
                            )
                            break
                    continue
                if typ in ("NonEx", ""):
                    continue
                ra = hms_to_rad(row.get("RA"))
                dec = dms_to_rad(row.get("Dec"))
                if ra is None or dec is None:
                    continue
                mag = ffloat(row.get("V-Mag")) or ffloat(row.get("B-Mag"))
                common = (row.get("Common names") or "").replace(",", ", ") or None
                pn = pretty_ngc(name)
                m_num = (row.get("M") or "").strip()
                if pn:
                    display = f"{pn[0]} {pn[1]}"
                elif name.startswith("Mel"):
                    display = name.replace("Mel", "Mel ").replace("  ", " ")
                else:
                    display = name
                if m_num:
                    display = f"M {int(m_num)}"
                oid = b.add_object(
                    name=display, type=typ, klass=KLASS.get(typ, "OTHER"),
                    ra=ra, dec=dec, mag=mag,
                    maj=ffloat(row.get("MajAx")), min=ffloat(row.get("MinAx")),
                    pa=ffloat(row.get("PosAng")), con=(row.get("Const") or None),
                    common=common,
                )
                n_obj += 1
                if pn:
                    b.add_desig(oid, pn[0], pn[1])
                    b.by_ngc[name] = oid
                if m_num:
                    b.add_desig(oid, "M", str(int(m_num)))
                    n_m += 1
                # cruzamentos NGC<->IC dados pelo OpenNGC
                for cat, col in (("NGC", "NGC"), ("IC", "IC")):
                    for extra in (row.get(col) or "").split(","):
                        extra = extra.strip()
                        pe = pretty_ngc(extra if extra.startswith(("NGC", "IC"))
                                        else f"{cat}{extra}") if extra else None
                        if pe:
                            b.add_desig(oid, pe[0], pe[1])
    print(f"  {n_obj:,} objetos ({n_m} Messier)")


def apply_caldwell(b: Builder) -> None:
    print("== Caldwell ==")
    found = 0
    for c_num, ngc_name in CALDWELL.items():
        oid = b.by_ngc.get(ngc_name)
        if oid is None and ngc_name in b.dup_map:
            oid = b.by_ngc.get(b.dup_map[ngc_name])
        if oid is None:
            print(f"  [!] C{c_num}: {ngc_name} não encontrado no OpenNGC")
            continue
        b.add_desig(oid, "C", str(c_num))
        found += 1
    # C99 — Saco de Carvão (sem NGC)
    ra = COALSACK["ra_h"] * math.pi / 12.0
    dec = math.radians(COALSACK["dec_deg"])
    oid = b.add_object(
        name=COALSACK["name"], type=COALSACK["type"], klass=COALSACK["klass"],
        ra=ra, dec=dec, maj=COALSACK["maj"], min=COALSACK["min"],
        con=COALSACK["con"], common=COALSACK["common"],
        notes="Coordenadas aproximadas do centro.",
    )
    b.add_desig(oid, "C", "99")
    print(f"  {found} + C99 + (C9->SH2, C41->Mel) aplicados após os demais catálogos")


# ---------------------------------------------------------------------------
# Sharpless (SH2) e Barnard via VizieR
# ---------------------------------------------------------------------------

def _vizier_tsv(source: str, columns: list[str], dest: Path, force: bool) -> list[dict]:
    params = {
        "-source": source,
        "-out.max": "unlimited",
        "-out.add": "_RAJ2000,_DEJ2000",
        "-out": ",".join(columns),
    }
    url = f"{VIZIER}?{urllib.parse.urlencode(params)}"
    path = download(url, dest, force)
    rows: list[dict] = []
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if header is None:
            header = [p.strip() for p in parts]
            continue
        if set(line.replace("\t", "")) <= {"-", " "}:
            continue  # linha separadora ----
        if len(parts) < len(header):
            continue
        rows.append({h: p.strip() for h, p in zip(header, parts)})
    return rows


def load_sh2(b: Builder, force: bool) -> None:
    print("== Sharpless SH2 (VizieR VII/20) ==")
    rows = _vizier_tsv("VII/20/catalog", ["Sh2", "Diam"], RAW / "sh2.tsv", force)
    sh2_ids: dict[str, int] = {}
    n = 0
    for r in rows:
        num = r.get("Sh2")
        ra = ffloat(r.get("_RAJ2000"))
        dec = ffloat(r.get("_DEJ2000"))
        if not num or ra is None or dec is None:
            continue
        diam = ffloat(r.get("Diam"))
        oid = b.add_object(
            name=f"Sh2-{num}", type="HII", klass="NEB",
            ra=math.radians(ra), dec=math.radians(dec),
            maj=diam, min=diam,
        )
        b.add_desig(oid, "SH2", num)
        sh2_ids[f"Sh2-{num}"] = oid
        n += 1
    for c_num, sh2_name in CALDWELL_SH2.items():
        if sh2_name in sh2_ids:
            b.add_desig(sh2_ids[sh2_name], "C", str(c_num))
    print(f"  {n} regiões HII")


def load_barnard(b: Builder, force: bool) -> None:
    print("== Barnard (VizieR VII/220A) ==")
    rows = _vizier_tsv(
        "VII/220A/barnard", ["Barn", "Diam"], RAW / "barnard.tsv", force
    )
    n = 0
    for r in rows:
        num = r.get("Barn")
        ra = ffloat(r.get("_RAJ2000"))
        dec = ffloat(r.get("_DEJ2000"))
        if not num or ra is None or dec is None:
            continue
        diam = ffloat(r.get("Diam"))
        oid = b.add_object(
            name=f"B {num}", type="DrkN", klass="DARK",
            ra=math.radians(ra), dec=math.radians(dec),
            maj=diam, min=diam,
        )
        b.add_desig(oid, "B", num)
        n += 1
    print(f"  {n} nebulosas escuras")


# ---------------------------------------------------------------------------
# Melotte via SIMBAD TAP
# ---------------------------------------------------------------------------

def _simbad_csv(query: str, dest: Path, force: bool) -> list[dict]:
    params = {
        "request": "doQuery", "lang": "adql", "format": "csv", "query": query,
    }
    url = f"{SIMBAD_TAP}?{urllib.parse.urlencode(params)}"
    path = download(url, dest, force)
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_melotte(b: Builder, force: bool) -> None:
    print("== Melotte (SIMBAD TAP) ==")
    try:
        main = _simbad_csv(
            "SELECT i.id AS mel, basic.ra, basic.dec, basic.otype_txt,"
            " basic.galdim_majaxis, basic.galdim_minaxis"
            " FROM ident AS i JOIN basic ON i.oidref = basic.oid"
            " WHERE i.id LIKE 'Cl Melotte %'",
            RAW / "melotte.csv", force,
        )
        cross = _simbad_csv(
            "SELECT i.id AS mel, o.id AS other"
            " FROM ident AS i JOIN ident AS o ON i.oidref = o.oidref"
            " WHERE i.id LIKE 'Cl Melotte %'"
            " AND (o.id LIKE 'NGC %' OR o.id LIKE 'IC %')",
            RAW / "melotte_cross.csv", force,
        )
    except Exception as exc:  # SIMBAD fora do ar não deve travar o build
        print(f"  [!] SIMBAD indisponível ({exc}); Melotte ficará de fora")
        return

    cross_map: dict[str, str] = {}
    for r in cross:
        num = re.sub(r"^Cl Melotte\s+", "", r["mel"]).strip()
        if not re.fullmatch(r"\d+", num):
            continue  # 'Cl Melotte 22 123' é uma ESTRELA do aglomerado
        other = re.sub(r"\s+", "", r["other"])  # 'NGC 7000' -> 'NGC7000'
        m = re.match(r"^(NGC|IC)(\d+)(.*)$", other)
        if m and num not in cross_map:
            cross_map[num] = f"{m.group(1)}{int(m.group(2)):04d}{m.group(3)}"

    mel_ids: dict[str, int] = {}
    n_new = n_linked = 0
    for r in main:
        num = re.sub(r"^Cl Melotte\s+", "", r["mel"]).strip()
        if not re.fullmatch(r"\d+", num):
            continue  # identificadores de estrelas individuais
        if num in mel_ids:
            continue
        ngc_name = cross_map.get(num)
        if ngc_name and ngc_name in b.by_ngc:
            b.add_desig(b.by_ngc[ngc_name], "Mel", num)
            mel_ids[num] = b.by_ngc[ngc_name]
            n_linked += 1
            continue
        ra = ffloat(r.get("ra"))
        dec = ffloat(r.get("dec"))
        if ra is None or dec is None:
            continue
        otype = (r.get("otype_txt") or "OpC").strip()
        oid = b.add_object(
            name=f"Mel {num}", type=otype, klass=KLASS.get(otype, "OC"),
            ra=math.radians(ra), dec=math.radians(dec),
            maj=ffloat(r.get("galdim_majaxis")),
            min=ffloat(r.get("galdim_minaxis")),
        )
        b.add_desig(oid, "Mel", num)
        mel_ids[num] = oid
        n_new += 1
    for c_num, mel_name in CALDWELL_MEL.items():
        num = mel_name.split()[1]
        if num in mel_ids:
            b.add_desig(mel_ids[num], "C", str(c_num))
    print(f"  {n_new} novos + {n_linked} ligados a NGC/IC existentes")


# ---------------------------------------------------------------------------
# Messier: casos especiais que podem faltar no OpenNGC
# ---------------------------------------------------------------------------

MESSIER_FALLBACK: dict[int, dict] = {
    # M24: Pequena Nuvem Estelar de Sagitário (não é NGC; IC 4715 aproxima)
    24: {"name": "M 24", "type": "*Ass", "klass": "OTHER",
         "ra_h": 18.28, "dec_deg": -18.55, "mag": 4.6, "maj": 95.0, "min": 35.0,
         "con": "Sgr", "common": "Pequena Nuvem Estelar de Sagitário"},
    # M40: Winnecke 4 (estrela dupla)
    40: {"name": "M 40", "type": "**", "klass": "OTHER",
         "ra_h": 12.37014, "dec_deg": 58.083, "mag": 9.7, "maj": 0.8,
         "con": "UMa", "common": "Winnecke 4"},
    # M45: Plêiades
    45: {"name": "M 45", "type": "OCl", "klass": "OC",
         "ra_h": 3.7833, "dec_deg": 24.1167, "mag": 1.6, "maj": 110.0,
         "con": "Tau", "common": "Plêiades"},
    # M102: identificação adotada = NGC 5866
    102: {"link": "NGC5866"},
}


def patch_messier(b: Builder) -> None:
    have = {
        int(row[0]) for row in b.cx.execute(
            "SELECT ident FROM designations WHERE catalog='M'"
        )
    }
    for m_num in range(1, 111):
        if m_num in have:
            continue
        patch = MESSIER_FALLBACK.get(m_num)
        if patch is None:
            print(f"  [!] M{m_num} ausente e sem fallback definido")
            continue
        if "link" in patch:
            target = patch["link"]
            oid = b.by_ngc.get(target) or b.by_ngc.get(b.dup_map.get(target, ""))
            if oid is None:
                print(f"  [!] M{m_num}: alvo {target} não encontrado")
                continue
        else:
            oid = b.add_object(
                name=patch["name"], type=patch["type"], klass=patch["klass"],
                ra=patch["ra_h"] * math.pi / 12.0,
                dec=math.radians(patch["dec_deg"]),
                mag=patch.get("mag"), maj=patch.get("maj"),
                min=patch.get("min"), con=patch.get("con"),
                common=patch.get("common"),
                notes="Entrada adicionada pelo build (fora do OpenNGC).",
            )
            # Mel 22 = Plêiades
            if m_num == 45:
                b.add_desig(oid, "Mel", "22")
        b.add_desig(oid, "M", str(m_num))
        print(f"  [+] M{m_num} adicionado via fallback")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    b = Builder()
    load_openngc(b, args.force)
    load_sh2(b, args.force)
    load_barnard(b, args.force)
    load_melotte(b, args.force)
    apply_caldwell(b)
    print("== Messier: verificação 1..110 ==")
    patch_messier(b)

    b.cx.execute("INSERT INTO categories (name) VALUES ('Favoritos')")
    import datetime as dt

    b.cx.execute(
        "INSERT INTO meta VALUES ('built_at', ?)",
        (dt.datetime.now(dt.timezone.utc).isoformat(),),
    )
    b.cx.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    b.cx.commit()

    total = b.cx.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    for cat in ("M", "C", "NGC", "IC", "SH2", "B", "Mel"):
        n = b.cx.execute(
            "SELECT COUNT(DISTINCT object_id) FROM designations WHERE catalog=?",
            (cat,),
        ).fetchone()[0]
        print(f"  {cat}: {n}")
    print(f"Total: {total:,} objetos -> {DB.name}")
    b.cx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
