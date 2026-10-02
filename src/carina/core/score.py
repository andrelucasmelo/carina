"""Pontuação de observabilidade (0–100) com explicação em português.

Junta numa nota só o que um observador experiente pesa de cabeça antes de
apontar o telescópio, e devolve também o **porquê** — cada fator vem com
uma frase curta para a ficha do objeto ("alto no céu, Lua longe, difuso
para seu céu").

Fatores (todos de 0 a 1)
------------------------
altitude
    Altitude na melhor hora da noite: 15° ou menos vale 0, 60° ou mais
    vale 1 (massa de ar de 1,15).
tempo
    Minutos utilizáveis na noite escura (acima da altitude mínima e do
    horizonte do quintal); duas horas valem 1.
lua
    Média, sobre a janela útil, do prejuízo causado pela Lua: iluminação ×
    proximidade (zona crítica de 10°–50° conforme a fase, a mesma da zona
    de influência para astrofotografia) mais o clareamento geral do céu
    quando ela está acima do horizonte.
céu
    O objeto aguenta o seu céu? Magnitude integrada contra a magnitude
    limite do instrumento (NELM do Bortle + ganho do instrumento) e, para
    objetos extensos, **brilho superficial** contra o brilho do fundo do
    céu — é o que separa M 31 (núcleo brilhante) de M 33 (difusa).

A nota é ``100 × (0,40·altitude + 0,25·tempo + 0,35·lua) × (0,2 + 0,8·céu)``:
o céu multiplica porque um objeto fraco demais para o seu céu não fica bom
só por estar alto. Cada fator é monotônico — melhorar um nunca piora a nota.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .eclipses import moon_influence_radii

# Magnitude limite a olho nu por classe de Bortle (escala clássica)
BORTLE_NELM = {1: 7.8, 2: 7.4, 3: 7.0, 4: 6.5, 5: 6.0, 6: 5.5, 7: 5.0,
               8: 4.5, 9: 4.0}
# Brilho do fundo do céu no zênite (mag/arcsec²), tabela de Bortle (2001)
BORTLE_SKY_SB = {1: 21.9, 2: 21.6, 3: 21.4, 4: 20.8, 5: 20.0, 6: 19.3,
                 7: 18.6, 8: 18.0, 9: 17.5}
ARCSEC2_PER_ARCMIN2 = 2.5 * math.log10(3600.0)      # 8,89 mag

# Ganho do instrumento sobre o olho nu: em magnitude limite estelar e, bem
# menor, no limiar de contraste de objetos extensos (o telescópio não deixa
# a nebulosa mais brilhante por unidade de área, só maior e mais escura).
INSTRUMENT_GAIN = {"olho": 0.0, "binoculo": 3.5, "pequeno": 5.5, "medio": 7.0}
INSTRUMENT_SB_GAIN = {"olho": 0.0, "binoculo": 0.6, "pequeno": 1.1, "medio": 1.5}

W_ALT, W_TIME, W_MOON = 0.40, 0.25, 0.35

VERDICTS = ((75, "Excelente"), (55, "Boa"), (35, "Razoável"), (1, "Difícil"),
            (0, "Não visível"))


def surface_brightness(mag: float | None, maj: float | None,
                       minor: float | None = None) -> float | None:
    """Brilho superficial médio em mag/arcmin² (elipse maj × min)."""
    if mag is None or not maj or maj <= 0:
        return None
    mn = minor if minor and minor > 0 else maj
    area = math.pi / 4.0 * maj * mn
    return float(mag) + 2.5 * math.log10(max(area, 1e-6))


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def altitude_factor(best_alt: float) -> float:
    return _clip01((best_alt - 15.0) / 45.0)


def time_factor(window_minutes: float) -> float:
    return _clip01(window_minutes / 120.0)


def moon_penalty(sep_deg, moon_alt_deg, illum: float):
    """Prejuízo da Lua (0..1) para separações e altitudes dadas (arrays)."""
    sep = np.asarray(sep_deg, dtype=np.float64)
    up = np.asarray(moon_alt_deg) > 0.0
    r1, r2 = (math.degrees(r) for r in moon_influence_radii(illum))
    prox = np.clip((r2 - sep) / (r2 - r1), 0.0, 1.0)
    pen = illum * (0.75 * prox + 0.25)               # 0,25 = céu lavado
    return np.where(up, np.clip(pen, 0.0, 1.0), 0.0)


def sky_factor(mag: float | None, maj: float | None, minor: float | None,
               klass: str, bortle: int, instrument: str = "pequeno") -> float:
    """O objeto aguenta o céu do observador com o instrumento dado?"""
    bortle = int(max(1, min(9, bortle)))
    if klass == "DARK":
        return _clip01((7.0 - bortle) / 5.0)
    if mag is None:
        return 0.5
    limit = BORTLE_NELM[bortle] + INSTRUMENT_GAIN.get(instrument, 5.5)
    f_mag = _clip01((limit - float(mag)) / 3.0)
    if klass in ("STAR", "PLANET", "MOON", "SUN"):
        return f_mag
    sb = surface_brightness(mag, maj, minor)
    if sb is None or (maj or 0) < 1.0:
        return f_mag                       # quase pontual: vale a magnitude
    sky = BORTLE_SKY_SB[bortle] - ARCSEC2_PER_ARCMIN2
    gain = INSTRUMENT_SB_GAIN.get(instrument, 1.1)
    f_sb = _clip01((sky + gain + 2.5 - sb) / 3.5)
    return 0.5 * f_mag + 0.5 * f_sb


def combine(f_alt: float, f_time: float, f_moon: float, f_sky: float) -> float:
    base = W_ALT * f_alt + W_TIME * f_time + W_MOON * f_moon
    return 100.0 * base * (0.2 + 0.8 * f_sky)


def verdict_of(total: int) -> str:
    for limit, text in VERDICTS:
        if total >= limit:
            return text
    return VERDICTS[-1][1]


@dataclass
class Factor:
    key: str                 # 'alt' | 'time' | 'moon' | 'sky'
    value: float             # 0..1
    text: str                # frase curta em PT


@dataclass
class Score:
    total: int
    verdict: str
    factors: list[Factor] = field(default_factory=list)
    reason: str = ""         # motivo principal quando total = 0

    def factor(self, key: str) -> Factor | None:
        return next((f for f in self.factors if f.key == key), None)

    def explain(self) -> str:
        """Frase única: "Boa (68): alto no céu, Lua longe, difuso…"."""
        if self.total <= 0:
            return f"{self.verdict}: {self.reason}" if self.reason else self.verdict
        parts = ", ".join(f.text for f in self.factors if f.text)
        return f"{self.verdict} ({self.total}): {parts}"


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _moon_text(f_moon: float, illum: float, sep_best: float, moon_alt_best: float) -> str:
    pct = round(illum * 100)
    if f_moon >= 0.9 or illum < 0.08:
        return "Lua longe ou abaixo do horizonte" if illum >= 0.08 else "sem Lua"
    if moon_alt_best > 0 and sep_best < 40:
        return f"Lua ({pct}%) a {sep_best:.0f}° atrapalha"
    return f"Lua ({pct}%) clareia o céu"


def _sky_text(f_sky: float, klass: str, bortle: int) -> str:
    if f_sky >= 0.75:
        return "brilhante o bastante para seu céu"
    if f_sky >= 0.45:
        return f"exige céu razoável (Bortle {bortle})"
    if klass in ("STAR", "PLANET"):
        return "fraco para seu céu"
    return f"difuso para seu céu (Bortle {bortle})"


def score_visibility(vis, mag: float | None = None, maj: float | None = None,
                     minor: float | None = None, klass: str = "",
                     bortle: int = 4, instrument: str = "pequeno") -> Score:
    """Pontua uma :class:`core.visibility.Visibility` já calculada."""
    from .localtime import to_local

    grid = vis.grid
    if not vis.observable:
        if vis.never_up:
            reason = "não nasce no seu local nesta data"
        elif vis.blocked_minutes > 0 and vis.best_alt >= vis.min_alt:
            reason = "fica atrás do seu horizonte durante a noite escura"
        elif vis.best_alt < 0:
            reason = "abaixo do horizonte durante toda a noite escura"
        else:
            reason = (f"não passa de {max(vis.best_alt, 0):.0f}° na noite "
                      f"escura (mínimo {vis.min_alt:.0f}°)")
        return Score(0, "Não visível", [], reason)

    f_alt = altitude_factor(vis.best_alt)
    hour = to_local(vis.best_utc).strftime("%H:%M") if vis.best_utc else ""
    alt_txt = (f"alto no céu ({vis.best_alt:.0f}° às {hour})" if f_alt >= 0.66
               else f"altura média ({vis.best_alt:.0f}° às {hour})" if f_alt >= 0.33
               else f"baixo no céu ({vis.best_alt:.0f}° às {hour})")

    minutes = vis.window_minutes
    f_time = time_factor(minutes)
    time_txt = f"{_hm(minutes)} de janela"
    if vis.blocked_minutes >= 20:
        time_txt += f" ({_hm(vis.blocked_minutes)} atrás do horizonte)"

    if klass in ("MOON", "SUN") or (vis.target.body == "Lua"):
        f_moon, moon_txt = 1.0, ""
    else:
        idx = [i for i, t in enumerate(grid.times)
               if any(a <= t <= b for a, b in vis.segments)]
        if idx:
            sep = grid.moon_separation(vis.alts[idx], vis.azs[idx], idx)
            pen = moon_penalty(sep, grid.moon_alt[idx], grid.moon_illum)
            f_moon = _clip01(1.0 - float(np.mean(pen)))
        else:
            f_moon = 1.0
        if klass == "PLANET":
            f_moon = 1.0 - 0.3 * (1.0 - f_moon)     # planeta não sofre com a Lua
        moon_txt = _moon_text(f_moon, grid.moon_illum, vis.moon_sep_best,
                              vis.moon_alt_best)

    f_sky = sky_factor(mag, maj, minor, klass, bortle, instrument)
    total = int(round(combine(f_alt, f_time, f_moon, f_sky)))
    total = max(1, min(100, total))
    factors = [Factor("alt", f_alt, alt_txt), Factor("time", f_time, time_txt),
               Factor("moon", f_moon, moon_txt),
               Factor("sky", f_sky, _sky_text(f_sky, klass, bortle))]
    return Score(total, verdict_of(total), factors)


def score_batch(grid, icrs: np.ndarray, mags, majs, mins, klasses,
                bortle: int = 4, instrument: str = "pequeno",
                min_alt: float = 20.0, horizon=None) -> np.ndarray:
    """Notas (N,) para muitos alvos fixos de uma vez, na resolução da grade.

    Mesmo modelo de :func:`score_visibility`, sem refinamento de instantes
    — serve para ordenar candidatos ("Hoje à noite", busca, listas).
    """
    from .visibility import batch_usable

    icrs = np.atleast_2d(icrs)
    best, minutes, alts, azs = batch_usable(grid, icrs, min_alt, horizon)
    limit = np.full_like(alts, float(min_alt))
    if horizon is not None and not horizon.is_flat:
        limit = np.maximum(limit, horizon.altitude_at(azs))
    ok = (alts >= limit) & grid.dark_mask[np.newaxis, :]
    sep = grid.moon_separation(alts, azs)                       # (N, T)
    pen = moon_penalty(sep, grid.moon_alt[np.newaxis, :], grid.moon_illum)
    with np.errstate(invalid="ignore"):
        mean_pen = np.where(ok.any(axis=1),
                            (pen * ok).sum(axis=1) / np.maximum(ok.sum(axis=1), 1),
                            0.0)
    best_ok = np.where(ok, alts, -90.0).max(axis=1)
    out = np.zeros(len(icrs))
    for i in range(len(icrs)):
        if minutes[i] <= 0:
            continue
        f_sky = sky_factor(mags[i], majs[i], mins[i], klasses[i], bortle, instrument)
        total = combine(altitude_factor(best_ok[i]), time_factor(minutes[i]),
                        _clip01(1.0 - mean_pen[i]), f_sky)
        out[i] = max(1.0, min(100.0, round(total)))
    return out
