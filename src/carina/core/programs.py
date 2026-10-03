"""Programas de observação com progresso (base da v0.17; ampliada na v0.20).

Um programa é uma lista fechada de alvos — a Lunar 100, mais tarde o
Messier, o Caldwell, os 110 do Herschel — e o progresso sai do **diário**:
um alvo conta como feito quando há ao menos um registro com a mesma
identidade (``kind`` + ``ident``) no ``carina.sqlite``.
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


@dataclass
class Program:
    key: str
    title: str
    source: str
    items: list[ProgramItem] = field(default_factory=list)

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


PROGRAMS = {"lunar100": lunar100}


def get(key: str) -> Program:
    return PROGRAMS[key]()
