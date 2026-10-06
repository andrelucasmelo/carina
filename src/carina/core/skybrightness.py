"""Brilho do céu causado pela Lua — modelo de Krisciunas & Schaefer (1991).

K. Krisciunas & B. E. Schaefer, "A model of the brightness of moonlight",
PASP 103, 1033 (1991). Em nanoLamberts:

    B_lua = f(ρ) · I* · 10^(−0,4·k·X(Zₗ)) · [1 − 10^(−0,4·k·X(Z))]
    I*    = 10^(−0,4·(3,84 + 0,026·|α| + 4·10⁻⁹·α⁴))       (α = ângulo de fase, °)
    f(ρ)  = 10^5,36·(1,06 + cos²ρ) + 10^(6,15 − ρ/40)       (ρ = separação, °)
    X(Z)  = (1 − 0,96·sin²Z)^(−1/2)                          (massa de ar)

com k o coeficiente de extinção em V (0,172 mag no artigo, Mauna Kea) e
Zₗ, Z as distâncias zenitais da Lua e do ponto do céu. O fundo escuro vem
do SQM do local (mag/arcsec²); a conversão usa a relação do artigo
B = 34,08·exp(20,7233 − 0,92104·V).

Usado na zona de influência da Lua (camada ``U``). Com a Lua cheia o céu
**inteiro** clareia mais de 2 magnitudes, então os anéis marcam onde o céu
fica 0,5, 1 e 1,5 mag mais claro **que a 90° da Lua** (``relative_separation``)
— a zona em que a proximidade da Lua pesa —, e o clareamento geral do céu
(``delta_mag`` a 90°) vai como texto.
"""

from __future__ import annotations

import math

K_DEFAULT = 0.172


def airmass(z_deg: float) -> float:
    s = math.sin(math.radians(min(max(z_deg, 0.0), 89.9)))
    return (1.0 - 0.96 * s * s) ** -0.5


def mag_to_nl(v: float) -> float:
    return 34.08 * math.exp(20.7233 - 0.92104 * v)


def nl_to_mag(b: float) -> float:
    return (20.7233 - math.log(b / 34.08)) / 0.92104


def moon_brightness_nl(phase_angle_deg: float, sep_deg: float, z_moon_deg: float,
                       z_sky_deg: float, k: float = K_DEFAULT) -> float:
    """Brilho acrescentado pela Lua (nanoLamberts); zero com a Lua abaixo do horizonte."""
    if z_moon_deg >= 90.0:
        return 0.0
    a = abs(phase_angle_deg)
    i_star = 10 ** (-0.4 * (3.84 + 0.026 * a + 4e-9 * a ** 4))
    rho = max(sep_deg, 0.5)
    f = 10 ** 5.36 * (1.06 + math.cos(math.radians(rho)) ** 2) + 10 ** (6.15 - rho / 40.0)
    return (f * i_star * 10 ** (-0.4 * k * airmass(z_moon_deg))
            * (1 - 10 ** (-0.4 * k * airmass(z_sky_deg))))


def sky_mag(dark_mag: float, phase_angle_deg: float, sep_deg: float, z_moon_deg: float,
            z_sky_deg: float, k: float = K_DEFAULT) -> float:
    """Brilho do céu (mag/arcsec²) com a Lua, a partir do céu escuro do local."""
    b0 = mag_to_nl(dark_mag)
    return nl_to_mag(b0 + moon_brightness_nl(phase_angle_deg, sep_deg, z_moon_deg,
                                             z_sky_deg, k))


def delta_mag(dark_mag: float, phase_angle_deg: float, sep_deg: float, z_moon_deg: float,
              z_sky_deg: float, k: float = K_DEFAULT) -> float:
    """Quanto a Lua clareia o céu (magnitudes, negativo = mais claro)."""
    return sky_mag(dark_mag, phase_angle_deg, sep_deg, z_moon_deg, z_sky_deg, k) - dark_mag


def separation_for(delta: float, dark_mag: float, phase_angle_deg: float,
                   z_moon_deg: float, z_sky_deg: float, k: float = K_DEFAULT) -> float | None:
    """Separação (°) em que o céu fica ``delta`` mag mais claro (busca binária);
    None se nem perto da Lua chega a tanto."""
    def d(rho):
        return delta_mag(dark_mag, phase_angle_deg, rho, z_moon_deg, z_sky_deg, k)

    if d(3.0) > delta:            # nem a 3° da Lua o céu clareia tanto
        return None
    if d(180.0) <= delta:         # clareia tudo
        return 180.0
    lo, hi = 3.0, 180.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if d(mid) <= delta:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def relative_separation(delta: float, phase_angle_deg: float, z_moon_deg: float,
                        z_sky_deg: float, dark_mag: float = 21.6,
                        k: float = K_DEFAULT) -> float | None:
    """Separação (°) em que o céu fica ``delta`` mag (negativo) mais claro que
    a 90° da Lua; None se nem a 3° dela chega a tanto ou a Lua não está no céu."""
    if z_moon_deg >= 90.0:
        return None
    ref = sky_mag(dark_mag, phase_angle_deg, 90.0, z_moon_deg, z_sky_deg, k)

    def d(rho):
        return sky_mag(dark_mag, phase_angle_deg, rho, z_moon_deg, z_sky_deg, k) - ref

    if d(3.0) > delta:
        return None
    lo, hi = 3.0, 90.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if d(mid) <= delta:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2

