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
            return cls(kind, idx, name, np.asarray(stars.xyz[idx], dtype=np.float64))
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
            return cls(kind, int(key), name, icrs, data)
        return cls(kind, key, str(key), None, None)

    def image_path(self):
        """Caminho da imagem local do objeto (só céu profundo), ou None."""
        if self.data is None:
            return None
        from ..catalogs import images

        return images.image_path_for(self.data["name"])
