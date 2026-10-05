"""Tours gerados para a data e o local do usuário (v0.20 T7, T8, T9).

Usam o mesmo motor dos tours autorais (:mod:`core.tours`): cada gerador
devolve um :class:`~core.tours.Tour` com passos cujos textos já trazem os
números calculados (altura, direção, horários). Os trechos fixos — sobre
cada estrela brilhante, cada planeta, a Lua — vêm de
``data/processed/tours/_textos.json`` (curado em
``scripts/curated/tours/_textos.md``); as histórias das constelações, do
:mod:`core.lore`.

Geradores:

- ``como-se-orientar`` — cardeais, poente, zênite, polo, o céu girando, a Lua;
- ``estrelas-brilhantes`` — as estrelas mais brilhantes no céu desta noite;
- ``lua-e-planetas`` — a Lua e os planetas que valem a pena esta noite;
- ``ceu-do-mes`` — constelações no meridiano no início da noite do dia 15,
  objetos para binóculo e telescópio pequeno, planetas e fenômenos do mês;
- ``objetos-do-mes`` — alvos de astrofoto com **mediana ≥ 4 h úteis por
  noite** no mês, em três seções (aglomerados, nebulosas, galáxias), cada
  uma na ordem em que os objetos ficam bons na noite típica (dia 15).
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .tours import Step, Tour, base_time

UTC = dt.timezone.utc
MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIRS_PT = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]
PHOTO_MIN_HOURS = 4.0                  # mediana das noites do mês (decisão 2026-10-04)
PHOTO_PER_SECTION = 12
SECTIONS = [
    ("aglomerados", "Aglomerados estelares", ("OC", "GC")),
    ("nebulosas", "Nebulosas", ("NEB", "PN", "DARK")),
    ("galaxias", "Galáxias", ("GAL",)),
]


@dataclass
class GenContext:
    engine: object
    stars: object
    dso: object
    now_utc: dt.datetime
    latitude: float = -22.9
    bortle: int = 5
    horizon: object = None
    # astrofotografia (setup ativo)
    photo_min_alt: float = 30.0
    mount_kind: str = "equatorial"
    zenith_limit: float = 80.0
    setup_name: str = ""
    setup_shape: object = None            # FovShape da câmera do setup ativo


@dataclass
class GenMeta:
    key: str
    title: str
    subtitle: str
    category: str
    level: int
    minutes: int
    fn: Callable[[GenContext], Tour] = field(repr=False, default=None)


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------

_TEXTS: dict | None = None


def texts() -> dict[str, str]:
    global _TEXTS
    if _TEXTS is None:
        from ..config import package_data_dir

        path = package_data_dir() / "tours" / "_textos.json"
        try:
            _TEXTS = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            _TEXTS = {}
    return _TEXTS


def dir_pt(az_deg: float) -> str:
    return DIRS_PT[int(((az_deg % 360) + 22.5) // 45) % 8]


def _hm(when: dt.datetime) -> str:
    from .localtime import to_local

    return f"{to_local(when):%H:%M}"


def _num(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def _vec_altaz(v: np.ndarray) -> tuple[float, float]:
    v = np.asarray(v, np.float64)
    v = v / np.linalg.norm(v)
    alt = math.degrees(math.asin(max(-1.0, min(1.0, float(v[2])))))
    az = math.degrees(math.atan2(float(v[1]), float(v[0]))) % 360.0
    return alt, az


def altaz_of(engine, when: dt.datetime, icrs=None, body: str | None = None):
    t = engine.ts.from_datetime(when)
    if icrs is not None:
        return _vec_altaz(np.asarray(engine.horizontal_matrix(t), np.float64) @ icrs)
    st = next((b for b in engine.bodies(t) if b.name == body), None)
    return _vec_altaz(st.vec) if st is not None else (-90.0, 0.0)


def _when_rule(when: dt.datetime) -> str:
    """Regra ``data:MM-DD hora:HH:MM`` que reproduz ``when`` (hora local)."""
    from .localtime import to_local

    lt = to_local(when)
    if lt.hour < 12:                        # madrugada: a regra usa a véspera
        lt0 = lt - dt.timedelta(days=1)
        return f"data:{lt0:%m-%d} hora:{lt:%H:%M}"
    return f"data:{lt:%m-%d} hora:{lt:%H:%M}"


def _const_name(cid: str) -> str:
    from ..catalogs.constnames import CONSTELLATIONS

    return CONSTELLATIONS.get(cid, (cid, cid))[1]


def _pole(lat: float) -> tuple[float, float, str]:
    """(azimute, altura, nome) do polo celeste visível."""
    return (180.0, abs(lat), "sul") if lat < 0 else (0.0, abs(lat), "norte")


def _moon_info(engine, when: dt.datetime) -> tuple[str, float]:
    from skyfield import almanac

    from .tonight import moon_phase_name

    t = engine.ts.from_datetime(when)
    phase, _deg = moon_phase_name(engine, t)
    illum = float(almanac.fraction_illuminated(engine.eph, "moon", t)) * 100.0
    return phase, illum


def _star_distance_ly(stars, idx: int) -> float | None:
    d = float(stars.dist[idx]) if len(stars.dist) > idx else 0.0
    return d * 3.2616 if 0 < d < 100000 else None


def _best_body_time(engine, body: str, base: dt.datetime, min_alt: float = 10.0):
    """(instante, altura) da melhor hora da noite para um corpo, ou (None, alt)."""
    from .visibility import Target, compute_visibility

    vis = compute_visibility(engine, Target(body=body), base, min_alt, refine=False)
    if vis.best_utc is None:
        return None, vis.best_alt
    return vis.best_utc, vis.best_alt


# ---------------------------------------------------------------------------
# Iniciantes
# ---------------------------------------------------------------------------

def como_se_orientar(ctx: GenContext) -> Tour:
    from .twilight import night_info

    eng = ctx.engine
    base = base_time(eng, "inicio_da_noite", ctx.now_utc)
    pole_az, pole_alt, pole_name = _pole(ctx.latitude)
    south = ctx.latitude < 0
    info = night_info(eng, base)
    steps = [Step(
        title="Os pontos cardeais", kind="intro", target=f"altaz:{pole_az:.0f},25", fov=120,
        layers={"cardinals": True, "grid_altaz": True, "const_lines": True,
                "ground": True},
        text=("O céu parece uma grande cúpula apoiada no horizonte. Para falar de qualquer "
              "estrela, primeiro é preciso saber para que lado se está olhando: as letras "
              "**N**, **S**, **L** e **O** no horizonte marcam o norte, o sul, o leste e o "
              "oeste.\n\nAs linhas curvas são a grade de altura: o horizonte é 0° e o ponto "
              "bem acima da cabeça é 90°. \"Uma estrela a 30° no sudeste\" quer dizer: vire "
              "para o sudeste e suba um terço do caminho até o topo."))]
    if info.sunset is not None:
        alt, az = altaz_of(eng, info.sunset, body="Sol")
        if south:
            season = ("Em junho ele se põe mais ao noroeste e em dezembro mais ao sudoeste; "
                      "só nos equinócios (março e setembro) é exatamente no oeste.")
        else:
            season = ("Em junho ele se põe mais ao noroeste e em dezembro mais ao sudoeste; "
                      "só nos equinócios é exatamente no oeste.")
        steps.append(Step(
            title="Onde o Sol se pôs", target=f"altaz:{az:.0f},8", fov=100,
            time=f"{_hm(info.sunset)}",
            text=(f"Hoje o Sol se pôs às **{_hm(info.sunset)}**, a {az:.0f}° de azimute — "
                  f"no **{dir_pt(az)}**. O ponto do poente muda ao longo do ano. {season}\n\n"
                  "Do lado oposto, o leste, é por onde as estrelas nascem.")))
    steps.append(Step(
        title="O zênite", target=f"altaz:{pole_az:.0f},88", fov=120,
        text=("O **zênite** é o ponto bem acima da sua cabeça. As estrelas perto dele são as "
              "melhores para observar: a luz atravessa menos ar, a imagem treme menos e a "
              "poluição luminosa atrapalha menos que perto do horizonte.")))
    if south:
        steps.append(Step(
            title="O polo sul celeste", target=f"altaz:{pole_az:.0f},{pole_alt:.0f}", fov=60,
            highlight=["asterism:cruzeiro", "asterism:apontadores"], skip_if_below=-90,
            text=(f"Todo o céu gira em volta de um ponto fixo: o **polo sul celeste**, a "
                  f"{pole_alt:.0f}° de altura — exatamente a sua latitude. Não há estrela "
                  "brilhante ali; para achá-lo, use o **Cruzeiro do Sul**: prolongue o braço "
                  "maior da cruz cerca de quatro vezes e meia.\n\nDescendo do polo até o "
                  "horizonte, você está olhando para o **sul**.")))
    else:
        steps.append(Step(
            title="O polo norte celeste", target=f"altaz:{pole_az:.0f},{pole_alt:.0f}", fov=60,
            skip_if_below=-90,
            text=(f"Todo o céu gira em volta do **polo norte celeste**, a {pole_alt:.0f}° de "
                  "altura — a sua latitude. Bem perto dele fica a Estrela Polar, na Ursa "
                  "Menor; descendo dela até o horizonte, você olha para o **norte**.")))
    steps.append(Step(
        title="Olhando para o leste", target="altaz:90,25", fov=90,
        text=("Repare nas estrelas acima do horizonte leste e guarde a posição de algumas "
              "delas. No próximo passo o relógio avança duas horas.")))
    steps.append(Step(
        title="Duas horas depois", target="altaz:90,25", fov=90, time="+2h",
        text=("As mesmas estrelas subiram cerca de 30°. O céu gira 15° por hora — reflexo da "
              "rotação da Terra: as estrelas nascem no leste, passam pelo meridiano (a linha "
              "norte–sul que cruza o zênite) e se põem no oeste. Perto do polo, elas giram em "
              "círculos e algumas nunca se põem.")))
    phase, illum = _moon_info(eng, base)
    t_moon, alt_moon = _best_body_time(eng, "Lua", base)
    if t_moon is not None:
        steps.append(Step(
            title="A Lua hoje", target="body:Lua", fov=3.0, time=_hm(t_moon),
            text=(f"Hoje a Lua está **{phase.lower()}**, com {illum:.0f}% do disco iluminado, "
                  f"e fica mais alta por volta das {_hm(t_moon)}, a {alt_moon:.0f}°.\n\n"
                  + texts().get("lua", ""))))
    else:
        steps.append(Step(
            title="E a Lua?", target=f"altaz:{pole_az:.0f},40", fov=100, kind="pause",
            text=(f"A Lua está {phase.lower()} ({illum:.0f}% iluminada) e não aparece no céu "
                  "escuro esta noite — boa notícia para ver as estrelas fracas e a Via Láctea.")))
    steps.append(Step(
        title="Para não esquecer", kind="fim", target=f"altaz:{pole_az:.0f},45", fov=110,
        text=("Pontos cardeais, altura e o giro do céu: com isso você já consegue seguir "
              "qualquer carta celeste. No Carina, **Agora** volta o relógio ao tempo real, "
              "**Buscar** (`Ctrl+F`) leva a qualquer objeto, e o botão direito no céu pergunta "
              "\"Qual constelação é esta?\".\n\nPróximo tour sugerido: **As estrelas mais "
              "brilhantes de hoje**.")))
    return Tour("como-se-orientar", "Como se orientar no céu", "iniciante",
                subtitle="Pontos cardeais, zênite, o polo celeste e o giro do céu",
                level=1, minutes=8, when=_when_rule(base), generated=True, steps=steps)


def estrelas_brilhantes(ctx: GenContext) -> Tour:
    eng, stars = ctx.engine, ctx.stars
    base = base_time(eng, "inicio_da_noite", ctx.now_utc)
    from .tours import Resolver

    res = Resolver(stars, ctx.dso)
    cands = []
    for key in texts():
        if not key.startswith("estrela:"):
            continue
        idx = res.star_index(key[8:])
        if idx is None:
            continue
        icrs = np.asarray(stars.xyz[idx], np.float64)
        for dh in (0.0, 1.5, 3.0):
            when = base + dt.timedelta(hours=dh)
            alt, az = altaz_of(eng, when, icrs=icrs)
            if alt >= 20:
                cands.append((float(stars.mag[idx]), key[8:], idx, dh, alt, az))
                break
    cands.sort()
    chosen = cands[:7]
    pole_az, _alt, _n = _pole(ctx.latitude)
    steps = [Step(
        title="As estrelas mais brilhantes de hoje", kind="intro",
        target=f"altaz:{pole_az:.0f},60", fov=120,
        layers={"star_names": True, "const_lines": True},
        text=("O brilho de uma estrela é medido em **magnitudes**: quanto menor o número, "
              "mais brilhante — Sirius tem −1,5; as estrelas mais fracas que se veem num céu "
              "escuro, cerca de 6. Este tour visita, da mais brilhante para a menos, as "
              f"{len(chosen)} estrelas de primeira grandeza que estão no seu céu esta noite.\n\n"
              "Repare nas **cores**: as azuladas são mais quentes que o Sol; as alaranjadas, "
              "mais frias."))]
    for mag, name, idx, dh, alt, az in chosen:
        ly = _star_distance_ly(stars, idx)
        dist = f", a cerca de {ly:,.0f} anos-luz".replace(",", ".") if ly else ""
        when_txt = "" if dh == 0 else f" (o relógio avançou {_num(dh, 1)} h para ela subir)"
        steps.append(Step(
            title=name, target=f"star:{name}", fov=35,
            time="" if dh == 0 else f"+{dh}h",
            text=(texts()[f"estrela:{name}"] + "\n\n"
                  f"Agora a **{alt:.0f}°** de altura, no **{dir_pt(az)}**{when_txt}. "
                  f"Magnitude {_num(mag)}{dist}.")))
    steps.append(Step(
        title="Brilho não é tamanho", kind="fim", target=f"altaz:{pole_az:.0f},60", fov=120,
        text=("Uma estrela parece brilhante por ser luminosa **ou** por estar perto: Sirius "
              "brilha mais que Rigel só porque está cem vezes mais perto. Na ficha de cada "
              "estrela (um clique nela) aparecem a distância, a cor e o tipo.\n\nPróximo tour "
              "sugerido: **Constelações que todo mundo reconhece**.")))
    return Tour("estrelas-brilhantes", "As estrelas mais brilhantes de hoje", "iniciante",
                subtitle="As estrelas de primeira grandeza que estão no seu céu esta noite",
                level=1, minutes=8, when=_when_rule(base), generated=True, steps=steps)


def lua_e_planetas(ctx: GenContext) -> Tour:
    eng = ctx.engine
    base = base_time(eng, "inicio_da_noite", ctx.now_utc)
    t_mid = eng.ts.from_datetime(base + dt.timedelta(hours=3))
    mags = {b.name: b.magnitude for b in eng.bodies(t_mid)}
    bodies = []
    for name in ("Lua", "Vênus", "Júpiter", "Saturno", "Marte", "Mercúrio", "Urano", "Netuno"):
        when, alt = _best_body_time(eng, name, base, 10.0)
        if when is not None and alt >= 10:
            bodies.append((name, when, alt))
    bodies.sort(key=lambda b: b[1])
    names = [b[0] for b in bodies if b[0] != "Lua"]
    if names:
        lista = ", ".join(names[:-1]) + (" e " if len(names) > 1 else "") + names[-1]
        intro = (f"Esta noite estão no céu: **{lista}**"
                 + (" — além da Lua." if any(b[0] == "Lua" for b in bodies) else ".")
                 + " O tour visita cada um na sua melhor hora, da primeira à última.")
    else:
        intro = ("Nenhum planeta fica bem posicionado no céu escuro esta noite"
                 + (" — só a Lua." if bodies else ", e a Lua também não aparece.")
                 + " Planetas se movem entre as estrelas: volte daqui a algumas semanas.")
    steps = [Step(title="A Lua e os planetas desta noite", kind="intro", target="altaz:270,25",
                  fov=110, layers={"planet_names": True, "ecliptic": True}, text=intro + (
                      "\n\nA linha amarela é a **eclíptica**, o caminho do Sol no céu: a Lua e "
                      "os planetas andam sempre perto dela."))]
    for name, when, alt in bodies:
        if name == "Lua":
            phase, illum = _moon_info(eng, when)
            extra = f"Hoje: **{phase.lower()}**, {illum:.0f}% iluminada."
            body_txt = texts().get("lua", "")
            fov = 3.0
        else:
            extra = f"Magnitude {_num(mags.get(name, 0.0))}."
            body_txt = texts().get(f"planeta:{name}", "")
            fov = 1.0 if name in ("Júpiter", "Saturno") else 2.0
        _a, az = altaz_of(eng, when, body=name)
        steps.append(Step(
            title=name, target=f"body:{name}", fov=fov, time=_hm(when),
            text=(body_txt + "\n\n"
                  f"Melhor hora: **{_hm(when)}**, a {alt:.0f}° de altura, no {dir_pt(az)}. "
                  + extra)))
    steps.append(Step(
        title="Mais sobre cada um", kind="fim", target="altaz:270,30", fov=110,
        text=("A janela **Planetas** (`Ctrl+Shift+E`) mostra cada planeta como no telescópio, "
              "a melhor época do ano e as luas de Júpiter e Saturno; **A Lua em detalhe** "
              "(`Ctrl+Shift+M`) mostra as crateras no terminador desta noite.")))
    return Tour("lua-e-planetas", "A Lua e os planetas desta noite", "iniciante",
                subtitle="O que há no Sistema Solar para ver hoje, na melhor hora de cada um",
                level=1, minutes=6, when=_when_rule(base), generated=True, steps=steps)


# ---------------------------------------------------------------------------
# Intermediário — o céu deste mês
# ---------------------------------------------------------------------------

def _month_ref(ctx: GenContext) -> tuple[int, int, dt.datetime]:
    """(ano, mês, instante de referência = dia 15 às 15h locais)."""
    from .localtime import from_local_naive, to_local

    lt = to_local(ctx.now_utc)
    ref = from_local_naive(dt.datetime(lt.year, lt.month, 15, 15, 0)).astimezone(UTC)
    return lt.year, lt.month, ref


def ceu_do_mes(ctx: GenContext) -> Tour:
    from ..catalogs import skygeometry
    from ..catalogs.dso import type_label
    from ..config import package_data_dir
    from .observing import INSTRUMENT_LABEL, _build_finder, instrument_for
    from .tonight import tonight_summary

    eng = ctx.engine
    year, month, ref = _month_ref(ctx)
    base = base_time(eng, "inicio_da_noite", ref)
    mname = MONTHS_PT[month - 1]
    pole_az, _a, _n = _pole(ctx.latitude)
    steps = [Step(
        title=f"O céu de {mname}", kind="intro", target="altaz:0,90" if ctx.latitude < 0
        else "altaz:180,90", fov=130,
        layers={"const_lines": True, "const_names": True, "asterisms": True},
        text=(f"Este é o céu do **início da noite de 15 de {mname}** no seu local, às "
              f"{_hm(base)}. Ao longo do mês ele é quase o mesmo — só começa um pouco mais "
              "cedo no fim do mês (cerca de duas horas a menos em trinta dias).\n\nO tour passa "
              "pelas constelações que estão no alto nas primeiras horas da noite, pelos objetos "
              "que valem um binóculo ou um telescópio pequeno, pelos planetas e pelos "
              "fenômenos do mês."))]

    # constelações que culminam nas primeiras horas
    infos = skygeometry.load_constellation_info(package_data_dir())
    seen, consts = set(), []
    grid = [base + dt.timedelta(minutes=10 * k) for k in range(0, 25)]   # 4 h
    zrow = np.array([np.asarray(eng.horizontal_matrix(eng.ts.from_datetime(g)),
                                np.float64)[2] for g in grid])          # (T, 3)
    for c in infos:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        ra, dec = math.radians(c["ra"]), math.radians(c["dec"])
        icrs = np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra),
                         math.sin(dec)])
        alts = np.degrees(np.arcsin(np.clip(zrow @ icrs, -1.0, 1.0)))
        k = int(np.argmax(alts))
        if 0 < k < len(grid) - 1 and alts[k] >= 35:
            consts.append((int(c.get("rank", 3)), grid[k], alts[k], c["id"]))
    consts.sort()
    top = [c for c in consts if c[0] <= 2][:6]
    if len(top) < 4:                         # completa com as discretas, se preciso
        top += [c for c in consts if c[0] > 2][:4 - len(top)]
    consts = sorted(top, key=lambda x: x[1])
    for _rank, when, alt, cid in consts:
        ra_c = next(c for c in infos if c["id"] == cid)
        icrs = np.array([math.cos(math.radians(ra_c["dec"])) * math.cos(math.radians(ra_c["ra"])),
                         math.cos(math.radians(ra_c["dec"])) * math.sin(math.radians(ra_c["ra"])),
                         math.sin(math.radians(ra_c["dec"]))])
        alt, az = altaz_of(eng, when, icrs=icrs)
        steps.append(Step(
            title=_const_name(cid), target=f"const:{cid}", fov=50, time=_hm(when),
            highlight=[f"const:{cid}"],
            text=(f"{{lore:short:{cid}}}\n\n"
                  f"Às **{_hm(when)}** ela passa pelo meridiano, a {alt:.0f}° de altura, no "
                  f"{dir_pt(az)}. **Como achar.** {{lore:find:{cid}}}")))

    # objetos para binóculo e telescópio pequeno, bem altos nas primeiras horas
    from ..catalogs.dso import type_label as _type_label
    from .observing import INSTRUMENT_ORDER, SB_VERY_DIFFUSE, _curated_rows
    from .score import surface_brightness

    hints = {"olho": "aparece a olho nu em céu escuro; o binóculo mostra mais",
             "binoculo": "um binóculo 10×50 basta; num telescópio pequeno surgem detalhes",
             "pequeno": "pede um telescópio pequeno (a partir de 70–80 mm)"}
    cand = []
    for r in _curated_rows(ctx.dso, 400):
        if _dwarf_spheroidal(r["common"]):
            continue
        if r["klass"] in ("GAL", "NEB"):
            sb = surface_brightness(r["mag"], r["maj"], r["min"])
            if sb is not None and sb > SB_VERY_DIFFUSE:
                continue
        inst = instrument_for(r["mag"], r["maj"], r["klass"], r["min"])
        if inst not in hints:
            continue
        ra, dec = float(r["ra"]), float(r["dec"])
        icrs = np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra),
                         math.sin(dec)])
        alts = np.degrees(np.arcsin(np.clip(zrow @ icrs, -1.0, 1.0)))
        k = int(np.argmax(alts))
        if alts[k] < 35.0:
            continue
        famous = bool(r["common"]) or r["name"].startswith("M ")
        mag = r["mag"] if r["mag"] is not None else 99.0
        cand.append(((0 if famous else 1, INSTRUMENT_ORDER.index(inst), mag),
                     r, inst, grid[k], float(alts[k])))
    cand.sort(key=lambda c: c[0])
    picks, per_class = [], {}
    for _key, r, inst, when, alt in cand:
        if per_class.get(r["klass"], 0) >= 2:
            continue                         # variedade: no máximo dois de cada tipo
        per_class[r["klass"]] = per_class.get(r["klass"], 0) + 1
        picks.append((r, inst, when, alt))
        if len(picks) >= 8:
            break
    if picks:
        steps.append(Step(
            title="Para o binóculo e o telescópio pequeno", kind="intro",
            target="altaz:0,90" if ctx.latitude < 0 else "altaz:180,90", fov=130,
            text=(f"Agora, {len(picks)} objetos de céu profundo bem altos nas primeiras horas "
                  f"da noite de {mname} — os mais conhecidos e fáceis primeiro, no máximo dois "
                  "de cada tipo. Cada passo vai à hora em que o objeto está mais alto antes "
                  "das 23h e diz como chegar a ele pelas estrelas.")))
    for r, inst, when, alt in picks:
        from ..catalogs import names as _names

        common = _names.common_label(r["common"]) if r["common"] else ""
        label = f"{r['name']} — {common}" if common else r["name"]
        cname = _const_name(r["con"]) if r["con"] else ""
        finder, _g = _build_finder(ctx.stars, float(r["ra"]), float(r["dec"]), cname)
        mag = f", magnitude {_num(float(r['mag']))}" if r["mag"] is not None else ""
        size = f", {_num(float(r['maj']), 0)}′" if r["maj"] else ""
        steps.append(Step(
            title=label, target=f"dso:{r['name']}", time=_hm(when), image=f"dss:{r['name']}",
            text=(f"**{_type_label(r['type'])}** em {cname}{mag}{size}. "
                  f"{INSTRUMENT_LABEL.get(inst, '')}: {hints[inst]}.\n\n"
                  f"Mais alto no começo da noite às **{_hm(when)}**, a {alt:.0f}°.\n\n"
                  f"**Como achar.** {finder}")))

    summ = tonight_summary(eng, ctx.dso, base, ctx.bortle, ctx.horizon, min_alt=20.0,
                           instrument="pequeno", n_best=1)

    # planetas
    shown = 0
    for it in summ.planets:
        if it.best_utc is None or shown >= 3:
            continue
        early_alts = [altaz_of(eng, g, body=it.name)[0] for g in grid[::6]]
        k = int(np.argmax(early_alts))
        if early_alts[k] < 20.0:
            continue                          # só de madrugada: fica para outro tour
        it.best_utc, it.best_alt = grid[::6][k], early_alts[k]
        shown += 1
        steps.append(Step(
            title=it.name, target=f"body:{it.name}", time=_hm(it.best_utc),
            fov=1.0 if it.name in ("Júpiter", "Saturno") else 2.0,
            text=(texts().get(f"planeta:{it.name}", "") + "\n\n"
                  f"Em {mname}: melhor às **{_hm(it.best_utc)}**, a {it.best_alt:.0f}° de "
                  "altura.")))

    # fenômenos do mês
    from .events import compute_events, month_range

    try:
        start, end = month_range(year, month)
        evs = compute_events(eng, start, end,
                             categories=["eclipse", "planeta", "meteoros", "encontro", "lua"],
                             min_importance=2)
    except Exception:              # noqa: BLE001 — o tour não depende disso
        evs = []
    if evs:
        lines = [f"- **{ev.local_start():%d/%m}** — {ev.title}" for ev in evs[:8]]
        steps.append(Step(
            title=f"Fenômenos de {mname}", kind="pause",
            target="altaz:0,90" if ctx.latitude < 0 else "altaz:180,90", fov=130,
            text=("Os destaques do mês no seu local, do Calendário do céu:\n\n"
                  + "\n".join(lines) + "\n\nNo **Calendário do céu** (`Ctrl+Shift+A`) cada "
                  "evento tem detalhes, lembrete e o botão para levar o céu até ele.")))
    steps.append(Step(
        title="Boas observações", kind="fim", target=f"altaz:{pole_az:.0f},50", fov=110,
        text=("Para levar esta lista para o campo, use **★ Guardar os objetos deste tour numa "
              "lista**, logo abaixo; depois, **Planejar ▸ Roteiros ▸ Roteiro da minha lista** "
              "monta a sequência da noite com horários e cartas de localização.")))
    return Tour("ceu-do-mes", f"O céu de {mname}", "intermediario",
                subtitle="Constelações, objetos para binóculo e telescópio pequeno, planetas "
                         "e fenômenos do mês",
                level=2, minutes=20, when=_when_rule(base), generated=True, steps=steps)


# ---------------------------------------------------------------------------
# Astrofotografia — objetos do mês
# ---------------------------------------------------------------------------

@dataclass
class MonthImaging:
    dates: list                       # datas locais das noites
    hours: np.ndarray                 # (N, noites) horas úteis
    night_times: list                 # instantes (UTC) da noite típica, passo fixo
    night_alts: np.ndarray            # (N, T) alturas na noite típica
    night_geo: np.ndarray             # (N, T) usável sem a Lua (geometria + escuro)
    night_dark: np.ndarray            # (T,) céu escuro na noite típica
    typical: int                      # índice da noite típica em ``dates``


def month_imaging(engine, icrs: np.ndarray, year: int, month: int, *,
                  min_alt: float = 30.0, dark_sun: float = -18.0,
                  moon_sep_min: float = 40.0, zenith_limit: float | None = None,
                  horizon=None, step_min: int = 10, typical_day: int = 15,
                  chunk: int = 256) -> MonthImaging:
    """Horas úteis por noite no mês para muitos alvos de uma vez (vetorizado).

    Útil = acima de ``min_alt``, Sol abaixo de ``dark_sun``, sem a Lua por
    perto (o mesmo modelo do calendário de imageabilidade: ela só atrapalha
    acima do horizonte, mais de 35% iluminada e mais perto que
    ``moon_sep_min`` + 40°·(fase − 0,35)), fora da zona do zênite (alt-az) e
    acima do perfil do horizonte. As noites vão de meio-dia a
    meio-dia locais, então cada noite tem exatamente 24 h de amostras.
    """
    from .localtime import from_local_naive, to_local

    ndays = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.date(year, month, 1)).days
    t0 = from_local_naive(dt.datetime(year, month, 1, 12, 0)).astimezone(UTC)
    per = int(24 * 60 // step_min)
    times = [t0 + dt.timedelta(minutes=step_min * k) for k in range(ndays * per)]
    t = engine.ts.from_datetimes(times)
    obs = engine.site.at(t)
    rows = []
    for alt_deg, az_deg in ((0.0, 0.0), (0.0, 90.0), (90.0, 0.0)):
        p = np.asarray(obs.from_altaz(alt_degrees=alt_deg, az_degrees=az_deg).position.au)
        rows.append((p / np.linalg.norm(p, axis=0)).astype(np.float32))
    sun_alt = np.asarray(obs.observe(engine.eph["sun"]).apparent().altaz()[0].degrees)
    moon = obs.observe(engine.eph["moon"]).apparent()
    malt = np.asarray(moon.altaz()[0].degrees)
    mvec = np.asarray(moon.position.au, np.float64)
    mvec = (mvec / np.linalg.norm(mvec, axis=0)).astype(np.float32)
    from skyfield import almanac

    dark = sun_alt <= dark_sun
    illum = np.asarray(almanac.fraction_illuminated(engine.eph, "moon", t))
    moon_up = (malt > 0.0) & (illum > 0.35)
    moon_reach = (moon_sep_min + 40.0 * (illum - 0.35)).astype(np.float32)
    icrs = np.asarray(icrs, np.float32)
    n = len(icrs)
    typical = min(max(typical_day, 1), ndays) - 1
    sl = slice(typical * per, (typical + 1) * per)
    hours = np.zeros((n, ndays), np.float32)
    night_alts = np.zeros((n, per), np.float32)
    night_geo = np.zeros((n, per), bool)
    for a in range(0, n, chunk):
        v = icrs[a:a + chunk]
        z = np.clip(v @ rows[2], -1.0, 1.0)
        alt = np.degrees(np.arcsin(z))
        geo = (alt >= min_alt) & dark[np.newaxis, :]
        if zenith_limit is not None:
            geo &= alt < zenith_limit
        if horizon is not None:
            az = np.degrees(np.arctan2(v @ rows[1], v @ rows[0])) % 360.0
            geo &= alt > np.asarray(horizon.altitude_at(az))
        sep = np.degrees(np.arccos(np.clip(v @ mvec, -1.0, 1.0)))
        ok = geo & (~moon_up[np.newaxis, :] | (sep >= moon_reach[np.newaxis, :]))
        hours[a:a + chunk] = ok.reshape(len(v), ndays, per).sum(axis=2) * (step_min / 60.0)
        night_alts[a:a + chunk] = alt[:, sl]
        night_geo[a:a + chunk] = geo[:, sl]
    dates = [to_local(t0 + dt.timedelta(days=d)).date() for d in range(ndays)]
    return MonthImaging(dates, hours, times[sl], night_alts, night_geo, dark[sl], typical)


def _dwarf_spheroidal(common: str | None) -> bool:
    """Anãs esferoidais/elípticas do Grupo Local: magnitude integrada boa no
    catálogo, mas espalhadas por graus — invisíveis ao binóculo e quase
    impossíveis em foto amadora. O tamanho do OpenNGC subestima a extensão."""
    c = (common or "").lower()
    return "dwarf spheroidal" in c or "dwarf elliptical" in c


def _photo_ok_size(c: dict, named: set[int]) -> bool:
    """Tamanho mínimo (3′) ou designação famosa (Messier, Caldwell, Sharpless),
    e galáxias/nebulosas não difusas demais para uma foto amadora."""
    from .observing import SB_VERY_DIFFUSE
    from .score import surface_brightness

    if (c.get("klass") or "") == "GAL" and _dwarf_spheroidal(c.get("common_raw")):
        return False
    if (c.get("klass") or "") in ("GAL", "NEB"):
        sb = surface_brightness(c.get("mag"), c.get("maj"), c.get("min"))
        if sb is not None and sb > SB_VERY_DIFFUSE:
            return False
    return (c.get("maj") or 0.0) >= 3.0 or c["id"] in named


def objetos_do_mes(ctx: GenContext) -> Tour:
    from ..catalogs.equipment import MOUNT_KINDS, fit_in_field, mount_flips, mount_is_altaz
    from .observing import _build_finder
    from .session import photo_candidates

    eng = ctx.engine
    year, month, ref = _month_ref(ctx)
    mname = MONTHS_PT[month - 1]
    altaz = mount_is_altaz(ctx.mount_kind)
    cands = photo_candidates(ctx.dso)
    named = {int(r[0]) for r in ctx.dso.cx.execute(
        "SELECT DISTINCT object_id FROM designations WHERE catalog IN ('M', 'C', 'SH2')")}
    cands = [c for c in cands if _photo_ok_size(c, named)]
    base = base_time(eng, "inicio_da_noite", ref)
    if not cands:
        return Tour("objetos-do-mes", f"Objetos de {mname} para fotografar", "astrofoto",
                    when=_when_rule(base), generated=True,
                    steps=[Step(title="Sem candidatos", kind="intro", target="altaz:180,60",
                                text="O catálogo de fotos não está disponível.")])
    mi = month_imaging(eng, np.array([c["icrs"] for c in cands]), year, month,
                       min_alt=ctx.photo_min_alt,
                       zenith_limit=ctx.zenith_limit if altaz else None,
                       horizon=ctx.horizon)
    med = np.median(mi.hours, axis=1)
    keep = np.nonzero(med >= PHOTO_MIN_HOURS)[0]
    mount_txt = MOUNT_KINDS.get(ctx.mount_kind, ctx.mount_kind)
    setup_txt = f" com o setup **{ctx.setup_name}**" if ctx.setup_name else ""
    night = mi.dates[mi.typical]
    steps = [Step(
        title=f"Objetos de {mname} para fotografar", kind="intro",
        target="altaz:0,90" if ctx.latitude < 0 else "altaz:180,90", fov=130,
        layers={"const_lines": True, "asterisms": True, "dso": True},
        text=(f"Os alvos que rendem **pelo menos {PHOTO_MIN_HOURS:.0f} horas úteis por noite** "
              f"em {mname}, contando a mediana das noites do mês: acima de "
              f"{ctx.photo_min_alt:.0f}°, no céu escuro (Sol abaixo de −18°), longe da Lua"
              + (", fora da zona do zênite" if altaz else "")
              + (" e acima do horizonte do seu quintal" if ctx.horizon is not None else "")
              + f".\n\nMontagem: {mount_txt}{setup_txt}. São três seções — aglomerados, "
              "nebulosas e galáxias —, cada uma na ordem em que os objetos ficam bons na "
              f"noite de {night:%d/%m}: os primeiros já estão altos ao escurecer.\n\n"
              "Cada passo mostra a altura do objeto ao longo da noite e as horas úteis em "
              "cada noite do mês; **+ Sessão** manda o alvo para a Sessão de astrofoto."))]
    total = 0
    for sec_key, sec_title, klasses in SECTIONS:
        idxs = [i for i in keep if (cands[i]["klass"] or "") in klasses]
        entries = []
        for i in idxs:
            geo = mi.night_geo[i]
            if not geo.any():
                continue
            k0 = int(np.argmax(geo))
            k1 = len(geo) - int(np.argmax(geo[::-1])) - 1
            entries.append((k0, -float(med[i]), i, k1))
        entries.sort()
        entries = entries[:PHOTO_PER_SECTION]
        if not entries:
            continue
        steps.append(Step(
            title=sec_title, kind="intro",
            target="altaz:0,90" if ctx.latitude < 0 else "altaz:180,90", fov=130,
            text=(f"**{sec_title}** — {len(entries)} alvo(s) em {mname}, na ordem em que "
                  f"ficam favoráveis na noite de {night:%d/%m}."
                  + ("" if len(idxs) <= PHOTO_PER_SECTION
                     else f" (Há {len(idxs)} ao todo; aqui ficam os {PHOTO_PER_SECTION} "
                          "primeiros.)"))))
        for k0, _m, i, k1 in entries:
            c = cands[i]
            t_in, t_out = mi.night_times[k0], mi.night_times[k1]
            k_mid = (k0 + k1) // 2
            when = mi.night_times[k_mid]
            cname = _const_name(c["con"]) if c.get("con") else ""
            finder, _g = _build_finder(ctx.stars, c["ra"], c["dec"], cname)
            size = f" · {_num(float(c['maj']), 0)}′" if c.get("maj") else ""
            mag = f" · mag {_num(float(c['mag']))}" if c.get("mag") is not None else ""
            fit_txt = ""
            if ctx.setup_shape is not None and c.get("maj"):
                f = fit_in_field(float(c["maj"]), c.get("min"), ctx.setup_shape)
                cols, rws = f["mosaic"]
                fit_txt = (f" Cabe no campo do setup (ocupa {f['fill'] * 100:.0f}% da área)."
                           if f["fits"] else f" Pede um mosaico de {cols}×{rws} no setup.")
            mer_txt = ""
            if mount_flips(ctx.mount_kind):
                kmax = int(np.argmax(mi.night_alts[i]))
                if k0 < kmax < k1:
                    mer_txt = (f" Passa pelo meridiano às {_hm(mi.night_times[kmax])}: "
                               "planeje o flip da montagem.")
            day = mi.dates[mi.typical]
            card = {
                "kind": "month_object", "ident": c["ident"], "name": c["label"],
                "median": float(med[i]), "min_hours": PHOTO_MIN_HOURS,
                "dates": [d.isoformat() for d in mi.dates],
                "hours": [round(float(h), 2) for h in mi.hours[i]],
                "times": [tt.isoformat() for tt in mi.night_times],
                "alts": [round(float(a), 1) for a in mi.night_alts[i]],
                "dark": [bool(x) for x in mi.night_dark],
                "min_alt": ctx.photo_min_alt,
                "zenith": ctx.zenith_limit if altaz else None,
                "meridian": mount_flips(ctx.mount_kind),
                "typical": day.isoformat(),
            }
            steps.append(Step(
                title=c["label"], target=f"dso:{c['ident']}", time=_hm(when),
                image=f"dss:{c['ident']}", card=card,
                text=(f"**{c['type_label']}** em {cname}{size}{mag}.\n\n"
                      f"Na noite de {day:%d/%m} fica útil das **{_hm(t_in)}** às "
                      f"**{_hm(t_out)}**; no mês rende cerca de **{_num(float(med[i]))} h por "
                      f"noite** (mediana).{mer_txt}{fit_txt}\n\n**Como achar.** {finder}")))
            total += 1
    if total == 0:
        steps.append(Step(
            title="Nenhum alvo neste mês", kind="pause", target="altaz:180,60", fov=120,
            text=(f"Com altura mínima de {ctx.photo_min_alt:.0f}° nenhum objeto chega a "
                  f"{PHOTO_MIN_HOURS:.0f} h por noite em {mname} no seu local. Na Sessão de "
                  "astrofoto dá para baixar a altura mínima e ver o calendário de cada alvo.")))
    steps.append(Step(
        title="Do tour para a sessão", kind="fim",
        target="altaz:0,90" if ctx.latitude < 0 else "altaz:180,90", fov=130,
        text=("Na **Sessão de astrofoto** (`Ctrl+Shift+S`) os alvos escolhidos viram uma agenda "
              "da noite, com a sub-exposição sugerida, o número de subs e quantas noites para "
              "juntar as horas que você quer. **✨ Sugestões de alvos**, lá dentro, faz a mesma "
              "conta para uma noite específica.")))
    return Tour("objetos-do-mes", f"Objetos de {mname} para fotografar", "astrofoto",
                subtitle=f"Alvos com pelo menos {PHOTO_MIN_HOURS:.0f} h úteis por noite, "
                         "em ordem de quando ficam bons",
                level=3, minutes=25, when=_when_rule(base), generated=True, steps=steps)


# ---------------------------------------------------------------------------
# registro
# ---------------------------------------------------------------------------

GENERATORS: dict[str, GenMeta] = {m.key: m for m in (
    GenMeta("como-se-orientar", "Como se orientar no céu",
            "Pontos cardeais, zênite, o polo celeste e o giro do céu",
            "iniciante", 1, 8, como_se_orientar),
    GenMeta("estrelas-brilhantes", "As estrelas mais brilhantes de hoje",
            "As estrelas de primeira grandeza que estão no seu céu esta noite",
            "iniciante", 1, 8, estrelas_brilhantes),
    GenMeta("lua-e-planetas", "A Lua e os planetas desta noite",
            "O que há no Sistema Solar para ver hoje, na melhor hora de cada um",
            "iniciante", 1, 6, lua_e_planetas),
    GenMeta("ceu-do-mes", "O céu deste mês",
            "Constelações, objetos para binóculo e telescópio pequeno, planetas e "
            "fenômenos do mês", "intermediario", 2, 20, ceu_do_mes),
    GenMeta("objetos-do-mes", "Objetos do mês para fotografar",
            "Alvos com pelo menos 4 h úteis por noite, em ordem de quando ficam bons",
            "astrofoto", 3, 25, objetos_do_mes),
)}


def generate(key: str, ctx: GenContext) -> Tour:
    return GENERATORS[key].fn(ctx)
