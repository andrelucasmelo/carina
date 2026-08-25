"""Gera a base local de cidades para a escolha da localização do observador.

Fonte: GeoNames ``cities15000.zip`` (CC BY 4.0, https://www.geonames.org) —
todas as cidades do mundo com mais de 15 mil habitantes, com coordenadas,
país, fuso horário IANA e elevação (modelo digital de terreno).

Seleção pedida pelo usuário:
  * as 500 cidades mais populosas do mundo;
  * as 100 mais populosas do Brasil, dos EUA, da China e da Europa,
    sem duplicar as que já entraram pelo corte mundial.

O resultado é ``data/processed/cities.json``, embarcado no instalador
(ADR-012: tudo que é baixado vira base local).
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "data" / "processed" / "cities.json"
URL = "https://download.geonames.org/export/dump/cities15000.zip"

# Europa geográfica; a Rússia entra só com a parte a oeste dos Urais
# (lon < 60°). A Turquia fica de fora — Istambul entra pelo corte mundial.
EUROPE = {
    "AD", "AL", "AT", "AX", "BA", "BE", "BG", "BY", "CH", "CY", "CZ", "DE",
    "DK", "EE", "ES", "FI", "FO", "FR", "GB", "GG", "GI", "GR", "HR", "HU",
    "IE", "IM", "IS", "IT", "JE", "LI", "LT", "LU", "LV", "MC", "MD", "ME",
    "MK", "MT", "NL", "NO", "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SM",
    "UA", "VA", "XK",
}

# País em português para exibição (ISO 3166-1 alfa-2 → nome).
COUNTRY_PT = {
    "AD": "Andorra", "AE": "Emirados Árabes Unidos", "AF": "Afeganistão",
    "AL": "Albânia", "AM": "Armênia", "AO": "Angola", "AR": "Argentina",
    "AT": "Áustria", "AU": "Austrália", "AZ": "Azerbaijão",
    "BA": "Bósnia e Herzegovina", "BB": "Barbados", "BD": "Bangladesh",
    "BE": "Bélgica", "BF": "Burquina Fasso", "BG": "Bulgária",
    "BH": "Bahrein", "BI": "Burundi", "BJ": "Benim", "BO": "Bolívia",
    "BR": "Brasil", "BS": "Bahamas", "BT": "Butão", "BW": "Botsuana",
    "BY": "Bielorrússia", "BZ": "Belize", "CA": "Canadá",
    "CD": "República Democrática do Congo", "CF": "República Centro-Africana",
    "CG": "República do Congo", "CH": "Suíça", "CI": "Costa do Marfim",
    "CL": "Chile", "CM": "Camarões", "CN": "China", "CO": "Colômbia",
    "CR": "Costa Rica", "CU": "Cuba", "CV": "Cabo Verde", "CY": "Chipre",
    "CZ": "Tchéquia", "DE": "Alemanha", "DJ": "Djibuti", "DK": "Dinamarca",
    "DO": "República Dominicana", "DZ": "Argélia", "EC": "Equador",
    "EE": "Estônia", "EG": "Egito", "ER": "Eritreia", "ES": "Espanha",
    "ET": "Etiópia", "FI": "Finlândia", "FJ": "Fiji", "FR": "França",
    "GA": "Gabão", "GB": "Reino Unido", "GE": "Geórgia", "GH": "Gana",
    "GM": "Gâmbia", "GN": "Guiné", "GQ": "Guiné Equatorial", "GR": "Grécia",
    "GT": "Guatemala", "GW": "Guiné-Bissau", "GY": "Guiana",
    "HK": "Hong Kong (China)", "HN": "Honduras", "HR": "Croácia",
    "HT": "Haiti", "HU": "Hungria", "ID": "Indonésia", "IE": "Irlanda",
    "IL": "Israel", "IN": "Índia", "IQ": "Iraque", "IR": "Irã",
    "IS": "Islândia", "IT": "Itália", "JM": "Jamaica", "JO": "Jordânia",
    "JP": "Japão", "KE": "Quênia", "KG": "Quirguistão", "KH": "Camboja",
    "KP": "Coreia do Norte", "KR": "Coreia do Sul", "KW": "Kuwait",
    "KZ": "Cazaquistão", "LA": "Laos", "LB": "Líbano", "LK": "Sri Lanka",
    "LR": "Libéria", "LS": "Lesoto", "LT": "Lituânia", "LU": "Luxemburgo",
    "LV": "Letônia", "LY": "Líbia", "MA": "Marrocos", "MC": "Mônaco",
    "MD": "Moldávia", "ME": "Montenegro", "MG": "Madagascar",
    "MK": "Macedônia do Norte", "ML": "Mali", "MM": "Mianmar",
    "MN": "Mongólia", "MO": "Macau (China)", "MR": "Mauritânia",
    "MT": "Malta", "MU": "Maurício", "MV": "Maldivas", "MW": "Malawi",
    "MX": "México", "MY": "Malásia", "MZ": "Moçambique", "NA": "Namíbia",
    "NE": "Níger", "NG": "Nigéria", "NI": "Nicarágua", "NL": "Países Baixos",
    "NO": "Noruega", "NP": "Nepal", "NZ": "Nova Zelândia", "OM": "Omã",
    "PA": "Panamá", "PE": "Peru", "PG": "Papua-Nova Guiné",
    "PH": "Filipinas", "PK": "Paquistão", "PL": "Polônia",
    "PR": "Porto Rico (EUA)", "PS": "Palestina", "PT": "Portugal",
    "PY": "Paraguai", "QA": "Catar", "RO": "Romênia", "RS": "Sérvia",
    "RU": "Rússia", "RW": "Ruanda", "SA": "Arábia Saudita",
    "SD": "Sudão", "SE": "Suécia", "SG": "Singapura", "SI": "Eslovênia",
    "SK": "Eslováquia", "SL": "Serra Leoa", "SN": "Senegal",
    "SO": "Somália", "SR": "Suriname", "SS": "Sudão do Sul",
    "SV": "El Salvador", "SY": "Síria", "SZ": "Essuatíni", "TD": "Chade",
    "TG": "Togo", "TH": "Tailândia", "TJ": "Tadjiquistão",
    "TL": "Timor-Leste", "TM": "Turcomenistão", "TN": "Tunísia",
    "TR": "Turquia", "TT": "Trindade e Tobago", "TW": "Taiwan",
    "TZ": "Tanzânia", "UA": "Ucrânia", "UG": "Uganda",
    "US": "Estados Unidos", "UY": "Uruguai", "UZ": "Uzbequistão",
    "VE": "Venezuela", "VN": "Vietnã", "XK": "Kosovo", "YE": "Iêmen",
    "ZA": "África do Sul",
    "ZM": "Zâmbia", "ZW": "Zimbábue",
}


def download() -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / "cities15000.zip"
    if cached.exists():
        return cached.read_bytes()
    print("baixando", URL)
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    cached.write_bytes(r.content)
    return r.content


def parse(raw: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        text = zf.read("cities15000.txt").decode("utf-8")
    rows = []
    for line in text.splitlines():
        f = line.split("\t")
        if len(f) < 18:
            continue
        pop = int(f[14] or 0)
        if pop <= 0:
            continue
        elev = f[15].strip() or f[16].strip() or "0"
        rows.append({
            "id": int(f[0]),
            "name": f[1],
            "ascii": f[2].lower(),
            "lat": round(float(f[4]), 4),
            "lon": round(float(f[5]), 4),
            "cc": f[8],
            "pop": pop,
            "elev": max(-430, int(float(elev))),
            "tz": f[17].strip(),
        })
    return rows


def is_europe(row: dict) -> bool:
    if row["cc"] in EUROPE:
        return True
    return row["cc"] == "RU" and row["lon"] < 60.0


def main() -> int:
    rows = parse(download())
    rows.sort(key=lambda r: -r["pop"])
    print(f"{len(rows)} cidades na base bruta")

    chosen: dict[int, dict] = {}

    def take(seq, n):
        count = 0
        for row in seq:
            if count >= n:
                break
            if row["id"] not in chosen:
                chosen[row["id"]] = row
                count += 1
        return count

    take(rows, 500)                                       # mundo
    extras = {
        "Brasil": [r for r in rows if r["cc"] == "BR"],
        "EUA": [r for r in rows if r["cc"] == "US"],
        "China": [r for r in rows if r["cc"] == "CN"],
        "Europa": [r for r in rows if is_europe(r)],
    }
    for label, seq in extras.items():
        # garante o TOP 100 da região presente (o que já entrou pelo
        # mundial conta para a cota, sem duplicar)
        top = seq[:100]
        added = 0
        for row in top:
            if row["id"] not in chosen:
                chosen[row["id"]] = row
                added += 1
        print(f"{label}: top {len(top)}, {added} novas")

    out = []
    for row in sorted(chosen.values(), key=lambda r: -r["pop"]):
        out.append({
            "n": row["name"],
            "c": COUNTRY_PT.get(row["cc"], row["cc"]),
            "cc": row["cc"],
            "lat": row["lat"],
            "lon": row["lon"],
            "el": row["elev"],
            "tz": row["tz"],
            "pop": row["pop"],
        })

    missing = {r["cc"] for r in chosen.values()} - set(COUNTRY_PT)
    if missing:
        print("AVISO: países sem nome PT:", sorted(missing))

    OUT.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    kb = OUT.stat().st_size / 1024
    print(f"{len(out)} cidades gravadas em {OUT.name} ({kb:.0f} KB)")
    sample = [f"{c['n']} ({c['c']}, {c['tz']})" for c in out[:5]]
    print("maiores:", "; ".join(sample))
    return 0


if __name__ == "__main__":
    sys.exit(main())
