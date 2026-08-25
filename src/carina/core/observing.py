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
    "MONTH": "Destaques do Mês",
    "SEASON": "Destaques da Estação",
    "STARS": "Estrelas Brilhantes",
}

# Limites de instrumento por magnitude — a fronteira é prática, não
# rigorosa: depende do céu e do objeto, mas serve para dizer ao
# observador com o que vale a pena tentar cada alvo.
MAG_NAKED_EYE = 5.5
MAG_BINOCULAR = 8.5
MAG_SMALL_SCOPE = 10.5

INSTRUMENT_LABEL = {
    "olho": "A olho nu",
    "binoculo": "Binóculo",
    "pequeno": "Pequeno telescópio",
    "medio": "Telescópio médio",
}


def instrument_for(mag: float | None, size_arcmin: float | None,
                   klass: str = "") -> str:
    """Menor instrumento com que o objeto vale a pena.

    Objetos MUITO grandes (mais de 1°) ganham um degrau de vantagem: o
    brilho se espalha, mas o contraste de campo largo compensa — é o caso
    das Híades, do Véu ou das Nuvens de Magalhães. Nebulosas escuras não
    têm magnitude e vivem de contraste: são alvo de binóculo.
    """
    if klass == "DARK":
        return "binoculo"
    if mag is None:
        return "pequeno"
    big = bool(size_arcmin and size_arcmin >= 60.0)
    limit_naked = MAG_NAKED_EYE + (1.0 if big else 0.0)
    limit_bino = MAG_BINOCULAR + (1.0 if big else 0.0)
    if mag <= limit_naked:
        return "olho"
    if mag <= limit_bino:
        return "binoculo"
    if mag <= MAG_SMALL_SCOPE:
        return "pequeno"
    return "medio"


@dataclass
class PlanSettings:
    """Configuração do planejamento (diálogo "Configurar planejamento").

    A janela de observação padrão é a **noite astronômica** — o céu
    realmente escuro. O usuário pode esticá-la para o crepúsculo civil
    (ou fixar horários), mas o trecho fora da noite astronômica só
    recebe objetos **bem brilhantes**: com o céu ainda claro, alvos
    fracos seriam frustração garantida.
    """

    minutes_per_object: int = DEFAULT_MINUTES
    start_mode: str = "astro"     # 'astro' | 'civil' | 'sunset' | 'custom'
    end_mode: str = "astro"       # idem (lado do amanhecer)
    custom_start: dt.time = dt.time(19, 0)
    custom_end: dt.time = dt.time(5, 0)
    min_altitude: float = MIN_ALT_DEG
    twilight_mag_limit: float = MAG_NAKED_EYE   # brilho exigido no crepúsculo

    def clamp(self) -> "PlanSettings":
        """Garante valores dentro das faixas aceitas."""
        self.minutes_per_object = max(3, min(10, int(self.minutes_per_object)))
        self.min_altitude = max(5.0, min(60.0, float(self.min_altitude)))
        return self


@dataclass
class ObservingWindow:
    """Janela de observação resolvida para uma noite concreta."""

    start: dt.datetime
    end: dt.datetime
    dark_start: dt.datetime | None   # início da noite astronômica
    dark_end: dt.datetime | None     # fim da noite astronômica
    label: str = ""

    def is_dark(self, when: dt.datetime) -> bool:
        """O céu está realmente escuro neste instante?"""
        if self.dark_start is None or self.dark_end is None:
            return True          # sem crepúsculo definido: trata como escuro
        return self.dark_start <= when <= self.dark_end


def resolve_window(engine, ref_utc: dt.datetime,
                   settings: PlanSettings) -> ObservingWindow:
    """Traduz a configuração em instantes concretos para a noite dada.

    Cada extremo pode vir do crepúsculo astronômico (padrão), do civil,
    do pôr/nascer do sol ou de um horário fixo digitado pelo usuário.
    Quando o crepúsculo escolhido não existe naquela data (verão de
    latitudes altas), cai para a alternativa mais próxima disponível.
    """
    from .localtime import from_local_naive, to_local

    info = night_info(engine, ref_utc)

    def pick(mode: str, evening: bool) -> dt.datetime | None:
        if evening:
            chain = {
                "astro": (info.astro_dusk, info.nautical_dusk,
                          info.civil_dusk, info.sunset),
                "civil": (info.civil_dusk, info.sunset, info.nautical_dusk),
                "sunset": (info.sunset, info.civil_dusk),
            }.get(mode, ())
        else:
            chain = {
                "astro": (info.astro_dawn, info.nautical_dawn,
                          info.civil_dawn, info.sunrise),
                "civil": (info.civil_dawn, info.sunrise, info.nautical_dawn),
                "sunset": (info.sunrise, info.civil_dawn),
            }.get(mode, ())
        for value in chain:
            if value is not None:
                return value
        return None

    start = end = None
    if settings.start_mode == "custom":
        base = to_local(ref_utc)
        naive = dt.datetime.combine(base.date(), settings.custom_start)
        start = from_local_naive(naive).astimezone(dt.timezone.utc)
    else:
        start = pick(settings.start_mode, True)
    if settings.end_mode == "custom":
        base = to_local(ref_utc)
        naive = dt.datetime.combine(base.date(), settings.custom_end)
        end = from_local_naive(naive).astimezone(dt.timezone.utc)
        if end <= (start or ref_utc):
            end += dt.timedelta(days=1)      # madrugada do dia seguinte
    else:
        end = pick(settings.end_mode, False)

    if start is None or end is None:
        base = to_local(ref_utc).replace(hour=19, minute=0, second=0,
                                         microsecond=0)
        start = start or base.astimezone(dt.timezone.utc)
        end = end or (start + dt.timedelta(hours=10))
    if end <= start:
        end = start + dt.timedelta(hours=10)

    label = {
        "astro": "noite astronômica", "civil": "crepúsculo civil",
        "sunset": "pôr do sol", "custom": "horário fixo",
    }
    return ObservingWindow(
        start=start, end=end,
        dark_start=info.astro_dusk, dark_end=info.astro_dawn,
        label=(f"{label.get(settings.start_mode, '')} → "
               f"{label.get(settings.end_mode, '')}"),
    )


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
    instrument: str = "pequeno"   # menor instrumento que vale a pena
    in_twilight: bool = False     # agendado fora da noite astronômica
    note: str = ""                # observação livre (planos genéricos)


@dataclass
class ObservingPlan:
    """O roteiro completo: janela, entradas em ordem e o contexto."""

    title: str
    night_start: dt.datetime | None
    night_end: dt.datetime | None
    location: str
    entries: list[PlanEntry] = field(default_factory=list)
    skipped: int = 0
    moon_illumination: float = 0.0
    minutes_per_object: int = DEFAULT_MINUTES
    window_label: str = ""
    subtitle: str = ""            # período coberto (mês, estação…)
    timed: bool = True            # False = lista curada, sem horários


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


MIN_GUIDES = 2            # sempre mais de uma referência (pedido do usuário)
MAX_GUIDES = 3
GUIDE_SEP_LIMIT = 35.0    # limite confortável de "salto" entre guias


def _build_finder(stars, ra: float, dec: float, const_name: str,
                  skip_index: int | None = None) -> tuple[str, list[dict]]:
    """Rota de localização a partir das estrelas brilhantes mais próximas.

    Retorna (texto, guias). As guias — nome, posição, magnitude e
    separação em GRAUS — alimentam a carta de localização do PDF, de modo
    que o desenho e o texto contam exatamente a mesma história.

    Duas ou três referências são sempre entregues: uma só permite chegar
    a uma direção, mas duas permitem TRIANGULAR o alvo, que é como se
    encontra um objeto invisível a olho nu. Se não houver duas estrelas
    de 3ª magnitude por perto, o corte de brilho é afrouxado por etapas
    até 5ª — melhor uma guia mais fraca do que nenhuma.

    ``skip_index`` exclui a própria estrela quando o alvo é estelar.
    """
    cd = math.cos(dec)
    target = np.array([cd * math.cos(ra), cd * math.sin(ra), math.sin(dec)])

    chosen: list[int] = []
    dots = None
    for mag_cut, sep_limit in ((3.6, GUIDE_SEP_LIMIT),
                               (4.5, GUIDE_SEP_LIMIT),
                               (5.0, GUIDE_SEP_LIMIT * 1.6)):
        count = stars.count_brighter_than(mag_cut)
        if count == 0:
            continue
        dots = np.clip(stars.xyz[:count] @ target, -1.0, 1.0)
        order = np.argsort(-dots)
        chosen = []
        for idx in order[:MAX_GUIDES + 2]:
            if skip_index is not None and int(idx) == skip_index:
                continue
            if math.degrees(math.acos(float(dots[idx]))) > sep_limit:
                break
            chosen.append(int(idx))
            if len(chosen) >= MAX_GUIDES:
                break
        if len(chosen) >= MIN_GUIDES:
            break

    if not chosen or dots is None:
        return (
            f"Sem estrela brilhante próxima: varra a região de "
            f"{const_name} com o buscador em baixa ampliação.", []
        )

    guides: list[dict] = []
    parts: list[str] = []
    for k, idx in enumerate(chosen):
        sep = math.degrees(math.acos(float(dots[idx])))
        name = (stars.proper.get(idx) or stars.label(idx, "bayer")
                or "estrela brilhante")
        direction = _direction_from(
            float(stars.ra[idx]), float(stars.dec[idx]), ra, dec
        )
        guides.append({
            "name": name,
            "ra": float(stars.ra[idx]),
            "dec": float(stars.dec[idx]),
            "mag": float(stars.mag[idx]),
            "sep": sep,
            "direction": direction,
            "primary": k == 0,
        })
        if k == 0:
            display = name
            const_star = stars.con.get(idx)
            if const_star:
                display = f"{name} ({_constellation_name(const_star, {})})"
            parts.append(
                f"Comece por {display}, de magnitude {stars.mag[idx]:.1f}, "
                f"e caminhe {sep:.1f}° para {direction}"
            )
        else:
            parts.append(
                f"{name} ({stars.mag[idx]:.1f}) fica a {sep:.1f}° do alvo, "
                f"{direction} dele"
            )
    text = parts[0] + "."
    if len(parts) > 1:
        text += (" Para confirmar o campo, triangule: "
                 + "; ".join(parts[1:]) + ".")
    return text, guides


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
                   const_names: dict, min_alt: float | None = None,
                   minutes_per_object: int | None = None,
                   max_objects: int | None = None,
                   settings: PlanSettings | None = None) -> ObservingPlan:
    """Monta o roteiro da maratona ``kind`` para a noite de ``ref_utc``.

    Ver a doc do módulo para o algoritmo. A janela e o ritmo vêm de
    ``settings`` (:class:`PlanSettings`); os parâmetros soltos existem
    por compatibilidade e sobrescrevem os campos correspondentes.
    """
    from ..catalogs.dso import type_label

    settings = (settings or PlanSettings()).clamp()
    if minutes_per_object is not None:
        settings.minutes_per_object = int(minutes_per_object)
    if min_alt is not None:
        settings.min_altitude = float(min_alt)
    min_alt = settings.min_altitude

    # 1) janela da noite conforme a configuração (padrão: astronômica)
    window = resolve_window(engine, ref_utc, settings)
    start, end = window.start, window.end

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
        minutes_per_object=settings.minutes_per_object,
        window_label=window.label,
    )

    # 4) janela de visibilidade de cada candidato.
    #    Objetos fracos ficam restritos à noite astronômica: no crepúsculo
    #    o céu ainda tem luz e só alvos bem brilhantes valem a tentativa.
    dark_first = dark_last = None
    if window.dark_start is not None and window.dark_end is not None:
        for i, when in enumerate(times):
            if window.is_dark(when):
                dark_first = i if dark_first is None else dark_first
                dark_last = i

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
        first, last = int(usable[0]), int(usable[-1])

        mag = row["mag"]
        bright = mag is not None and mag <= settings.twilight_mag_limit
        if not bright and dark_first is not None:
            # recorta a janela do objeto para dentro da noite escura
            first = max(first, dark_first)
            last = min(last, dark_last)
            if first > last:
                plan.skipped += 1
                continue
        candidates.append({
            "row": row, "label": label, "vec": vec,
            "first": first, "last": last,
        })

    # 5) escalonamento por urgência: quem se põe antes é observado antes.
    #    O cursor avança o tempo configurado por objeto; na maratona da
    #    noite inteira o passo é esticado para preencher toda a janela.
    candidates.sort(key=lambda c: (c["last"], c["first"]))
    if max_objects:
        candidates = candidates[:max_objects]

    night_minutes = (end - start).total_seconds() / 60.0
    step_min = float(settings.minutes_per_object)
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
            instrument=instrument_for(row["mag"], row["maj"], klass),
            in_twilight=not window.is_dark(when),
        ))
    return plan


# ---------------------------------------------------------------------------
# Planejamentos genéricos: mês, estação e estrelas brilhantes
# ---------------------------------------------------------------------------

MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# Estações por trimestre no hemisfério NORTE (mês inicial → nome). No
# hemisfério sul as mesmas datas correspondem à estação oposta — o que o
# planejador resolve pela latitude do observador.
_SEASON_NORTH = {
    (12, 1, 2): "Inverno", (3, 4, 5): "Primavera",
    (6, 7, 8): "Verão", (9, 10, 11): "Outono",
}
_OPPOSITE = {
    "Inverno": "Verão", "Verão": "Inverno",
    "Primavera": "Outono", "Outono": "Primavera",
}


def season_of(when: dt.datetime, latitude: float) -> tuple[str, list[int]]:
    """Estação e seus três meses, do ponto de vista do OBSERVADOR.

    A mesma data é inverno no norte e verão no sul: a latitude decide.
    Devolve (nome da estação, [meses]).
    """
    month = when.month
    for months, name in _SEASON_NORTH.items():
        if month in months:
            if latitude < 0:
                name = _OPPOSITE[name]
            return name, list(months)
    return "", [month]


# Tipos que existem no catálogo mas não são alvo de observação visual:
# novas e estrelas isoladas (não são "céu profundo"), duplicatas e
# entradas inexistentes herdadas dos catálogos históricos.
_NOT_SHOWPIECES = ("Nova", "Dup", "NonEx", "*", "**", "Other")


def _curated_rows(dso, limit: int = 400) -> list:
    """Objetos que valem uma noite: brilhantes ou grandes o suficiente.

    O corte elimina o que só aparece em astrofotografia — a lista é para
    apreciar a olho nu, ao binóculo ou em pequenos telescópios — e também
    o que não é espetáculo nenhum: novas, estrelas isoladas, duplicatas e
    entradas sem designação de catálogo reconhecível (nomes internos como
    "MWSC3171" não ajudam ninguém a achar nada no campo).
    """
    marks = ",".join("?" * len(_NOT_SHOWPIECES))
    return dso.cx.execute(
        "SELECT o.id, o.name, o.common, o.klass, o.type, o.ra, o.dec,"
        " o.mag, o.maj, o.con FROM objects o"
        " WHERE o.enabled = 1"
        f"   AND o.type NOT IN ({marks})"
        "   AND (o.name LIKE 'M %' OR o.name LIKE 'NGC%'"
        "        OR o.name LIKE 'IC %' OR o.common != '')"
        "   AND (o.mag <= ? OR (o.maj >= 60.0 AND o.klass != 'DARK'))"
        " ORDER BY COALESCE(o.mag, 99) LIMIT ?",
        (*_NOT_SHOWPIECES, MAG_SMALL_SCOPE, limit),
    ).fetchall()


def _nights_of(engine, year: int, months: list[int],
               settings: PlanSettings) -> list[dt.datetime]:
    """Instantes de referência (meio da noite escura) ao longo do período.

    Amostra os dias 5, 15 e 25 de cada mês: o suficiente para exigir que
    um objeto esteja bem posicionado durante TODO o período, sem o custo
    de calcular noite a noite.
    """
    out = []
    for month in months:
        for day in (5, 15, 25):
            try:
                ref = dt.datetime(year, month, day, 23, 0,
                                  tzinfo=dt.timezone.utc)
            except ValueError:
                continue
            w = resolve_window(engine, ref, settings)
            out.append(w.start + (w.end - w.start) / 2)
    return out


def build_period_plan(engine, dso, stars, kind: str, ref_utc: dt.datetime,
                      const_names: dict, latitude: float,
                      settings: PlanSettings | None = None,
                      max_objects: int = 40) -> ObservingPlan:
    """Lista curada do mês ou da estação (``kind`` = 'MONTH' | 'SEASON').

    Diferente das maratonas, aqui não há horário de parada: são objetos
    que valem a pena durante TODO o período. O critério é exigente de
    propósito — o objeto precisa passar da altitude mínima no meio da
    noite em **todas** as datas amostradas, para que a lista continue
    válida em qualquer noite do mês (ou da estação).
    """
    from ..catalogs.dso import type_label

    settings = (settings or PlanSettings()).clamp()
    local_ref = ref_utc
    if kind == "SEASON":
        season, months = season_of(local_ref, latitude)
        subtitle = f"{season} — {', '.join(MONTHS_PT[m - 1] for m in months)}"
        title = f"Destaques da Estação · {season}"
    else:
        months = [local_ref.month]
        subtitle = f"{MONTHS_PT[local_ref.month - 1]} de {local_ref.year}"
        title = f"Destaques de {MONTHS_PT[local_ref.month - 1].capitalize()}"

    nights = _nights_of(engine, local_ref.year, months, settings)
    if not nights:
        nights = [local_ref]
    ts = engine.ts.from_datetimes(nights)
    mats = [engine.horizontal_matrix(t) for t in ts]

    rows = _curated_rows(dso)
    plan = ObservingPlan(
        title=title, night_start=None, night_end=None, location="",
        minutes_per_object=settings.minutes_per_object,
        subtitle=subtitle, timed=False,
        window_label="visível durante todo o período",
    )

    scored = []
    for row in rows:
        cd = math.cos(row["dec"])
        vec = np.array([cd * math.cos(row["ra"]), cd * math.sin(row["ra"]),
                        math.sin(row["dec"])])
        alts = [math.degrees(math.asin(
            max(-1.0, min(1.0, float((vec @ m.T)[2])))
        )) for m in mats]
        if min(alts) < settings.min_altitude:
            plan.skipped += 1
            continue                       # some em alguma noite do período
        scored.append((sum(alts) / len(alts), row, vec, max(alts)))

    # os mais altos primeiro: é onde a atmosfera atrapalha menos
    scored.sort(key=lambda s: -s[0])
    mid = ts[len(ts) // 2]
    m_mid = engine.horizontal_matrix(mid)

    for mean_alt, row, vec, best_alt in scored[:max_objects]:
        v_h = vec @ m_mid.T
        az = math.atan2(float(v_h[1]), float(v_h[0])) % (2 * math.pi)
        finder, guides = _build_finder(
            stars, row["ra"], row["dec"],
            _constellation_name(row["con"], const_names),
        )
        instrument = instrument_for(row["mag"], row["maj"], row["klass"])
        plan.entries.append(PlanEntry(
            when_utc=mid.utc_datetime(),
            name=row["name"],
            common=(row["common"] or "").split(",")[0].strip(),
            catalog_id=row["name"],
            klass=row["klass"],
            type_label=type_label(row["type"]),
            magnitude=row["mag"],
            size_arcmin=row["maj"],
            altitude=best_alt,
            azimuth=math.degrees(az),
            constellation=_constellation_name(row["con"], const_names),
            moon_sep=999.0,
            moon_warning=False,
            what_to_see=VISUAL_HINTS.get(row["klass"], VISUAL_HINTS["OTHER"]),
            binocular=BINOCULAR_HINTS.get(row["klass"],
                                          BINOCULAR_HINTS["OTHER"]),
            how_to_find=finder,
            ra=row["ra"], dec=row["dec"], guides=guides,
            instrument=instrument,
            note=(f"Altitude média no meio da noite: {mean_alt:.0f}°; "
                  f"chega a {best_alt:.0f}° no período."),
        ))
    return plan


def build_bright_stars(engine, stars, ref_utc: dt.datetime,
                       const_names: dict,
                       settings: PlanSettings | None = None,
                       max_objects: int = 30) -> ObservingPlan:
    """As estrelas mais brilhantes do céu do observador nesta noite.

    Ordenadas por brilho (é assim que se aprende o céu: primeiro as que
    saltam aos olhos). Cada uma traz a constelação, o horário em que está
    mais alta e como chegar a ela a partir das vizinhas — as mesmas
    estrelas-guia que alimentam a carta de localização.
    """
    settings = (settings or PlanSettings()).clamp()
    window = resolve_window(engine, ref_utc, settings)
    start, end = window.start, window.end

    n = max(2, int((end - start).total_seconds() / (SAMPLE_MINUTES * 60)))
    times = [start + dt.timedelta(minutes=SAMPLE_MINUTES * i)
             for i in range(n + 1)]
    ts = engine.ts.from_datetimes(times)
    mats = [engine.horizontal_matrix(t) for t in ts]

    plan = ObservingPlan(
        title=MARATHON_TITLES["STARS"],
        night_start=start, night_end=end, location="",
        minutes_per_object=settings.minutes_per_object,
        window_label=window.label, timed=True,
        subtitle="ordenadas por brilho — as que saltam aos olhos primeiro",
        moon_illumination=float(engine.moon_illumination(
            engine.ts.from_datetime(ref_utc)
        )),
    )

    count = stars.count_brighter_than(2.6)     # até 2ª magnitude
    for idx in range(count):
        vec = stars.xyz[idx].astype(np.float64)
        alts = np.array([
            math.asin(max(-1.0, min(1.0, float((vec @ m.T)[2]))))
            for m in mats
        ])
        best = int(np.argmax(alts))
        if math.degrees(alts[best]) < settings.min_altitude:
            plan.skipped += 1
            continue
        v_h = vec @ mats[best].T
        az = math.atan2(float(v_h[1]), float(v_h[0])) % (2 * math.pi)
        name = (stars.proper.get(idx) or stars.label(idx, "bayer")
                or f"HIP {int(stars.hip[idx])}")
        const = _constellation_name(stars.con.get(idx), const_names)
        finder, guides = _build_finder(
            stars, float(stars.ra[idx]), float(stars.dec[idx]), const,
            skip_index=idx,
        )
        mag = float(stars.mag[idx])
        color = _star_color_hint(float(stars.ci[idx]))
        plan.entries.append(PlanEntry(
            when_utc=times[best],
            name=name,
            common=stars.proper.get(idx, ""),
            catalog_id=name,
            klass="STAR",
            type_label="Estrela",
            magnitude=mag,
            size_arcmin=None,
            altitude=math.degrees(alts[best]),
            azimuth=math.degrees(az),
            constellation=const,
            moon_sep=999.0,
            moon_warning=False,
            what_to_see=color,
            binocular=("A olho nu já é evidente; ao binóculo a cor fica "
                       "mais nítida e as companheiras de campo aparecem."),
            how_to_find=finder,
            ra=float(stars.ra[idx]), dec=float(stars.dec[idx]),
            guides=guides,
            instrument="olho",
            in_twilight=not window.is_dark(times[best]),
            note=stars.full_designation(idx),
        ))
        if len(plan.entries) >= max_objects:
            break
    plan.entries.sort(key=lambda e: e.magnitude)
    return plan


def _star_color_hint(ci: float) -> str:
    """O que se vê numa estrela: a cor, que vem do índice de cor B−V."""
    if ci < 0.0:
        tone, kind = "azulada", "muito quente"
    elif ci < 0.3:
        tone, kind = "branco-azulada", "quente"
    elif ci < 0.6:
        tone, kind = "branca", "parecida com o Sol"
    elif ci < 1.0:
        tone, kind = "amarelada", "como o Sol"
    elif ci < 1.5:
        tone, kind = "alaranjada", "mais fria que o Sol"
    else:
        tone, kind = "avermelhada", "fria, muitas vezes gigante"
    return (f"Estrela {tone} ({kind}). A cor aparece melhor com o olhar "
            f"relaxado ou desfocando levemente a imagem no telescópio.")
