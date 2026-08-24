"""Formatação de coordenadas e grandezas astronômicas para exibição."""

from __future__ import annotations

import math


def ra_hms(ra_rad: float) -> str:
    """Ascensão reta em 'HHh MMm SSs'."""
    hours = (math.degrees(ra_rad) / 15.0) % 24.0
    h = int(hours)
    m = int((hours - h) * 60.0)
    s = ((hours - h) * 60.0 - m) * 60.0
    return f"{h:02d}h {m:02d}m {s:04.1f}s"


def dec_dms(dec_rad: float) -> str:
    """Declinação em '±DD° MM′ SS″'."""
    deg = math.degrees(dec_rad)
    sign = "-" if deg < 0 else "+"
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60.0)
    s = ((deg - d) * 60.0 - m) * 60.0
    return f"{sign}{d:02d}° {m:02d}′ {s:04.1f}″"


def angle_deg(rad: float, decimals: int = 1) -> str:
    return f"{math.degrees(rad):.{decimals}f}°"


def speed_label(speed: float) -> str:
    """Rótulo curto da velocidade da simulação ('⏸', '', '×100', '×-10')."""
    if speed == 0.0:
        return "⏸ pausado"
    if speed == 1.0:
        return ""
    if speed == int(speed):
        return f"×{int(speed)}"
    return f"×{speed:g}"
