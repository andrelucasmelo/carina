"""Horizonte do quintal: o perfil real de prédios, muros e árvores.

O horizonte geométrico (altitude 0°) raramente é o que o observador vê.
:class:`HorizonProfile` guarda pontos (azimute, altitude) em graus e
interpola linearmente entre eles, de forma circular (359° encosta em 0°).
Um objeto está **bloqueado** quando a sua altitude é menor que a do perfil
naquele azimute. O perfil alimenta a visibilidade (``core.visibility``), a
pontuação (``core.score``), o planejamento e o desenho do solo.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import numpy as np

MAX_ALT = 89.0


@dataclass
class HorizonProfile:
    """Perfil azimute × altitude (graus). Vazio = horizonte plano."""

    points: list[tuple[float, float]] = field(default_factory=list)
    name: str = "Plano"

    def __post_init__(self) -> None:
        self.points = self._normalized(self.points)

    # -- construção ----------------------------------------------------
    @staticmethod
    def _normalized(points) -> list[tuple[float, float]]:
        """Azimutes em [0, 360), altitudes em [0, 89], ordem crescente e
        sem azimutes repetidos (o último valor vence)."""
        merged: dict[float, float] = {}
        for az, alt in points:
            az = round(float(az) % 360.0, 3)
            merged[az] = max(0.0, min(MAX_ALT, float(alt)))
        return sorted(merged.items())

    def set_points(self, points) -> None:
        self.points = self._normalized(points)

    @property
    def is_flat(self) -> bool:
        return not self.points or all(alt <= 0.0 for _az, alt in self.points)

    # -- consulta ------------------------------------------------------
    def altitude_at(self, az_deg):
        """Altitude do perfil (graus) no(s) azimute(s) dado(s).

        Aceita escalar ou array. A interpolação é circular: os pontos são
        replicados uma volta antes e uma depois, de modo que o trecho entre
        o último ponto (ex.: 350°) e o primeiro (ex.: 10°) passe por 0°.
        """
        scalar = np.isscalar(az_deg)
        az = np.mod(np.asarray(az_deg, dtype=np.float64), 360.0)
        if self.is_flat:
            out = np.zeros_like(az)
        elif len(self.points) == 1:
            out = np.full_like(az, self.points[0][1])
        else:
            a = np.array([p[0] for p in self.points])
            h = np.array([p[1] for p in self.points])
            xs = np.concatenate([a - 360.0, a, a + 360.0])
            ys = np.concatenate([h, h, h])
            out = np.interp(az, xs, ys)
        return float(out) if scalar else out

    def blocks(self, az_deg, alt_deg):
        """``True`` onde a altitude dada fica abaixo do perfil."""
        res = np.asarray(alt_deg) < self.altitude_at(az_deg)
        return bool(res) if np.ndim(res) == 0 else res

    def max_altitude(self) -> float:
        return max((alt for _az, alt in self.points), default=0.0)

    # -- CSV -----------------------------------------------------------
    def to_csv(self) -> str:
        """Texto CSV ``azimute;altitude`` (graus, ponto decimal)."""
        buf = io.StringIO()
        buf.write("azimute;altitude\n")
        for az, alt in self.points:
            buf.write(f"{az:.2f};{alt:.2f}\n")
        return buf.getvalue()

    @classmethod
    def from_csv(cls, text: str, name: str = "Importado") -> "HorizonProfile":
        """Lê ``az;alt`` ou ``az,alt`` (cabeçalho opcional; aceita vírgula
        decimal quando o separador é ponto e vírgula, como no Excel PT)."""
        sample = text[:1024]
        delim = ";" if ";" in sample else ("\t" if "\t" in sample else ",")
        pts = []
        for row in csv.reader(io.StringIO(text), delimiter=delim):
            if len(row) < 2:
                continue
            try:
                az = float(row[0].strip().replace(",", "."))
                alt = float(row[1].strip().replace(",", "."))
            except ValueError:
                continue                    # cabeçalho ou linha inválida
            pts.append((az, alt))
        return cls(pts, name)

    # -- serialização compacta (banco do usuário) ---------------------
    def to_list(self) -> list[list[float]]:
        return [[az, alt] for az, alt in self.points]

    @classmethod
    def from_list(cls, data, name: str = "Meu horizonte") -> "HorizonProfile":
        return cls([(float(a), float(b)) for a, b in (data or [])], name)


# -- perfis prontos ----------------------------------------------------------
def preset_flat() -> HorizonProfile:
    return HorizonProfile([], "Plano")


def preset_wall(height: float = 10.0) -> HorizonProfile:
    """Muro uniforme em volta do observador."""
    return HorizonProfile([(az, height) for az in range(0, 360, 30)],
                          f"Muro de {height:.0f}°")


def preset_valley() -> HorizonProfile:
    """Vale: montanhas a leste e oeste, aberto ao norte e ao sul."""
    pts = [(0, 5), (45, 12), (90, 22), (135, 12), (180, 5),
           (225, 12), (270, 22), (315, 12)]
    return HorizonProfile(pts, "Vale")


def preset_city_south() -> HorizonProfile:
    """Prédio alto ao sul (caso típico de apartamento)."""
    pts = [(0, 3), (120, 3), (150, 35), (210, 35), (240, 3)]
    return HorizonProfile(pts, "Prédio ao sul")


PRESETS = {
    "Plano": preset_flat,
    "Muro de 10°": lambda: preset_wall(10.0),
    "Vale": preset_valley,
    "Prédio ao sul": preset_city_south,
}
