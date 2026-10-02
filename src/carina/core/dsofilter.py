"""Filtro de exibição do céu profundo (revisão 2026-10, §9).

Um único objeto decide o que aparece no mapa: catálogos, tipos, faixa de
magnitude, faixa de tamanho angular, "só com nome comum", "só Messier/
Caldwell" e a regra para as **regiões gigantes** (Sharpless, Barnard,
LDN) que, desenhadas como círculos de vários graus, sufocavam Órion e
Sagitário. Tudo vira máscaras NumPy sobre os arrays de render do
:class:`~carina.catalogs.dso.DsoCatalog` — nada de SQL por quadro.

O mesmo filtro alimenta símbolos, imagens e rótulos; o planejamento e a
busca NÃO passam por ele (filtro de exibição, não de existência).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from ..catalogs.dso import ALL_CATALOGS, CATALOG_ORDER, KLASS_CODES

CLASS_LABELS = {
    "GAL": "Galáxias", "OC": "Aglomerados abertos", "GC": "Aglomerados globulares",
    "NEB": "Nebulosas difusas", "PN": "Nebulosas planetárias",
    "DARK": "Nebulosas escuras", "OTHER": "Outros",
}

# Como tratar objetos maiores que ``big_threshold_arcmin``
BIG_MODES = {
    "normal": "Desenhar como os demais",
    "outline": "Contorno fino tracejado",
    "label": "Só o rótulo, sem contorno",
    "hide": "Ocultar quando o campo for maior que…",
}


@dataclass
class DsoFilter:
    """Critérios de exibição. Valores "sem limite" são os padrões."""

    catalogs: set[str] = field(default_factory=lambda: set(CATALOG_ORDER))
    classes: set[str] = field(default_factory=lambda: set(KLASS_CODES))
    mag_min: float = -30.0
    mag_max: float = 30.0
    include_unknown_mag: bool = True
    size_min: float = 0.0          # minutos de arco
    size_max: float = 100_000.0
    include_unknown_size: bool = True
    only_named: bool = False
    only_mc: bool = False
    big_mode: str = "outline"
    big_threshold_arcmin: float = 120.0
    big_hide_fov_deg: float = 40.0

    # ------------------------------------------------------------------
    def mask(self, dso, fov_deg: float | None = None) -> np.ndarray:
        """Máscara booleana dos objetos que passam (alinhada aos arrays).

        ``fov_deg`` só importa para o modo ``hide`` das regiões grandes;
        sem ele (contagem na tela de filtros) essas regiões contam como
        visíveis.
        """
        n = len(dso.mag)
        if n == 0:
            return np.zeros(0, dtype=bool)
        keep = np.ones(n, dtype=bool)

        if set(self.catalogs) != set(ALL_CATALOGS):
            cols = [ALL_CATALOGS.index(c) for c in self.catalogs if c in ALL_CATALOGS]
            in_cat = dso.cat_matrix[:, cols].any(axis=1) if cols else np.zeros(n, bool)
            # objetos sem designação alguma (criados pelo usuário) ficam
            keep &= in_cat | ~dso.cat_matrix.any(axis=1)

        if set(self.classes) != set(KLASS_CODES):
            codes = np.array([KLASS_CODES[c] for c in self.classes if c in KLASS_CODES],
                             dtype=np.int8)
            keep &= np.isin(dso.klass, codes)

        has_mag = dso.mag < 90.0
        in_mag = (dso.mag >= self.mag_min) & (dso.mag <= self.mag_max)
        keep &= np.where(has_mag, in_mag, self.include_unknown_mag)

        has_size = dso.maj > 0.0
        in_size = (dso.maj >= self.size_min) & (dso.maj <= self.size_max)
        keep &= np.where(has_size, in_size, self.include_unknown_size)

        if self.only_named:
            keep &= dso.has_common
        if self.only_mc:
            keep &= dso.is_mc
        if (self.big_mode == "hide" and fov_deg is not None
                and fov_deg > self.big_hide_fov_deg):
            keep &= ~self.big_mask(dso)
        return keep

    def big_mask(self, dso) -> np.ndarray:
        """Objetos que contam como 'região grande'."""
        return dso.maj >= float(self.big_threshold_arcmin)

    # ------------------------------------------------------------------
    def to_json(self) -> str:
        d = asdict(self)
        d["catalogs"] = sorted(self.catalogs)
        d["classes"] = sorted(self.classes)
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str | None) -> "DsoFilter":
        """Reconstrói; texto inválido ou vazio devolve o padrão."""
        if not text:
            return cls()
        try:
            d = json.loads(text)
        except (TypeError, ValueError):
            return cls()
        f = cls()
        for key, value in d.items():
            if not hasattr(f, key):
                continue
            if key in ("catalogs", "classes"):
                value = set(value)
            setattr(f, key, value)
        if f.big_mode not in BIG_MODES:
            f.big_mode = "outline"
        return f

    def copy(self) -> "DsoFilter":
        return DsoFilter.from_json(self.to_json())


def _preset(**kw) -> DsoFilter:
    f = DsoFilter()
    for k, v in kw.items():
        setattr(f, k, v)
    return f


PRESETS: dict[str, DsoFilter] = {
    "Padrão": _preset(),
    "Binóculo": _preset(
        catalogs={"M", "C", "NGC", "IC", "Mel"}, mag_max=9.0, size_min=3.0,
        include_unknown_mag=False, big_mode="outline",
    ),
    "Astrofoto de grande campo": _preset(
        catalogs=set(ALL_CATALOGS), classes={"NEB", "DARK", "GAL", "OC"},
        size_min=15.0, big_mode="normal",
    ),
    "Só Messier e Caldwell": _preset(only_mc=True, big_mode="normal"),
    "Tudo": _preset(catalogs=set(ALL_CATALOGS), big_mode="normal"),
    "Limpo (só nomeados até mag 8)": _preset(
        only_named=True, mag_max=8.0, include_unknown_mag=False,
        big_mode="label",
    ),
}


def preset_names() -> list[str]:
    return list(PRESETS)


def arcmin_label(value: float) -> str:
    """'45′' ou '2,0°' conforme o tamanho."""
    if value >= 60.0:
        return f"{value / 60.0:.1f}°".replace(".", ",")
    return f"{value:.0f}′"


__all__ = ["DsoFilter", "PRESETS", "CLASS_LABELS", "BIG_MODES",
           "preset_names", "arcmin_label", "math"]
