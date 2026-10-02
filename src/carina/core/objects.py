"""Referência unificada a um objeto do céu (revisão 2026-10, T13).

A seleção circula pela interface como uma tupla ``(tipo, chave)`` —
``("star", índice)``, ``("dso", id)`` ou ``("body", nome)`` — e cada
janela refazia por conta própria o mesmo trabalho: achar o nome de
exibição, o vetor ICRS e a ficha do banco. :class:`ObjectRef` concentra
isso num lugar só.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..catalogs import names


@dataclass
class ObjectRef:
    """Um objeto resolvido: tipo, chave, nome de exibição, vetor ICRS
    (``None`` para corpos do Sistema Solar, que mudam de posição) e a
    ficha do banco (só céu profundo)."""

    kind: str
    key: object
    name: str
    icrs: np.ndarray | None = None
    data: dict | None = None
    ident: str = ""          # identidade estável (banco do usuário)

    @property
    def selection(self) -> tuple[str, object]:
        return (self.kind, self.key)

    @property
    def is_fixed(self) -> bool:
        """Estrelas e céu profundo têm posição fixa (gráficos anuais)."""
        return self.icrs is not None

    @classmethod
    def resolve(cls, selection, stars, dso) -> "ObjectRef | None":
        """Monta a referência a partir da seleção; ``None`` se o objeto
        não existe mais (removido do banco, por exemplo)."""
        if selection is None:
            return None
        kind, key = selection
        if kind == "star":
            idx = int(key)
            name = (stars.proper.get(idx) or stars.label(idx, "bayer")
                    or f"HIP {int(stars.hip[idx])}")
            hip = int(stars.hip[idx]) if stars.hip[idx] else 0
            ident = f"HIP {hip}" if hip else f"STAR {idx}"
            return cls(kind, idx, name, np.asarray(stars.xyz[idx], dtype=np.float64),
                       None, ident)
        if kind == "dso":
            data = dso.get(int(key))
            if data is None:
                return None
            name = data["name"]
            common = names.common_label(data.get("common"))
            if common:
                name += f" — {common}"
            cd = math.cos(data["dec"])
            icrs = np.array([cd * math.cos(data["ra"]), cd * math.sin(data["ra"]),
                             math.sin(data["dec"])])
            return cls(kind, int(key), name, icrs, data, data["name"])
        return cls(kind, key, str(key), None, None, str(key))

    @classmethod
    def from_ident(cls, kind: str, ident: str, stars, dso) -> "ObjectRef | None":
        """Caminho inverso de :attr:`ident`: o que o banco do usuário guarda
        volta a ser uma referência viva (``None`` se sumiu do catálogo)."""
        if kind == "dso":
            row = dso.cx.execute("SELECT id FROM objects WHERE name = ?",
                                 (ident,)).fetchone()
            return cls.resolve(("dso", int(row[0])), stars, dso) if row else None
        if kind == "star":
            if ident.startswith("HIP "):
                index = _hip_index(stars).get(int(ident[4:]))
            elif ident.startswith("STAR "):
                index = int(ident[5:])
            else:
                index = None
            if index is None or not 0 <= index < len(stars.mag):
                return None
            return cls.resolve(("star", index), stars, dso)
        return cls.resolve(("body", ident), stars, dso)

    @property
    def ra_dec(self) -> tuple[float, float] | None:
        """(AR, Dec) J2000 em radianos, para objetos de posição fixa."""
        if self.icrs is None:
            return None
        x, y, z = (float(c) for c in self.icrs)
        return math.atan2(y, x) % (2 * math.pi), math.asin(max(-1.0, min(1.0, z)))

    def image_path(self):
        """Caminho da imagem local do objeto (só céu profundo), ou None."""
        if self.data is None:
            return None
        from ..catalogs import images

        return images.image_path_for(self.data["name"])


def _hip_index(stars) -> dict[int, int]:
    """Mapa HIP → índice no catálogo (montado uma vez por catálogo)."""
    cached = getattr(stars, "_hip_index_cache", None)
    if cached is None:
        hips = np.asarray(stars.hip)
        nz = np.nonzero(hips)[0]
        cached = {int(hips[i]): int(i) for i in nz}
        stars._hip_index_cache = cached
    return cached
