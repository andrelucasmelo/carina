"""Estimativa de exposição para astrofotografia (v0.19 T2).

Modelo deliberadamente simples, do tipo usado nas calculadoras de
astrofotografia amadora:

- **fundo de céu** no pixel: o brilho do céu (mag/arcsec², pelo Bortle ou
  pelo mapa de poluição luminosa) vira fluxo de fótons; multiplica-se pela
  área da abertura, pela área do pixel no céu (escala de placa²), pela
  eficiência quântica e pela transmissão do conjunto;
- **sub-exposição sugerida**: longa o bastante para o ruído do fundo de
  céu "afogar" o ruído de leitura (sinal do céu ≥ 10 × RN²); curta o
  bastante para não saturar estrelas nem acumular erros de guiagem;
- **integração**: horas úteis por noite (da sessão ou do calendário de
  imageabilidade) e quantas noites para juntar N horas.

Os números são **ordens de grandeza** para começar o ensaio — o histograma
da primeira sub é que manda.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# fótons/s/cm² de uma fonte de magnitude 0 na banda visual larga (~400–700 nm)
PHOTONS_MAG0 = 1.0e6
THROUGHPUT = 0.7          # espelhos, lentes, filtro UV/IR
SWAMP = 10.0              # céu ≥ 10·RN² por pixel
SUB_STEPS = (5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600)

# Bortle → magnitude típica do céu no zênite (mag/arcsec²)
BORTLE_SQM = {1: 21.9, 2: 21.6, 3: 21.4, 4: 20.9, 5: 20.2, 6: 19.6, 7: 19.0,
              8: 18.5, 9: 17.8}

# ruído de leitura (e⁻) e eficiência quântica típicos, pelo nome da câmera
CAMERA_HINTS = [
    ("533", 1.0, 0.80), ("2600", 1.0, 0.80), ("294", 1.2, 0.75), ("183", 1.6, 0.84),
    ("224", 0.8, 0.75), ("120", 2.5, 0.60), ("174", 3.5, 0.78), ("462", 0.8, 0.80),
    ("585", 0.8, 0.80), ("662", 0.8, 0.80), ("6200", 1.2, 0.80), ("dslr", 3.0, 0.50),
    ("micro 4/3", 2.5, 0.55),
]


def camera_noise(camera) -> tuple[float, float]:
    """(ruído de leitura e⁻, eficiência quântica) da câmera."""
    rn = float(getattr(camera, "read_noise_e", 0.0) or 0.0)
    qe = float(getattr(camera, "qe", 0.0) or 0.0)
    name = getattr(camera, "name", "").lower()
    for key, h_rn, h_qe in CAMERA_HINTS:
        if key in name:
            return (rn or h_rn, qe or h_qe)
    return (rn or 2.0, qe or 0.6)


def plate_scale_arcsec(scope, camera, accessory=None) -> float:
    """Escala de placa (″/pixel)."""
    focal = scope.focal_mm * (accessory.factor if accessory else 1.0)
    pixel = getattr(camera, "pixel_um", 0.0) or 3.76
    return 206.265 * pixel / focal


def sky_electrons_per_s(sqm: float, scope, camera, accessory=None) -> float:
    """Elétrons por segundo por pixel vindos do fundo de céu."""
    area_cm2 = math.pi * (scope.aperture_mm / 20.0) ** 2
    scale = plate_scale_arcsec(scope, camera, accessory)
    _rn, qe = camera_noise(camera)
    photons = PHOTONS_MAG0 * 10 ** (-0.4 * sqm) * area_cm2 * scale ** 2
    # câmera colorida (matriz de Bayer): cada pixel vê ~1/3 da banda
    bayer = 1 / 3 if "mc" in getattr(camera, "name", "").lower() or \
        "dslr" in camera.name.lower() or "seestar" in camera.name.lower() else 1.0
    return photons * qe * THROUGHPUT * bayer


@dataclass
class ExposureAdvice:
    sub_s: int
    sky_e_s: float
    read_noise: float
    plate_scale: float
    sqm: float
    reason: str

    def text(self) -> str:
        from .formats import num

        return (f"Subs de ~{self.sub_s} s: o céu (≈{num(self.sky_e_s, 2)} e⁻/s por pixel, "
                f"{num(self.sqm)} mag/arcsec²) cobre o ruído de leitura "
                f"({num(self.read_noise)} e⁻). {self.reason}")


def suggest_sub(sqm: float, scope, camera, accessory=None, altaz: bool = False) -> ExposureAdvice:
    """Sub-exposição sugerida (segundos)."""
    rn, _qe = camera_noise(camera)
    sky = sky_electrons_per_s(sqm, scope, camera, accessory)
    t = SWAMP * rn * rn / max(sky, 1e-6)
    reason = ""
    limit = 600
    if altaz:
        # rotação de campo: alt-az limita a sub (Seestar trabalha com 10–30 s)
        limit = 30
        reason = "Montagem altazimutal: subs curtas por causa da rotação de campo."
    elif scope.focal_mm * (accessory.factor if accessory else 1.0) > 1200:
        limit = 300
        reason = "Focal longa: subs mais curtas aliviam a guiagem."
    if t > limit:
        t = limit
    sub = min(SUB_STEPS, key=lambda s: abs(s - t))
    sub = min(sub, limit)
    if t < 5:
        reason = (reason + " Céu claro: subs bem curtas; um filtro de banda estreita "
                  "ou de poluição luminosa ajuda muito.").strip()
    return ExposureAdvice(int(sub), sky, rn, plate_scale_arcsec(scope, camera, accessory),
                          sqm, reason)


def nights_for(hours_goal: float, hours_per_night: list[float]) -> int | None:
    """Quantas noites (na ordem dada) para juntar ``hours_goal`` horas."""
    acc = 0.0
    for k, h in enumerate(hours_per_night, start=1):
        acc += max(0.0, h)
        if acc >= hours_goal:
            return k
    return None
