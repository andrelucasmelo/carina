"""Temas do céu (v0.16 T2, ADR-045).

``dark``
    O Carina de sempre: céu escuro, atmosfera, Via Láctea fotográfica.
``light``
    Papel: fundo branco e traços escuros (o antigo "modo carta").
``red``
    Visão noturna: o quadro inteiro passa a ter só o canal vermelho — a
    luz vermelha fraca preserva a adaptação do olho ao escuro, que leva
    20 a 30 minutos para se formar e se perde num instante com luz branca.

O tema vive em ``RenderOptions.theme`` e em ``SkyWidget.theme``; o gerador
de carta, o atlas e o PDF o recebem como opção própria.
"""

from __future__ import annotations

THEMES = {
    "dark": "Escuro (Carina)",
    "light": "Claro (papel)",
    "red": "Vermelho (visão noturna)",
}
DEFAULT = "dark"


def normalize(theme: str | None) -> str:
    return theme if theme in THEMES else DEFAULT
