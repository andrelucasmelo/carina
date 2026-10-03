"""Gera o mapa de brilho artificial do céu embarcado (v0.19 T6, ADR-050).

Fonte: **NASA Black Marble 2016** (Earth at Night, VIIRS DNB, composição
global de 3 km; domínio público), em ``data/raw/lightpollution``.

O atlas de Falchi et al. (2016) seria a referência, mas é liberado só por
formulário e sob CC BY-NC — incompatível com a licença MIT do Carina. Em
vez dele, fazemos aqui uma versão simplificada do mesmo modelo:

1. **luz emitida**: a imagem é uma composição colorida para visualização;
   as luzes artificiais são amareladas (R ≥ B) e o fundo (solo ao luar,
   oceano) é azulado. Índice de luz = max(0, R − 0,55·B), na resolução de
   3 km, somado em células de 0,1°;
2. **brilho do céu**: cada célula ilumina as vizinhas com a lei de Walker
   (∝ (d + 1 km)^−2,5) até 250 km — convolução por FFT em faixas de
   latitude, com o núcleo em km corrigido pelo cosseno da latitude;
3. **magnitude do céu**: SQM ≈ 22,0 − 2,5·log10(1 + (G/G₀)^γ), com G₀ e
   γ ajustados por mínimos quadrados em referências tiradas do atlas de
   Falchi (metrópoles, cidades médias, sítios, Amazônia, Atacama).

Saída: ``data/processed/lightpollution.npz`` — uint8 3600×1800 com
(22,0 − SQM)·40 (0 = céu natural), mais os metadados.

É uma estimativa para **sugerir** o Bortle ao escolher a cidade; o
usuário continua escolhendo o valor final.

Uso:
    python scripts/build_lightpollution.py [--download]
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "lightpollution"
OUT = ROOT / "data" / "processed" / "lightpollution.npz"
URL = ("https://eoimages.gsfc.nasa.gov/images/imagerecords/144000/144898/"
       "BlackMarble_2016_3km_geo.tif")
SRC = RAW / "BlackMarble_2016_3km_geo.tif"

W, H = 3600, 1800              # 0,1°
KM_PER_DEG = 111.195
RADIUS_KM = 250.0
CORE_KM = 6.0
EXT_KM = 120.0
SQM_NATURAL = 22.0
SCALE = 40.0                   # uint8 = (22 − SQM)·40 → até 6,4 mag

# referências de calibração e conferência (lat, lon, SQM aproximado)
REFERENCES = [
    ("São Paulo (centro)", -23.55, -46.63, 17.9),
    ("Rio de Janeiro (centro)", -22.91, -43.18, 18.2),
    ("Campinas", -22.90, -47.06, 18.4),
    ("Brasília (Plano Piloto)", -15.79, -47.88, 18.6),
    ("Ribeirão Preto", -21.18, -47.81, 18.9),
    ("Interior de MG (rural)", -18.5, -45.5, 21.6),
    ("Serra da Mantiqueira (sítio)", -22.5, -45.6, 20.8),
    ("Amazônia", -5.0, -63.0, 21.95),
    ("Atacama (San Pedro)", -22.9, -68.2, 21.8),
]


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        with urllib.request.urlopen(URL) as resp:
            SRC.write_bytes(resp.read())


def light_index() -> np.ndarray:
    """Índice de luz artificial em células de 0,1° (média da grade 3 km)."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    img = np.asarray(Image.open(SRC).convert("RGB"), dtype=np.float32)
    # piso de 6: o solo claro ao luar (desertos) passa um pouco de vermelho
    light = np.maximum(0.0, img[:, :, 0] - 0.55 * img[:, :, 2] - 6.0)
    lim = Image.fromarray(light, mode="F").resize((W, H), Image.Resampling.BOX)
    return np.asarray(lim, dtype=np.float64)


def sky_glow(light: np.ndarray) -> np.ndarray:
    """Convolução com a lei de Walker, em faixas de 5° de latitude."""
    out = np.zeros_like(light)
    band = 50                                   # linhas por faixa (5°)
    pad_rows = int(RADIUS_KM / KM_PER_DEG / 0.1) + 2
    for r0 in range(0, H, band):
        r1 = min(H, r0 + band)
        lat_c = 90.0 - (r0 + r1) / 2 * 0.1
        coslat = max(np.cos(np.radians(lat_c)), 0.05)
        km_x = 0.1 * KM_PER_DEG * coslat
        km_y = 0.1 * KM_PER_DEG
        nx = int(min(RADIUS_KM / km_x, W / 2 - 1))
        ny = pad_rows
        yy, xx = np.mgrid[-ny:ny + 1, -nx:nx + 1]
        d = np.hypot(xx * km_x, yy * km_y)
        # Walker com núcleo suavizado (a luz da própria célula se espalha por
        # ~10 km) e extinção atmosférica nas distâncias grandes
        kern = np.where(d <= RADIUS_KM, (d + CORE_KM) ** -2.5 * np.exp(-d / EXT_KM), 0.0)
        a0, a1 = max(0, r0 - ny), min(H, r1 + ny)
        block = light[a0:a1]
        # dá a volta em longitude: preenche com as bordas opostas
        block = np.concatenate([block[:, -nx:], block, block[:, :nx]], axis=1)
        sh = (block.shape[0] + kern.shape[0] - 1, block.shape[1] + kern.shape[1] - 1)
        conv = np.fft.irfft2(np.fft.rfft2(block, sh) * np.fft.rfft2(kern, sh), sh)
        conv = conv[ny:ny + block.shape[0], nx:nx + block.shape[1]]
        conv = conv[:, nx:nx + W]
        out[r0:r1] = conv[r0 - a0:r0 - a0 + (r1 - r0)]
    return np.maximum(out, 0.0)


def at(arr: np.ndarray, lat: float, lon: float) -> float:
    x = int((lon + 180.0) / 360.0 * W) % W
    y = min(H - 1, max(0, int((90.0 - lat) / 180.0 * H)))
    return float(arr[y, x])


def to_sqm(glow: np.ndarray, g0: float, gamma: float = 1.0) -> np.ndarray:
    return SQM_NATURAL - 2.5 * np.log10(1.0 + (glow / g0) ** gamma)


def calibrate(glow: np.ndarray) -> tuple[float, float]:
    """(G₀, γ) por mínimos quadrados nas referências.

    O expoente γ compensa a saturação dos centros urbanos na imagem de
    origem (todas as metrópoles chegam a 255)."""
    gs = np.array([at(glow, lat, lon) for _, lat, lon, _ in REFERENCES])
    ref = np.array([r for *_, r in REFERENCES])
    best = None
    for gamma in np.linspace(0.6, 2.0, 57):
        for lg0 in np.linspace(np.log10(gs.max()) - 4, np.log10(gs.max()) + 1, 201):
            pred = to_sqm(gs, 10 ** lg0, gamma)
            err = float(np.sum((pred - ref) ** 2))
            if best is None or err < best[0]:
                best = (err, 10 ** lg0, gamma)
    return best[1], best[2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()
    if args.download:
        download()
    light = light_index()
    glow = sky_glow(light)
    g0, gamma = calibrate(glow)
    print(f"  calibração: G0 = {g0:.4g}, gama = {gamma:.3f}")
    sqm = to_sqm(glow, g0, gamma)
    for name, lat, lon, ref in REFERENCES:
        print(f"  {name:26s} SQM {at(sqm, lat, lon):5.2f}  (referência ~{ref})")
    enc = np.clip(np.round((SQM_NATURAL - sqm) * SCALE), 0, 255).astype(np.uint8)
    np.savez_compressed(OUT, sky=enc, sqm_natural=np.float32(SQM_NATURAL),
                        scale=np.float32(SCALE),
                        source=np.array("NASA Black Marble 2016 (VIIRS DNB), modelo de Walker"))
    print(f"{OUT.name}: {OUT.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
