"""Opções de renderização de um quadro (revisão 2026-10, T13).

Hoje o :class:`~carina.ui.skywidget.SkyWidget` lê camadas, modo carta,
Bortle, teto de magnitude, modos de rótulo e o filtro de céu profundo de
atributos soltos. :class:`RenderOptions` é a fotografia desse estado num
único objeto serializável — o que o gerador de carta (v0.16) vai passar
para renderizar fora da tela com opções próprias, sem mexer na vista do
usuário. Na v0.14 serve para capturar/aplicar o estado e para testes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class RenderOptions:
    layers: dict[str, bool] = field(default_factory=dict)
    chart_mode: bool = False
    bortle: int = 1
    mag_cap: float | None = None
    name_mode: str = "proper"          # 'proper' | 'bayer'
    dso_name_mode: str = "number"      # 'number' | 'name'
    const_label_mode: str = "none"     # none | pt | latin | abbr
    prefer_caldwell: bool = True
    dso_filter: str = ""               # JSON do DsoFilter
    theme: str = "dark"                # dark | light (papel) | red (v0.16)
    mag_fixed: float | None = None     # cartas: magnitude exata das estrelas
    label_mag_cap: float | None = None  # cartas: nomes de estrelas até esta mag

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "RenderOptions":
        try:
            d = json.loads(text or "{}")
        except (TypeError, ValueError):
            d = {}
        opts = cls()
        for key, value in d.items():
            if hasattr(opts, key):
                setattr(opts, key, value)
        return opts
