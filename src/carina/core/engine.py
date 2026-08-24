"""Motor astronômico: envelope sobre o Skyfield.

Estratégia de desempenho: em vez de chamar observe() para cada uma das ~120 mil
estrelas, calculamos uma única matriz de rotação ICRS -> frame horizontal
(norte/leste/zênite) por instante de tempo e a aplicamos a todos os vetores
unitários de uma vez (um matmul NumPy). Isso embute precessão, nutação, rotação
da Terra e movimento polar; ignora aberração anual (~20″) e paralaxe estelar,
invisíveis na escala de um planetário. Corpos do Sistema Solar usam o caminho
completo observe().apparent() por serem poucos.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from skyfield.api import Loader, wgs84

from ..config import ObserverLocation

# Efeméride JPL: DE440s cobre 1849–2150, ~32 MB.
EPHEMERIS = "de440s.bsp"

_BODIES = [
    # (chave, nome no BSP, cor RGB)
    ("Sol", "sun", (1.00, 0.95, 0.75)),
    ("Lua", "moon", (0.93, 0.93, 0.90)),
    ("Mercúrio", "mercury", (0.80, 0.75, 0.70)),
    ("Vênus", "venus", (0.98, 0.95, 0.85)),
    ("Marte", "mars barycenter", (1.00, 0.60, 0.40)),
    ("Júpiter", "jupiter barycenter", (0.95, 0.88, 0.75)),
    ("Saturno", "saturn barycenter", (0.95, 0.90, 0.70)),
    ("Urano", "uranus barycenter", (0.70, 0.90, 0.90)),
    ("Netuno", "neptune barycenter", (0.55, 0.70, 0.98)),
]

_RADIUS_KM = {"Sol": 695700.0, "Lua": 1737.4}


@dataclass
class BodyState:
    name: str
    az: float                 # radianos
    alt: float                # radianos
    vec: np.ndarray           # vetor unitário no frame horizontal
    magnitude: float
    angular_radius: float     # radianos (0 para pontos)
    color: tuple[float, float, float]
    distance_au: float


class TimeController:
    """Relógio da simulação: tempo real, tempo fixo ou acelerado."""

    def __init__(self, ts) -> None:
        self.ts = ts
        self._fixed: dt.datetime | None = None
        self._offset = dt.timedelta(0)   # deslocamento em relação ao relógio real
        self.speed = 1.0                 # reservado para acelerar o tempo

    def set_fixed(self, when: dt.datetime | None) -> None:
        """Congela a simulação num instante (UTC). None volta ao tempo real."""
        if when is not None and when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        self._fixed = when

    def current_datetime(self) -> dt.datetime:
        if self._fixed is not None:
            return self._fixed
        return dt.datetime.now(dt.timezone.utc) + self._offset

    def current(self):
        """Instante atual como skyfield.Time."""
        return self.ts.from_datetime(self.current_datetime())


class SkyEngine:
    def __init__(self, ephem_dir: Path) -> None:
        self._loader = Loader(str(ephem_dir), verbose=False)
        self.ts = self._loader.timescale(builtin=True)
        self.eph = self._loader(EPHEMERIS)
        self.earth = self.eph["earth"]
        self.time = TimeController(self.ts)
        self._site = None
        self._matrix_cache: tuple[float, np.ndarray] | None = None
        self._bodies_cache: tuple[float, list[BodyState]] | None = None

    # -- observador ------------------------------------------------------
    def set_location(self, loc: ObserverLocation) -> None:
        self.topos = wgs84.latlon(
            latitude_degrees=loc.latitude,
            longitude_degrees=loc.longitude,
            elevation_m=loc.elevation,
        )
        self._site = self.earth + self.topos
        self._matrix_cache = None
        self._bodies_cache = None

    # -- rotação ICRS -> horizontal --------------------------------------
    def horizontal_matrix(self, t) -> np.ndarray:
        """Matriz 3x3 M tal que v_horizontal = M @ v_icrs.

        Linhas de M: direções norte, leste e zênite expressas em ICRS.
        Cacheada por meio segundo para não recalcular a cada quadro.
        """
        key = round(t.tt * 172800.0)  # meio segundo em dias
        if self._matrix_cache is not None and self._matrix_cache[0] == key:
            return self._matrix_cache[1]
        obs = self._site.at(t)
        rows = []
        for alt_deg, az_deg in ((0.0, 0.0), (0.0, 90.0), (90.0, 0.0)):
            p = obs.from_altaz(alt_degrees=alt_deg, az_degrees=az_deg).position.au
            rows.append(p / np.linalg.norm(p))
        m = np.stack(rows)
        self._matrix_cache = (key, m)
        return m

    # -- Sistema Solar ---------------------------------------------------
    def bodies(self, t) -> list[BodyState]:
        key = round(t.tt * 172800.0)
        if self._bodies_cache is not None and self._bodies_cache[0] == key:
            return self._bodies_cache[1]
        from skyfield.magnitudelib import planetary_magnitude

        obs = self._site.at(t)
        states: list[BodyState] = []
        for name, key_bsp, color in _BODIES:
            app = obs.observe(self.eph[key_bsp]).apparent()
            alt, az, distance = app.altaz()
            alt_r, az_r = alt.radians, az.radians
            if name == "Sol":
                mag = -26.7
            elif name == "Lua":
                mag = -12.0
            else:
                try:
                    mag = float(planetary_magnitude(app))
                except Exception:
                    mag = 1.0
            radius_km = _RADIUS_KM.get(name)
            ang = 0.0
            if radius_km:
                ang = float(np.arcsin(radius_km / (distance.km)))
            ca = np.cos(alt_r)
            vec = np.array([ca * np.cos(az_r), ca * np.sin(az_r), np.sin(alt_r)])
            states.append(
                BodyState(
                    name=name, az=az_r, alt=alt_r, vec=vec, magnitude=mag,
                    angular_radius=ang, color=color, distance_au=float(distance.au),
                )
            )
        self._bodies_cache = (key, states)
        return states

    def sun_altitude(self, t) -> float:
        """Altitude do Sol em radianos (para o modelo de atmosfera)."""
        for b in self.bodies(t):
            if b.name == "Sol":
                return b.alt
        return -1.0
