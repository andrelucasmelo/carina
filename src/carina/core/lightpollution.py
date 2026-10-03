"""Brilho artificial do céu por localização (v0.19 T6, ADR-050).

Consulta o mapa embarcado ``lightpollution.npz`` (0,1°, gerado por
``scripts/build_lightpollution.py`` a partir do NASA Black Marble 2016 com
um modelo de espalhamento de Walker) e converte a magnitude do céu no zênite
(mag/arcsec², a mesma escala dos medidores SQM) em classe de Bortle.

É uma **estimativa** para sugerir o Bortle ao escolher a cidade: erro típico
de ±0,4 mag (cerca de uma classe). O usuário continua decidindo — o céu do
quintal depende de postes, árvores e da direção da cidade mais próxima.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

# SQM → Bortle (limites usuais na literatura de observação)
BORTLE_SQM = [(21.75, 1), (21.6, 2), (21.3, 3), (20.8, 4), (20.3, 5),
              (19.5, 6), (18.95, 7), (18.4, 8)]


@lru_cache(maxsize=1)
def _data():
    from ..config import package_data_dir

    path = package_data_dir() / "lightpollution.npz"
    if not path.exists():
        return None
    d = np.load(path)
    return d["sky"], float(d["sqm_natural"]), float(d["scale"])


def available() -> bool:
    return _data() is not None


def sqm_at(lat: float, lon: float) -> float | None:
    """Magnitude do céu no zênite (mag/arcsec²) estimada no local.

    Interpolação bilinear na grade de 0,1° (dá a volta em longitude)."""
    d = _data()
    if d is None:
        return None
    sky, natural, scale = d
    h, w = sky.shape
    x = (lon + 180.0) / 360.0 * w - 0.5
    y = (90.0 - lat) / 180.0 * h - 0.5
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    fx, fy = x - x0, y - y0
    y0 = min(max(y0, 0), h - 2)
    xs = (x0 % w, (x0 + 1) % w)
    v = ((sky[y0, xs[0]] * (1 - fx) + sky[y0, xs[1]] * fx) * (1 - fy)
         + (sky[y0 + 1, xs[0]] * (1 - fx) + sky[y0 + 1, xs[1]] * fx) * fy)
    return natural - float(v) / scale


def bortle_from_sqm(sqm: float) -> int:
    for limit, bortle in BORTLE_SQM:
        if sqm >= limit:
            return bortle
    return 9


@dataclass
class SkySuggestion:
    bortle: int
    sqm: float | None
    source: str          # 'mapa' | 'populacao'

    def text(self) -> str:
        from .formats import num

        if self.sqm is None:
            return f"Bortle {self.bortle} (estimado pela população)"
        return (f"céu estimado em {num(self.sqm)} mag/arcsec² — Bortle {self.bortle} "
                "(mapa de luzes noturnas da NASA)")


def suggest(lat: float, lon: float, population: int | None = None) -> SkySuggestion:
    """Bortle sugerido: pelo mapa quando houver; senão, pela população."""
    sqm = sqm_at(lat, lon)
    if sqm is not None:
        return SkySuggestion(bortle_from_sqm(sqm), sqm, "mapa")
    pop = population or 0
    b = 8 if pop >= 1_000_000 else 7 if pop >= 200_000 else 6 if pop >= 50_000 \
        else 5 if pop >= 10_000 else 4
    return SkySuggestion(b, None, "populacao")
