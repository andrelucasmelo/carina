"""Fronteiras das constelações: trechos de AR ou Dec constantes em B1875.

As fronteiras IAU são meridianos e paralelos do equinócio B1875. Depois de
precessar os vértices gerados de volta a 1875, cada segmento consecutivo
deve manter OU a ascensão reta OU a declinação (a menos de ruído de
float32). Era isto que a subdivisão por círculo máximo violava perto dos
polos (fronteiras retilíneas em Octans/Mensa — revisão 2026-10, §1).
"""

import math
from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
B1875_JD_TT = 2405889.25858


@pytest.fixture(scope="module")
def segments_1875():
    npz_path = DATA / "const_bounds.npz"
    if not npz_path.exists():
        pytest.skip("const_bounds.npz ausente")
    from skyfield.api import load
    from skyfield.precessionlib import compute_precession

    P = np.asarray(compute_precession(load.timescale().tt_jd(B1875_JD_TT).tdb))
    npz = np.load(npz_path)
    verts, counts = npz["verts"].astype(np.float64), npz["counts"]
    out = []
    start = 0
    for n in counts:
        poly = verts[start:start + n] @ P.T          # J2000 → B1875
        start += n
        ra = np.degrees(np.arctan2(poly[:, 1], poly[:, 0])) % 360.0
        dec = np.degrees(np.arcsin(np.clip(poly[:, 2], -1, 1)))
        dra = (np.diff(ra) + 180.0) % 360.0 - 180.0
        ddec = np.diff(dec)
        out.append((dra * np.cos(np.radians(dec[:-1])), ddec, dec[:-1]))
    return out


def test_every_segment_keeps_ra_or_dec(segments_1875):
    bad = total = 0
    for dra_eff, ddec, _dec in segments_1875:
        total += len(ddec)
        # um dos dois tem de ser (quase) zero em cada passo
        bad += int(np.sum(np.minimum(np.abs(dra_eff), np.abs(ddec)) > 0.02))
    assert total > 10_000
    # Exceção conhecida: o d3-celestial representa o trecho UMi/Cep junto
    # ao polo norte (Dec ≈ +87,5° a +88°) com quatro cantos intermediários
    # que não são alinhados em 1875 — oito segmentos curtos (dois
    # polígonos) que a subdivisão em 0,5° transforma em ~28 passos.
    assert bad <= 40, f"{bad} de {total} segmentos mudam AR e Dec ao mesmo tempo"
    assert bad / total < 0.003


def test_polar_boundaries_are_parallels(segments_1875):
    """Perto do polo sul há trechos longos de Dec constante: arcos, não cordas.

    Um arco de paralelo com Dec ≈ −82° (Octans) subdividido a cada 0,5°
    tem dezenas de passos com Dec idêntica; com cordas de círculo máximo a
    declinação oscilaria ao longo do trecho.
    """
    runs = 0
    for dra_eff, ddec, dec in segments_1875:
        polar = dec < -75.0
        if not polar.any():
            continue
        const_dec = (np.abs(ddec) < 0.02) & polar & (np.abs(dra_eff) > 0.1)
        runs += int(const_dec.sum())
    assert runs >= 40


def test_segment_length_is_bounded(segments_1875):
    """Nenhum passo maior que o pedido (0,5°) — a subdivisão aconteceu."""
    for dra_eff, ddec, _dec in segments_1875:
        step = np.hypot(dra_eff, ddec)
        assert step.max() <= 0.5 + 1e-3
