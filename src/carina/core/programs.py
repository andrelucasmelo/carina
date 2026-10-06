"""Programas de observação com progresso (base da v0.17; completos na v0.22).

Um programa é uma lista fechada de alvos e o progresso sai do **diário**:
um alvo conta como feito quando há ao menos um registro com a mesma
identidade (``kind`` + ``ident``) no ``carina.sqlite``.

Programas: Messier (110), Caldwell (109), Herschel 400, Céu ao binóculo
(listas em ``data/processed/programs/``, de ``scripts/build_programs.py``),
Lunar 100 e **Planetas no ano** — os sete planetas observados no ano
corrente (esse programa recomeça todo ano: ``period = "year"``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProgramItem:
    number: int
    kind: str          # 'lunar' | 'dso' | 'star' | 'body'
    ident: str         # identidade estável usada no diário
    name: str
    group: str = ""    # tipo/categoria para filtros
    description: str = ""
    lat: float | None = None
    lon: float | None = None
    common: str = ""   # nome popular cru (traduzido ao exibir)

    @property
    def label(self) -> str:
        if not self.common:
            return self.name
        from ..catalogs import names

        return f"{self.name} — {names.common_label(self.common)}"


@dataclass
class Program:
    key: str
    title: str
    source: str
    items: list[ProgramItem] = field(default_factory=list)
    period: str = "always"     # "always" | "year" (só observações do ano corrente)
    description: str = ""

    def done(self, observed: set[tuple[str, str]]) -> list[ProgramItem]:
        return [it for it in self.items if (it.kind, it.ident) in observed]

    def progress(self, observed: set[tuple[str, str]]) -> tuple[int, int]:
        return len(self.done(observed)), len(self.items)

    def next_item(self, observed: set[tuple[str, str]]) -> ProgramItem | None:
        for it in self.items:
            if (it.kind, it.ident) not in observed:
                return it
        return None


LUNAR_KIND = "lunar"


def lunar100() -> Program:
    """A Lunar 100 de Charles Wood, com as descrições em português."""
    from . import moon

    prog = Program("lunar100", "Lunar 100",
                   "Charles A. Wood, Sky & Telescope (2004)")
    for f in moon.lunar100_features():
        lat = None if f.lat != f.lat else f.lat       # NaN → None
        lon = None if f.lon != f.lon else f.lon
        prog.items.append(ProgramItem(f.l100, LUNAR_KIND, f"L100 {f.l100}", f.name,
                                      moon.L100_TYPE_PT.get(f.type, f.type),
                                      f.desc, lat, lon))
    return prog


def lunar_ident(name: str) -> str:
    """Identidade no diário de uma formação lunar fora da Lunar 100."""
    return f"Lua: {name}"


def _from_json(key: str) -> Program:
    import json

    from ..config import package_data_dir

    d = json.loads((package_data_dir() / "programs" / f"{key}.json").read_text(
        encoding="utf-8"))
    prog = Program(key, d["title"], d.get("source", ""))
    for it in d["items"]:
        prog.items.append(ProgramItem(int(it["number"]), it.get("kind", "dso"), it["ident"],
                                      it["name"], it.get("group", ""), common=it.get("common", "")))
    return prog


def messier() -> Program:
    p = _from_json("messier")
    p.description = ("Os 110 objetos que Charles Messier listou no século XVIII para não "
                     "confundi-los com cometas — o programa clássico da astronomia amadora.")
    return p


def caldwell() -> Program:
    p = _from_json("caldwell")
    p.description = ("Os 109 objetos que Patrick Moore reuniu em 1995 como complemento ao "
                     "Messier, incluindo muitos do céu austral.")
    return p


def herschel400() -> Program:
    p = _from_json("herschel400")
    p.description = ("Os 400 objetos do catálogo de William Herschel escolhidos pela "
                     "Astronomical League — o passo seguinte ao Messier, para telescópios "
                     "a partir de 15 cm.")
    return p


def binoculo() -> Program:
    p = _from_json("binoculo")
    p.description = ("Os alvos curados do Carina para binóculo 7×50 ou 10×50: aglomerados, "
                     "nebulosas brilhantes, galáxias próximas e as Nuvens de Magalhães.")
    return p


PLANETS = ["Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno"]


def planetas_ano() -> Program:
    p = Program("planetas-ano", "Planetas no ano", "Carina", period="year",
                description=("Os sete planetas observados ao longo do ano corrente. Mercúrio "
                             "é o mais difícil; Urano e Netuno pedem binóculo e carta. "
                             "Recomeça em 1º de janeiro."))
    for i, name in enumerate(PLANETS, 1):
        p.items.append(ProgramItem(i, "body", name, name, "Planeta"))
    return p


PROGRAMS = {"messier": messier, "caldwell": caldwell, "herschel400": herschel400,
            "lunar100": lunar100, "binoculo": binoculo, "planetas-ano": planetas_ano}


def get(key: str) -> Program:
    return PROGRAMS[key]()


def observed_for(program: Program, userdata, year: int | None = None) -> set[tuple[str, str]]:
    """Identidades observadas que valem para o programa (no ano, se for anual)."""
    if userdata is None:
        return set()
    if program.period != "year":
        return userdata.observed_idents()
    import datetime as dt

    from .localtime import to_local

    year = year or to_local(dt.datetime.now(dt.timezone.utc)).year
    return {(o["kind"], o["ident"]) for o in userdata.observations()
            if to_local(o["when_utc"]).year == year}


def completion_date(program: Program, userdata, year: int | None = None):
    """Data (local) da observação que completou o programa, ou None."""
    obs = observed_for(program, userdata, year)
    if any((it.kind, it.ident) not in obs for it in program.items):
        return None
    from .localtime import to_local

    wanted = {(it.kind, it.ident) for it in program.items}
    firsts: dict = {}
    for o in userdata.observations():
        key = (o["kind"], o["ident"])
        if key in wanted:
            when = to_local(o["when_utc"])
            if program.period == "year" and year and when.year != year:
                continue
            if key not in firsts or when < firsts[key]:
                firsts[key] = when
    return max(firsts.values()).date() if firsts else None
