"""Geometrias do céu: constelações, Via Láctea e grades de coordenadas.

Todas as polilinhas são mantidas como vetores unitários 3D. As que estão em
coordenadas equatoriais (ICRS) são rotacionadas pela matriz horária a cada
quadro; a grade horizontal já vive no frame do observador e não precisa de
rotação.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class PolylineSet:
    """Conjunto de polilinhas: vértices concatenados + pares de índices GL_LINES."""

    verts: np.ndarray      # (K,3) float32, vetores unitários
    counts: np.ndarray     # (P,) comprimento de cada polilinha
    segments: np.ndarray   # (S,2) int32: índices dos extremos de cada segmento

    @classmethod
    def from_arrays(cls, verts: np.ndarray, counts: np.ndarray) -> "PolylineSet":
        """Monta o conjunto a partir de vértices concatenados + tamanho de
        cada polilinha, gerando os pares de índices GL_LINES de uma vez."""
        segs = []
        start = 0
        for c in counts:
            c = int(c)
            idx = np.arange(start, start + c - 1, dtype=np.int32)
            segs.append(np.stack([idx, idx + 1], axis=1))
            start += c
        segments = (
            np.concatenate(segs) if segs else np.zeros((0, 2), dtype=np.int32)
        )
        return cls(verts=verts.astype(np.float32), counts=counts, segments=segments)


@dataclass
class PolygonSet:
    """Polígonos (anéis fechados) para preenchimento via stencil."""

    verts: np.ndarray
    counts: np.ndarray
    layer: np.ndarray      # camada de cada polígono (Via Láctea: isofotas)
    n_layers: int

    def rings(self):
        """Itera (camada, slice) de cada anel — o preenchimento por stencil
        processa um anel por vez."""
        start = 0
        for c, ly in zip(self.counts, self.layer):
            c = int(c)
            yield ly, slice(start, start + c)
            start += c


def load_constellation_lines(data_dir: Path) -> PolylineSet:
    """Traçados das figuras de constelação (d3-celestial, pré-processados)."""
    npz = np.load(data_dir / "const_lines.npz")
    return PolylineSet.from_arrays(npz["verts"], npz["counts"])


def load_constellation_bounds(data_dir: Path) -> PolylineSet:
    """Limites oficiais IAU das 88 constelações."""
    npz = np.load(data_dir / "const_bounds.npz")
    return PolylineSet.from_arrays(npz["verts"], npz["counts"])


def load_constellation_info(data_dir: Path) -> list[dict]:
    """Metadados das constelações: sigla, nomes (latim/PT) e centro."""
    return json.loads((data_dir / "constellations.json").read_text("utf-8"))


def load_milkyway(data_dir: Path) -> PolygonSet:
    """Isofotas vetoriais da Via Láctea (fallback do modo sem textura)."""
    npz = np.load(data_dir / "milkyway.npz")
    return PolygonSet(
        verts=npz["verts"].astype(np.float32),
        counts=npz["counts"],
        layer=npz["layer"],
        n_layers=int(npz["n_layers"]),
    )


@dataclass
class PointCloud:
    """Nuvem de splats da Via Láctea: posição + peso (nº de isofotas)."""

    xyz: np.ndarray     # (N,3) float32
    weight: np.ndarray  # (N,) uint8


def load_milkyway_points(data_dir: Path) -> PointCloud:
    """Splats da Via Láctea (modo pontos, usado em zoom fechado)."""
    npz = np.load(data_dir / "milkyway_pts.npz")
    return PointCloud(xyz=npz["xyz"].astype(np.float32), weight=npz["weight"])


# ---------------------------------------------------------------------------
# Grades de coordenadas (geradas proceduralmente)
# ---------------------------------------------------------------------------

def _circle_of_latitude(lat: float, step_deg: float) -> np.ndarray:
    """Paralelo completo na latitude dada, amostrado a cada ``step_deg``."""
    lon = np.radians(np.arange(0.0, 360.0 + step_deg, step_deg))
    cl = math.cos(lat)
    return np.stack(
        [cl * np.cos(lon), cl * np.sin(lon), np.full_like(lon, math.sin(lat))],
        axis=1,
    )


def _meridian(lon: float, lat_min: float, lat_max: float, step_deg: float) -> np.ndarray:
    """Arco de meridiano na longitude dada, entre duas latitudes."""
    lat = np.radians(np.arange(math.degrees(lat_min), math.degrees(lat_max) + step_deg, step_deg))
    cl = np.cos(lat)
    return np.stack(
        [cl * math.cos(lon), cl * math.sin(lon), np.sin(lat)], axis=1
    )


def build_grid(parallel_step: float = 10.0, meridian_step: float = 15.0,
               densify: float = 2.0) -> PolylineSet:
    """Grade de linhas de latitude/longitude numa esfera (serve para a grade
    horizontal — azimute/altitude — e para a equatorial — AR/declinação)."""
    polylines: list[np.ndarray] = []
    for lat_deg in np.arange(-80.0, 80.0 + 1e-6, parallel_step):
        polylines.append(_circle_of_latitude(math.radians(lat_deg), densify))
    for lon_deg in np.arange(0.0, 360.0, meridian_step):
        polylines.append(
            _meridian(math.radians(lon_deg), math.radians(-88.0), math.radians(88.0), densify)
        )
    counts = np.array([len(p) for p in polylines], dtype=np.int32)
    verts = np.concatenate(polylines).astype(np.float32)
    return PolylineSet.from_arrays(verts, counts)


def build_horizon(densify: float = 1.0) -> PolylineSet:
    """A linha do horizonte: o paralelo de altitude zero no frame horizontal."""
    verts = _circle_of_latitude(0.0, densify).astype(np.float32)
    return PolylineSet.from_arrays(verts, np.array([len(verts)], dtype=np.int32))


def load_outlines(data_dir: Path) -> dict[str, list[np.ndarray]]:
    """Contornos reais de nebulosas: {nome: [ (N,3) vetores ICRS, ... ]}."""
    path = data_dir / "outlines.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[np.ndarray]] = {}
    for name, polys in raw.items():
        shapes = []
        for poly in polys:
            arr = np.asarray(poly, dtype=np.float64)
            ra = np.radians(arr[:, 0])
            dec = np.radians(arr[:, 1])
            cd = np.cos(dec)
            pts = np.stack([cd * np.cos(ra), cd * np.sin(ra), np.sin(dec)],
                           axis=1)
            # fecha o anel
            if not np.allclose(pts[0], pts[-1]):
                pts = np.vstack([pts, pts[:1]])
            shapes.append(pts.astype(np.float32))
        if shapes:
            out[name] = shapes
    return out


def build_meridian(densify: float = 0.5) -> PolylineSet:
    """Meridiano local: círculo máximo N → zênite → S → nadir (frame horizontal)."""
    ang = np.radians(np.arange(0.0, 360.0 + densify, densify))
    verts = np.stack(
        [np.cos(ang), np.zeros_like(ang), np.sin(ang)], axis=1
    ).astype(np.float32)
    return PolylineSet.from_arrays(verts, np.array([len(verts)], dtype=np.int32))


def build_ecliptic(densify: float = 0.5) -> PolylineSet:
    """Eclíptica em coordenadas ICRS (obliquidade J2000 = 23,4393°)."""
    eps = math.radians(23.439291)
    lon = np.radians(np.arange(0.0, 360.0 + densify, densify))
    x = np.cos(lon)
    y = np.sin(lon) * math.cos(eps)
    z = np.sin(lon) * math.sin(eps)
    verts = np.stack([x, y, z], axis=1).astype(np.float32)
    return PolylineSet.from_arrays(verts, np.array([len(verts)], dtype=np.int32))


def build_equator(densify: float = 0.5) -> PolylineSet:
    """Equador celeste (ICRS)."""
    lon = np.radians(np.arange(0.0, 360.0 + densify, densify))
    verts = np.stack(
        [np.cos(lon), np.sin(lon), np.zeros_like(lon)], axis=1
    ).astype(np.float32)
    return PolylineSet.from_arrays(verts, np.array([len(verts)], dtype=np.int32))


def build_sphere_mesh(n_ra: int = 96, n_dec: int = 48):
    """Malha triangular da esfera celeste com UVs para textura equirretangular.

    Mesmo mecanismo do Stellarium: a Via Láctea é uma textura mapeada na
    esfera. Retorna (verts (V,3) ICRS, uv (V,2), tris (T,3)); a coluna de RA
    é duplicada na costura para evitar interpolação errada de u.
    """
    ra = np.linspace(0.0, 2.0 * math.pi, n_ra + 1)          # inclui costura
    dec = np.linspace(math.pi / 2, -math.pi / 2, n_dec + 1)  # topo -> base
    ra_g, dec_g = np.meshgrid(ra, dec)
    cd = np.cos(dec_g)
    verts = np.stack(
        [cd * np.cos(ra_g), cd * np.sin(ra_g), np.sin(dec_g)], axis=-1
    ).reshape(-1, 3)
    u = (ra_g / (2.0 * math.pi)).reshape(-1)
    v = ((math.pi / 2 - dec_g) / math.pi).reshape(-1)
    uv = np.stack([u, v], axis=1)

    cols = n_ra + 1
    i = np.arange(n_dec)[:, None]
    j = np.arange(n_ra)[None, :]
    a = (i * cols + j).ravel()
    b = (i * cols + j + 1).ravel()
    c = ((i + 1) * cols + j).ravel()
    d = ((i + 1) * cols + j + 1).ravel()
    tris = np.concatenate(
        [np.stack([a, b, c], axis=1), np.stack([b, d, c], axis=1)]
    ).astype(np.int32)
    return verts.astype(np.float32), uv.astype(np.float32), tris


def build_ground(az_step: float = 5.0, alt_step: float = 10.0):
    """Malha triangular do hemisfério abaixo do horizonte (solo opaco).

    Retorna (verts (V,3) float32, tris (T,3) int32). Malha densa para que a
    projeção com clamp de pontos atrás do observador degrade suavemente.
    """
    n_az = int(round(360.0 / az_step))
    az = np.radians(np.arange(n_az) * az_step)
    alts = np.radians(np.arange(0.0, -80.0 - 1e-6, -alt_step))
    rings = []
    for alt in alts:
        ca, sa = math.cos(alt), math.sin(alt)
        rings.append(
            np.stack([ca * np.cos(az), ca * np.sin(az), np.full(n_az, sa)], axis=1)
        )
    verts = np.concatenate(rings + [np.array([[0.0, 0.0, -1.0]])])
    nadir = len(verts) - 1

    tris = []
    n_rings = len(alts)
    for r in range(n_rings - 1):
        base0, base1 = r * n_az, (r + 1) * n_az
        for j in range(n_az):
            j2 = (j + 1) % n_az
            tris.append([base0 + j, base0 + j2, base1 + j])
            tris.append([base0 + j2, base1 + j2, base1 + j])
    base_last = (n_rings - 1) * n_az
    for j in range(n_az):
        j2 = (j + 1) % n_az
        tris.append([base_last + j, base_last + j2, nadir])
    return verts.astype(np.float32), np.asarray(tris, dtype=np.int32)


# Pontos cardeais no frame horizontal (az medido do norte para o leste).
CARDINALS = [
    ("N", 0.0), ("NE", 45.0), ("L", 90.0), ("SE", 135.0),
    ("S", 180.0), ("SO", 225.0), ("O", 270.0), ("NO", 315.0),
]


def cardinal_vectors() -> list[tuple[str, np.ndarray]]:
    """Pontos cardeais como vetores no horizonte, para os rótulos N/S/L/O."""
    out = []
    for name, az_deg in CARDINALS:
        az = math.radians(az_deg)
        out.append((name, np.array([math.cos(az), math.sin(az), 0.0])))
    return out
