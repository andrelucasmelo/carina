"""Planejamento de observação: maratonas de uma noite.

O planejador monta um roteiro executável para a noite escolhida a partir de
um dos sete tipos de maratona:

``M`` / ``C``
    Os catálogos clássicos Messier (110) e Caldwell (109), completos.
``OC`` / ``GC`` / ``NEB`` / ``DARK``
    Maratonas temáticas — aglomerados abertos, aglomerados globulares,
    nebulosas (de emissão/reflexão e planetárias) e nebulosas escuras —
    com um corte de brilho/tamanho para manter a lista exequível.
``BEST``
    "Melhores Objetos da Noite": os alvos mais espetaculares visíveis —
    objetos de céu profundo com nome próprio famoso, os planetas acima do
    horizonte e a Lua quando iluminada — espalhados pela noite inteira.

Como o roteiro é montado
------------------------
1. Para cada candidato calcula-se a **janela de visibilidade**: os
   instantes da noite (amostrados a cada 15 min) em que ele passa da
   altitude mínima (20° por padrão — abaixo disso a massa de ar degrada
   demais a imagem).
2. Os candidatos são ordenados por **urgência**: quem sai de alcance
   primeiro (se põe a oeste) é observado primeiro. É a estratégia clássica
   das maratonas Messier — os alvos do leste podem esperar.
3. Cada objeto recebe um **slot sequencial com a duração configurada**
   (padrão 4 min, ajustável de 3 a 10 no menu) dentro da própria janela,
   e o horário exato tem a altitude/azimute recomputados com precisão.
4. Cada entrada carrega o que se espera ver (olho nu, binóculo 10×50 e
   telescópio, por classe de objeto), a distância à Lua com aviso quando
   ela atrapalha, e uma rota de **star-hopping** gerada a partir das
   estrelas brilhantes (mag < 3,6) mais próximas — as mesmas estrelas-guia
   usadas pelas cartas de localização do PDF.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np

from .eclipses import moon_influence_radii
from .twilight import night_info

MIN_ALT_DEG = 20.0        # abaixo disso a atmosfera atrapalha demais
SAMPLE_MINUTES = 15.0     # resolução da grade de visibilidade
DEFAULT_MINUTES = 4       # tempo padrão de observação por objeto

MARATHON_TITLES = {
    "M": "Maratona Messier",
    "C": "Maratona Caldwell",
    "OC": "Maratona de Aglomerados Abertos",
    "GC": "Maratona de Aglomerados Globulares",
    "NEB": "Maratona de Nebulosas",
    "DARK": "Maratona de Nebulosas Escuras",
    "BEST": "Melhores Objetos da Noite",
}


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

# Dicas específicas dos corpos do Sistema Solar ("Melhores Objetos")
SOLAR_HINTS = {
    "Lua": (
        "Observe ao longo do terminador (a linha dia/noite): é onde as "
        "sombras alongadas revelam crateras e montanhas em relevo. Qualquer "
        "ampliação funciona; um filtro lunar reduz o ofuscamento.",
        "Ao binóculo 10×50: mares, crateras grandes e o terminador nítidos.",
    ),
    "Mercúrio": (
        "Sempre baixo, ao crepúsculo; em telescópio mostra um pequeno disco "
        "com fase, como uma Lua em miniatura.",
        "Ao binóculo 10×50: ponto brilhante no crepúsculo — cuidado com o "
        "Sol abaixo do horizonte.",
    ),
    "Vênus": (
        "O disco exibe fases como a Lua; a ampliação média já as revela. O "
        "brilho é tão intenso que vale observar ainda no crepúsculo.",
        "Ao binóculo 10×50: fase perceptível quando em crescente.",
    ),
    "Marte": (
        "Disco alaranjado; perto das oposições revela calotas polares e "
        "manchas escuras com 150× ou mais em noites de ar parado.",
        "Ao binóculo 10×50: ponto alaranjado brilhante, sem detalhes.",
    ),
    "Júpiter": (
        "As duas faixas equatoriais aparecem já com 50×; as quatro luas "
        "galileanas trocam de posição a cada noite — anote a configuração!",
        "Ao binóculo 10×50: as 4 luas galileanas em fila, espetáculo garantido.",
    ),
    "Saturno": (
        "Os anéis são visíveis a partir de ~30×; com 100× procure a divisão "
        "de Cassini e a lua Titã ao lado.",
        "Ao binóculo 10×50: alongado — os anéis insinuados, Titã visível.",
    ),
    "Urano": (
        "Pequeno disco esverdeado com 150×; distingue-se de uma estrela por "
        "não cintilar e não focar em ponto.",
        "Ao binóculo 10×50: como uma estrela fraca (mag ~5,7).",
    ),
    "Netuno": (
        "Disco azulado minúsculo; precisa de carta detalhada e 200× para "
        "diferenciá-lo de estrela.",
        "Ao binóculo 10×50: no limite, indistinguível de estrela.",
    ),
}


@dataclass
class PlanEntry:
    """Uma parada do roteiro: o que observar, quando e como encontrar."""

    when_utc: dt.datetime
    name: str                # designação primária (M 42, NGC 104, Júpiter…)
    common: str              # nome próprio, se houver
    catalog_id: str          # rótulo exibido na lista/PDF
    klass: str               # GC/OC/GAL/PN/NEB/DARK/PLANET/MOON…
    type_label: str
    magnitude: float | None
    size_arcmin: float | None
    altitude: float          # graus, no horário sugerido
    azimuth: float           # graus
    constellation: str
    moon_sep: float          # graus (999 = Lua abaixo do horizonte)
    moon_warning: bool
    what_to_see: str
    binocular: str
    how_to_find: str
    ra: float = 0.0          # rad ICRS — usados pela carta de localização
    dec: float = 0.0
    guides: list = field(default_factory=list)  # estrelas-guia da rota


@dataclass
class ObservingPlan:
    """O roteiro completo de uma maratona: janela da noite, entradas em
    ordem cronológica e o contexto (local, Lua, tempo por objeto)."""

    title: str
    night_start: dt.datetime | None
    night_end: dt.datetime | None
    location: str
    entries: list[PlanEntry] = field(default_factory=list)
    skipped: int = 0
    moon_illumination: float = 0.0
    minutes_per_object: int = DEFAULT_MINUTES


def _constellation_name(abbr: str | None, const_names: dict) -> str:
    """Nome da constelação em português (trata Serpens, que vem como Se1/Se2)."""
    from ..catalogs.constnames import CONSTELLATIONS

    if not abbr:
        return ""
    key = abbr.strip()
    if key.startswith("Se") and key not in CONSTELLATIONS:
        return "Serpente"      # as duas metades (Caput/Cauda) do IAU
    if key in CONSTELLATIONS:
        return CONSTELLATIONS[key][1]
    info = const_names.get(key)
    return info.get("name", key) if info else key


def _direction_from(ra0: float, dec0: float, ra1: float, dec1: float) -> str:
    """Direção cardinal celeste aproximada de (ra0,dec0) para (ra1,dec1).

    Compara o deslocamento em ascensão reta (corrigido pelo cos δ, para ser
    um ângulo real no céu) com o de declinação e escolhe entre os 8 pontos
    cardeais — suficiente para instruções faladas de star-hopping.
    """
    dra = (ra1 - ra0 + math.pi) % (2 * math.pi) - math.pi
    ddec = dec1 - dec0
    ew = "leste" if dra > 0 else "oeste"
    ns = "norte" if ddec > 0 else "sul"
    if abs(dra) * math.cos(dec0) > 2.5 * abs(ddec):
        return ew
    if abs(ddec) > 2.5 * abs(dra) * math.cos(dec0):
        return ns
    return f"{ns}{ew}"


def _build_finder(stars, ra: float, dec: float,
                  const_name: str) -> tuple[str, list[dict]]:
    """Rota de localização a partir das estrelas brilhantes mais próximas.

    Retorna (texto, guias). As guias — nome, posição e magnitude das
    estrelas de referência — alimentam a carta de localização do PDF, de
    modo que o desenho e o texto contam exatamente a mesma história.
    """
    mag_cut = stars.count_brighter_than(3.6)
    if mag_cut == 0:
        return "Use a carta do céu para localizar o campo.", []
    sub = stars.xyz[:mag_cut]
    cd = math.cos(dec)
    target = np.array([cd * math.cos(ra), cd * math.sin(ra), math.sin(dec)])
    dots = np.clip(sub @ target, -1.0, 1.0)
    order = np.argsort(-dots)[:3]

    parts: list[str] = []
    guides: list[dict] = []
    for k, idx in enumerate(order):
        sep = math.degrees(math.acos(float(dots[idx])))
        if sep > 35.0:
            continue                     # longe demais para servir de guia
        name = (stars.proper.get(int(idx))
                or stars.label(int(idx), "bayer") or "estrela brilhante")
        direction = _direction_from(
            float(stars.ra[idx]), float(stars.dec[idx]), ra, dec
        )
        guides.append({
            "name": name,
            "ra": float(stars.ra[idx]),
            "dec": float(stars.dec[idx]),
            "mag": float(stars.mag[idx]),
            "sep": sep,
        })
        if k == 0:
            display = name
            const_star = stars.con.get(int(idx))
            if const_star:
                display = f"{name} ({_constellation_name(const_star, {})})"
            parts.append(
                f"Comece por {display} ({stars.mag[idx]:.1f}) e caminhe "
                f"{sep:.0f}° para {direction}"
            )
        else:
            parts.append(f"{name} fica a {sep:.0f}° ({direction} do alvo)")
    if not parts:
        return (
            f"Sem estrela brilhante próxima: varra a região de "
            f"{const_name} com o buscador em baixa ampliação.", []
        )
    text = parts[0]
    if len(parts) > 1:
        text += ". Referências: " + "; ".join(parts[1:])
    return text + ".", guides


# ---------------------------------------------------------------------------
# Seleção de candidatos por tipo de maratona
# ---------------------------------------------------------------------------

def _catalog_rows(dso, catalog: str) -> list[tuple[dict, str]]:
    """Objetos de um catálogo designado (M/C), com o rótulo 'M 42'."""
    rows = dso.cx.execute(
        "SELECT o.id, o.name, o.common, o.klass, o.type, o.ra, o.dec,"
        " o.mag, o.maj, o.con, d.ident FROM objects o"
        " JOIN designations d ON d.object_id = o.id"
        " WHERE d.catalog = ? AND o.enabled = 1"
        " ORDER BY CAST(d.ident AS INTEGER)",
        (catalog,),
    ).fetchall()
    return [(dict(r), f"{catalog} {r['ident']}") for r in rows]


def _class_rows(dso, kind: str) -> list[tuple[dict, str]]:
    """Objetos de uma maratona temática, com corte para lista exequível.

    Os cortes escolhem alvos realmente observáveis num telescópio amador:
      * aglomerados abertos/globulares e nebulosas: pelos mais brilhantes;
      * nebulosas escuras: sem magnitude por natureza — pelo TAMANHO
        (grandes o bastante para o contraste ser perceptível).
    """
    if kind == "OC":
        where, order = "o.klass = 'OC' AND o.mag <= 8.0", "o.mag"
    elif kind == "GC":
        where, order = "o.klass = 'GC' AND o.mag <= 9.5", "o.mag"
    elif kind == "NEB":
        where = ("o.klass IN ('NEB', 'PN') AND o.mag <= 10.0"
                 " AND o.mag IS NOT NULL")
        order = "o.mag"
    else:  # DARK
        where, order = "o.klass = 'DARK' AND o.maj >= 40.0", "o.maj DESC"
    rows = dso.cx.execute(
        "SELECT o.id, o.name, o.common, o.klass, o.type, o.ra, o.dec,"
        f" o.mag, o.maj, o.con FROM objects o WHERE {where} AND o.enabled = 1"
        f" ORDER BY {order} LIMIT 110",
    ).fetchall()
    return [(dict(r), r["name"]) for r in rows]


def _best_rows(dso) -> list[tuple[dict, str]]:
    """Céu profundo dos "Melhores Objetos": famosos, brilhantes ou enormes."""
    rows = dso.cx.execute(
        "SELECT o.id, o.name, o.common, o.klass, o.type, o.ra, o.dec,"
        " o.mag, o.maj, o.con FROM objects o"
        " WHERE o.enabled = 1 AND o.common != '' AND o.klass != 'DARK'"
        " AND (o.mag <= 8.0 OR o.maj >= 90.0)"
        " ORDER BY COALESCE(o.mag, 99) LIMIT 60",
    ).fetchall()
    out = []
    for r in rows:
        label = (r["common"] or "").split(",")[0].strip() or r["name"]
        out.append((dict(r), label))
    return out


def _solar_system_candidates(engine, t_mid) -> list[tuple[dict, str]]:
    """Planetas (e a Lua) como candidatos dos "Melhores Objetos da Noite".

    A posição usada é a do MEIO da noite: os planetas se movem menos de um
    arco-minuto em horas, erro irrelevante para um roteiro de observação
    (a Lua, mais rápida, ainda fica dentro de ~3°, suficiente para
    escalonar o horário — o mapa mostra a posição exata ao vivo).
    """
    out = []
    obs = engine.site.at(t_mid)
    illum = float(engine.moon_illumination(t_mid))
    bodies = [
        ("Mercúrio", -0.5), ("Vênus", -4.2), ("Marte", 0.8),
        ("Júpiter", -2.4), ("Saturno", 0.6), ("Urano", 5.7),
        ("Netuno", 7.9),
    ]
    if illum >= 0.05:
        # a Lua só entra quando há fase para ver (na nova não há alvo)
        bodies.insert(0, ("Lua", -11.0))
    for name, mag in bodies:
        try:
            app = obs.observe(engine.eph[engine.body_key(name)]).apparent()
        except KeyError:
            continue
        v = np.asarray(app.position.au, dtype=np.float64)
        v /= np.linalg.norm(v)
        ra = math.atan2(float(v[1]), float(v[0])) % (2 * math.pi)
        dec = math.asin(max(-1.0, min(1.0, float(v[2]))))
        klass = "MOON" if name == "Lua" else "PLANET"
        row = {
            "id": -1, "name": name, "common": name, "klass": klass,
            "type": klass, "ra": ra, "dec": dec,
            "mag": (round(illum * 100) / 10 - 11 if name == "Lua" else mag),
            "maj": None, "con": "",
        }
        out.append((row, name))
    return out


# ---------------------------------------------------------------------------
# Montagem do roteiro
# ---------------------------------------------------------------------------

def build_marathon(engine, dso, stars, kind: str, ref_utc: dt.datetime,
                   const_names: dict, min_alt: float = MIN_ALT_DEG,
                   minutes_per_object: int = DEFAULT_MINUTES,
                   max_objects: int | None = None) -> ObservingPlan:
    """Monta o roteiro da maratona ``kind`` para a noite de ``ref_utc``.

    Ver a doc do módulo para o algoritmo. ``minutes_per_object`` é o tempo
    reservado a cada alvo (3–10 min); na maratona "BEST" o passo é
    esticado para que o roteiro cubra a noite inteira.
    """
    from ..catalogs.dso import type_label

    # 1) janela da noite: do crepúsculo civil do anoitecer ao do amanhecer
    #    (antes disso o céu está claro demais até para alvos brilhantes)
    info = night_info(engine, ref_utc)
    start = info.civil_dusk or info.sunset
    end = info.civil_dawn or info.sunrise
    if start is None or end is None:
        # latitudes extremas sem crepúsculo definido: janela fixa de 10 h
        from .localtime import to_local

        base = to_local(ref_utc).replace(hour=19, minute=0, second=0,
                                         microsecond=0)
        start = base.astimezone(dt.timezone.utc)
        end = start + dt.timedelta(hours=10)
    if end <= start:
        end = start + dt.timedelta(hours=10)

    # 2) candidatos do tipo pedido
    if kind in ("M", "C"):
        candidates_rows = _catalog_rows(dso, kind)
    elif kind == "BEST":
        t_mid = engine.ts.from_datetime(start + (end - start) / 2)
        candidates_rows = (_best_rows(dso)
                           + _solar_system_candidates(engine, t_mid))
    else:
        candidates_rows = _class_rows(dso, kind)

    # 3) grade de amostragem da noite (15 min) e efemérides comuns
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
        title=MARATHON_TITLES.get(kind, kind),
        night_start=start, night_end=end, location="",
        moon_illumination=illum,
        minutes_per_object=int(minutes_per_object),
    )

    # 4) janela de visibilidade de cada candidato
    candidates = []
    for row, label in candidates_rows:
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
            "row": row, "label": label, "vec": vec,
            "first": int(usable[0]), "last": int(usable[-1]),
        })

    # 5) escalonamento por urgência: quem se põe antes é observado antes.
    #    O cursor avança o tempo configurado por objeto; na maratona da
    #    noite inteira o passo é esticado para preencher toda a janela.
    candidates.sort(key=lambda c: (c["last"], c["first"]))
    if max_objects:
        candidates = candidates[:max_objects]

    night_minutes = (end - start).total_seconds() / 60.0
    step_min = float(minutes_per_object)
    if kind == "BEST" and candidates:
        step_min = max(step_min, night_minutes / (len(candidates) + 1))

    scheduled: list[tuple[dt.datetime, dict]] = []
    cursor = 0.0
    for cand in candidates:
        first_min = cand["first"] * SAMPLE_MINUTES
        last_min = cand["last"] * SAMPLE_MINUTES
        when_min = max(cursor, first_min)
        if when_min > last_min:
            # o slot só abriria depois de o objeto sair de alcance:
            # observa-o no último instante ainda válido (fora de ordem,
            # mas é isso que um maratonista faria)
            when_min = last_min
        scheduled.append((start + dt.timedelta(minutes=when_min), cand))
        cursor = when_min + step_min
    scheduled.sort(key=lambda s: s[0])

    # 6) entradas finais com alt/az EXATOS no horário agendado
    for when, cand in scheduled:
        row = cand["row"]
        t_exact = engine.ts.from_datetime(when)
        m_exact = engine.horizontal_matrix(t_exact)
        v_h = cand["vec"] @ m_exact.T
        alt_rad = math.asin(max(-1.0, min(1.0, float(v_h[2]))))
        az = math.atan2(float(v_h[1]), float(v_h[0])) % (2 * math.pi)

        # separação da Lua no índice de grade mais próximo (erro < 8 min
        # de movimento lunar ≈ 0,07° — irrelevante para o aviso)
        gi = min(len(times) - 1,
                 int(round((when - start).total_seconds() / 60.0
                           / SAMPLE_MINUTES)))
        cos_sep = (
            math.sin(alt_rad) * math.sin(moon_alt[gi])
            + math.cos(alt_rad) * math.cos(moon_alt[gi])
            * math.cos(az - moon_az[gi])
        )
        moon_up = moon_alt[gi] > 0
        sep = (math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))
               if moon_up else 999.0)

        klass = row["klass"]
        if klass in ("PLANET", "MOON"):
            what, bino = SOLAR_HINTS.get(
                row["name"], (VISUAL_HINTS["OTHER"], BINOCULAR_HINTS["OTHER"])
            )
            finder = ("É o ponto mais brilhante da região — visível a olho "
                      "nu; aponte diretamente." if row["name"] != "Netuno"
                      else "Use a busca do Carina para centralizar e siga "
                           "as estrelas do campo.")
            guides: list[dict] = []
            tipo = "Lua" if klass == "MOON" else "Planeta"
            moon_w = False if klass == "MOON" else (
                moon_up and sep < math.degrees(r_crit))
        else:
            what = VISUAL_HINTS.get(klass, VISUAL_HINTS["OTHER"])
            bino = BINOCULAR_HINTS.get(klass, BINOCULAR_HINTS["OTHER"])
            finder, guides = _build_finder(
                stars, row["ra"], row["dec"],
                _constellation_name(row["con"], const_names),
            )
            tipo = type_label(row["type"])
            moon_w = moon_up and sep < math.degrees(r_crit)

        plan.entries.append(PlanEntry(
            when_utc=when,
            name=row["name"],
            common=(row["common"] or "").split(",")[0].strip(),
            catalog_id=cand["label"],
            klass=klass,
            type_label=tipo,
            magnitude=row["mag"],
            size_arcmin=row["maj"],
            altitude=math.degrees(alt_rad),
            azimuth=math.degrees(az),
            constellation=_constellation_name(row["con"], const_names),
            moon_sep=sep,
            moon_warning=moon_w,
            what_to_see=what,
            binocular=bino,
            how_to_find=finder,
            ra=row["ra"],
            dec=row["dec"],
            guides=guides,
        ))
    return plan
