"""Planejamento de observação: maratonas Messier e Caldwell (item 8).

Para a noite escolhida, seleciona os objetos do catálogo que ficam
observáveis, atribui a cada um o horário em que está **melhor posicionado**
(maior altitude dentro da janela de escuridão, respeitando a Lua) e monta a
lista em ordem cronológica, com o que se espera ver a olho nu, ao binóculo e
ao telescópio, e uma rota de localização a partir de estrelas brilhantes.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np

from .eclipses import moon_influence_radii
from .twilight import night_info

MIN_ALT_DEG = 20.0        # abaixo disso a atmosfera atrapalha demais
SAMPLE_MINUTES = 15.0


# --- o que se vê, por classe de objeto ------------------------------------
VISUAL_HINTS = {
    "GC": (
        "Bola difusa de luz; em telescópios de 6\" ou mais as bordas começam "
        "a se resolver em estrelas individuais. Use visão periférica para "
        "perceber o halo."
    ),
    "OC": (
        "Grupo solto de estrelas — geralmente o melhor alvo para binóculos e "
        "baixa ampliação, onde cabe inteiro no campo."
    ),
    "GAL": (
        "Mancha oval tênue; procure o núcleo mais brilhante primeiro. "
        "Estrutura espiral só aparece em céus escuros e aberturas maiores."
    ),
    "PN": (
        "Disco pequeno e azulado, quase estelar em baixa ampliação; aumente a "
        "ampliação para separar do fundo. Filtro OIII ajuda muito."
    ),
    "NEB": (
        "Nebulosidade difusa; filtros UHC/OIII aumentam bastante o contraste. "
        "Céu escuro faz mais diferença do que abertura."
    ),
    "DARK": (
        "Região onde as estrelas somem — observe o contraste contra a Via "
        "Láctea, de preferência com binóculo e campo largo."
    ),
    "OTHER": "Alvo de campo largo; comece com a menor ampliação disponível.",
}

BINOCULAR_HINTS = {
    "GC": "Ao binóculo 10×50: pontinho nebuloso, sem resolver estrelas.",
    "OC": "Ao binóculo 10×50: excelente — muitas estrelas já se separam.",
    "GAL": "Ao binóculo 10×50: só as mais brilhantes aparecem, como um borrão.",
    "PN": "Ao binóculo 10×50: indistinguível de uma estrela.",
    "NEB": "Ao binóculo 10×50: mancha clara, melhor com céu bem escuro.",
    "DARK": "Ao binóculo 10×50: o alvo ideal — o contraste é todo o efeito.",
    "OTHER": "Ao binóculo 10×50: vale pelo campo largo.",
}


@dataclass
class PlanEntry:
    when_utc: dt.datetime
    name: str
    common: str
    catalog_id: str
    klass: str
    type_label: str
    magnitude: float | None
    size_arcmin: float | None
    altitude: float          # graus, no horário sugerido
    azimuth: float           # graus
    constellation: str
    moon_sep: float          # graus (999 se a Lua estiver abaixo do horizonte)
    moon_warning: bool
    what_to_see: str
    binocular: str
    how_to_find: str


@dataclass
class ObservingPlan:
    title: str
    night_start: dt.datetime | None
    night_end: dt.datetime | None
    location: str
    entries: list[PlanEntry] = field(default_factory=list)
    skipped: int = 0
    moon_illumination: float = 0.0


def _constellation_name(abbr: str | None, const_names: dict) -> str:
    """Nome da constelação em português (trata Serpens, que vem como Se1/Se2)."""
    from ..catalogs.constnames import CONSTELLATIONS

    if not abbr:
        return ""
    key = abbr.strip()
    if key.startswith("Se"):          # Se1/Se2 = as duas partes de Serpens
        return "Serpente"
    if key in CONSTELLATIONS:
        return CONSTELLATIONS[key][1]
    info = const_names.get(key)
    return info.get("name", key) if info else key


def _cardinal(az_deg: float) -> str:
    names = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste",
             "oeste", "noroeste"]
    return names[int((az_deg % 360) / 45.0 + 0.5) % 8]


def _direction_from(ra0: float, dec0: float, ra1: float, dec1: float) -> str:
    """Direção cardinal celeste de (ra0,dec0) para (ra1,dec1)."""
    dra = (ra1 - ra0 + math.pi) % (2 * math.pi) - math.pi
    ddec = dec1 - dec0
    ew = "leste" if dra > 0 else "oeste"
    ns = "norte" if ddec > 0 else "sul"
    if abs(dra) * math.cos(dec0) > 2.5 * abs(ddec):
        return ew
    if abs(ddec) > 2.5 * abs(dra) * math.cos(dec0):
        return ns
    return f"{ns}{ew}"


def _build_finder(stars, ra: float, dec: float, const_name: str) -> str:
    """Rota de localização a partir das estrelas brilhantes mais próximas."""
    mag_cut = stars.count_brighter_than(3.6)
    if mag_cut == 0:
        return "Use a carta do céu para localizar o campo."
    sub = stars.xyz[:mag_cut]
    cd = math.cos(dec)
    target = np.array([cd * math.cos(ra), cd * math.sin(ra), math.sin(dec)])
    dots = np.clip(sub @ target, -1.0, 1.0)
    order = np.argsort(-dots)[:3]

    parts = []
    for k, idx in enumerate(order):
        sep = math.degrees(math.acos(float(dots[idx])))
        if sep > 35.0:
            continue
        name = (stars.proper.get(int(idx))
                or stars.label(int(idx), "bayer") or "estrela brilhante")
        const_star = stars.con.get(int(idx))
        if k == 0 and const_star:
            name = f"{name} ({_constellation_name(const_star, {})})"
        direction = _direction_from(
            float(stars.ra[idx]), float(stars.dec[idx]), ra, dec
        )
        if k == 0:
            parts.append(
                f"Comece por {name} ({stars.mag[idx]:.1f}) e caminhe "
                f"{sep:.0f}° para {direction}"
            )
        else:
            parts.append(f"{name} fica a {sep:.0f}° ({direction} do alvo)")
    if not parts:
        return (
            f"Sem estrela brilhante próxima: varra a região de "
            f"{const_name} com o buscador em baixa ampliação."
        )
    text = parts[0]
    if len(parts) > 1:
        text += ". Referências: " + "; ".join(parts[1:])
    return text + "."


def build_marathon(engine, dso, stars, catalog: str, ref_utc: dt.datetime,
                   const_names: dict, min_alt: float = MIN_ALT_DEG,
                   max_objects: int | None = None) -> ObservingPlan:
    """Monta o roteiro da maratona (catalog = 'M' ou 'C') para a noite."""
    from ..catalogs.dso import type_label

    info = night_info(engine, ref_utc)
    start = info.civil_dusk or info.sunset
    end = info.civil_dawn or info.sunrise
    if start is None or end is None:
        base = ref_utc.astimezone().replace(hour=19, minute=0, second=0,
                                            microsecond=0)
        start = base.astimezone(dt.timezone.utc)
        end = start + dt.timedelta(hours=10)
    if end <= start:
        end = start + dt.timedelta(hours=10)

    rows = dso.cx.execute(
        "SELECT o.id, o.name, o.common, o.klass, o.type, o.ra, o.dec,"
        " o.mag, o.maj, o.con, d.ident FROM objects o"
        " JOIN designations d ON d.object_id = o.id"
        " WHERE d.catalog = ? AND o.enabled = 1"
        " ORDER BY CAST(d.ident AS INTEGER)",
        (catalog,),
    ).fetchall()

    n = max(2, int((end - start).total_seconds() / (SAMPLE_MINUTES * 60)))
    times = [start + dt.timedelta(minutes=SAMPLE_MINUTES * i)
             for i in range(n + 1)]
    ts = engine.ts.from_datetimes(times)
    mats = [engine.horizontal_matrix(t) for t in ts]

    moon_app = engine.site.at(ts).observe(engine.eph["moon"]).apparent()
    moon_alt, moon_az, _ = moon_app.altaz()
    moon_alt = np.radians(moon_alt.degrees)
    moon_az = np.radians(moon_az.degrees)
    illum = float(engine.moon_illumination(engine.ts.from_datetime(ref_utc)))
    r_crit, _ = moon_influence_radii(illum)

    plan = ObservingPlan(
        title=("Maratona Messier" if catalog == "M" else "Maratona Caldwell"),
        night_start=start, night_end=end, location="", moon_illumination=illum,
    )

    # --- 1. janela de visibilidade de cada objeto -----------------------
    candidates = []
    for row in rows:
        cd = math.cos(row["dec"])
        vec = np.array(
            [cd * math.cos(row["ra"]), cd * math.sin(row["ra"]),
             math.sin(row["dec"])]
        )
        alts = np.array([
            math.asin(max(-1.0, min(1.0, float((vec @ m.T)[2]))))
            for m in mats
        ])
        usable = np.nonzero(np.degrees(alts) >= min_alt)[0]
        if len(usable) == 0:
            plan.skipped += 1
            continue
        candidates.append({
            "row": row, "vec": vec, "alts": alts,
            "first": int(usable[0]), "last": int(usable[-1]),
            "best": int(np.argmax(alts)),
        })

    # --- 2. escalonamento: quem se põe antes é observado antes ----------
    # Numa maratona real os alvos a oeste são urgentes (somem no horizonte)
    # e os do leste podem esperar; um slot por objeto evita empilhar tudo
    # no mesmo minuto.
    candidates.sort(key=lambda c: (c["last"], c["best"]))
    if max_objects:
        candidates = candidates[:max_objects]

    slot_span = max(1, len(times) // max(1, len(candidates) + 1))
    scheduled = []
    cursor = 0
    for cand in candidates:
        # o mais cedo possível, sem passar do fim da janela do objeto
        i = max(cursor, cand["first"])
        if i > cand["last"]:
            i = cand["last"]
        scheduled.append((i, cand))
        cursor = min(len(times) - 1, i + slot_span)
    scheduled.sort(key=lambda s: s[0])

    entries_data = []
    for i, cand in scheduled:
        row = cand["row"]
        alt_rad = float(cand["alts"][i])
        v_h = cand["vec"] @ mats[i].T
        az = math.atan2(float(v_h[1]), float(v_h[0])) % (2 * math.pi)
        cos_sep = (
            math.sin(alt_rad) * math.sin(moon_alt[i])
            + math.cos(alt_rad) * math.cos(moon_alt[i])
            * math.cos(az - moon_az[i])
        )
        moon_up = moon_alt[i] > 0
        sep = (math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))
               if moon_up else 999.0)
        const = _constellation_name(row["con"], const_names)
        entries_data.append((
            times[i], row, math.degrees(alt_rad), math.degrees(az), sep,
            moon_up and sep < math.degrees(r_crit), const,
        ))

    for when, row, alt, az, sep, warn, const in entries_data:
        klass = row["klass"]
        plan.entries.append(PlanEntry(
            when_utc=when,
            name=row["name"],
            common=(row["common"] or "").split(",")[0].strip(),
            catalog_id=f"{catalog} {row['ident']}",
            klass=klass,
            type_label=type_label(row["type"]),
            magnitude=row["mag"],
            size_arcmin=row["maj"],
            altitude=alt,
            azimuth=az,
            constellation=const,
            moon_sep=sep,
            moon_warning=warn,
            what_to_see=VISUAL_HINTS.get(klass, VISUAL_HINTS["OTHER"]),
            binocular=BINOCULAR_HINTS.get(klass, BINOCULAR_HINTS["OTHER"]),
            how_to_find=_build_finder(stars, row["ra"], row["dec"], const),
        ))
    return plan
