"""Catálogo de estrelas (HYG) processado por scripts/build_data.py.

Os arrays vêm ordenados por magnitude crescente, de modo que o corte por
magnitude-limite em tempo de execução é um simples slice via searchsorted.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Letras gregas das designações de Bayer (códigos usados pelo HYG).
GREEK = {
    "Alp": "α", "Bet": "β", "Gam": "γ", "Del": "δ", "Eps": "ε", "Zet": "ζ",
    "Eta": "η", "The": "θ", "Iot": "ι", "Kap": "κ", "Lam": "λ", "Mu": "μ",
    "Nu": "ν", "Xi": "ξ", "Omi": "ο", "Pi": "π", "Rho": "ρ", "Sig": "σ",
    "Tau": "τ", "Ups": "υ", "Phi": "φ", "Chi": "χ", "Psi": "ψ", "Ome": "ω",
}
_SUPERSCRIPT = {"1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵"}

# Nome por extenso das letras gregas (para designações completas).
GREEK_FULL = {
    "Alp": "Alpha", "Bet": "Beta", "Gam": "Gamma", "Del": "Delta",
    "Eps": "Epsilon", "Zet": "Zeta", "Eta": "Eta", "The": "Theta",
    "Iot": "Iota", "Kap": "Kappa", "Lam": "Lambda", "Mu": "Mu", "Nu": "Nu",
    "Xi": "Xi", "Omi": "Omicron", "Pi": "Pi", "Rho": "Rho", "Sig": "Sigma",
    "Tau": "Tau", "Ups": "Upsilon", "Phi": "Phi", "Chi": "Chi", "Psi": "Psi",
    "Ome": "Omega",
}

# Genitivo latino das 88 constelações (abreviação IAU -> genitivo).
GENITIVE = {
    "And": "Andromedae", "Ant": "Antliae", "Aps": "Apodis", "Aqr": "Aquarii",
    "Aql": "Aquilae", "Ara": "Arae", "Ari": "Arietis", "Aur": "Aurigae",
    "Boo": "Boötis", "Cae": "Caeli", "Cam": "Camelopardalis", "Cnc": "Cancri",
    "CVn": "Canum Venaticorum", "CMa": "Canis Majoris", "CMi": "Canis Minoris",
    "Cap": "Capricorni", "Car": "Carinae", "Cas": "Cassiopeiae",
    "Cen": "Centauri", "Cep": "Cephei", "Cet": "Ceti", "Cha": "Chamaeleontis",
    "Cir": "Circini", "Col": "Columbae", "Com": "Comae Berenices",
    "CrA": "Coronae Australis", "CrB": "Coronae Borealis", "Crv": "Corvi",
    "Crt": "Crateris", "Cru": "Crucis", "Cyg": "Cygni", "Del": "Delphini",
    "Dor": "Doradus", "Dra": "Draconis", "Equ": "Equulei", "Eri": "Eridani",
    "For": "Fornacis", "Gem": "Geminorum", "Gru": "Gruis", "Her": "Herculis",
    "Hor": "Horologii", "Hya": "Hydrae", "Hyi": "Hydri", "Ind": "Indi",
    "Lac": "Lacertae", "Leo": "Leonis", "LMi": "Leonis Minoris",
    "Lep": "Leporis", "Lib": "Librae", "Lup": "Lupi", "Lyn": "Lyncis",
    "Lyr": "Lyrae", "Men": "Mensae", "Mic": "Microscopii",
    "Mon": "Monocerotis", "Mus": "Muscae", "Nor": "Normae", "Oct": "Octantis",
    "Oph": "Ophiuchi", "Ori": "Orionis", "Pav": "Pavonis", "Peg": "Pegasi",
    "Per": "Persei", "Phe": "Phoenicis", "Pic": "Pictoris", "Psc": "Piscium",
    "PsA": "Piscis Austrini", "Pup": "Puppis", "Pyx": "Pyxidis",
    "Ret": "Reticuli", "Sge": "Sagittae", "Sgr": "Sagittarii",
    "Sco": "Scorpii", "Scl": "Sculptoris", "Sct": "Scuti", "Ser": "Serpentis",
    "Sex": "Sextantis", "Tau": "Tauri", "Tel": "Telescopii",
    "Tri": "Trianguli", "TrA": "Trianguli Australis", "Tuc": "Tucanae",
    "UMa": "Ursae Majoris", "UMi": "Ursae Minoris", "Vel": "Velorum",
    "Vir": "Virginis", "Vol": "Volantis", "Vul": "Vulpeculae",
}


def bayer_display(code: str, con: str | None = None, full: bool = False) -> str:
    """'Alp' + 'CMa' -> 'α CMa' (ou 'Alpha Canis Majoris' se full)."""
    base, _, sub = code.partition("-")
    letter = GREEK.get(base, base)
    sup = _SUPERSCRIPT.get(sub, sub)
    if full and con:
        return f"{GREEK_FULL.get(base, base)}{sup} {GENITIVE.get(con, con)}"
    if con:
        return f"{letter}{sup} {con}"
    return f"{letter}{sup}"


def bv_to_temperature(bv) -> np.ndarray:
    """Temperatura efetiva (K) pelo índice B−V — fórmula de Ballesteros (2012)."""
    bv = np.clip(np.asarray(bv, dtype=np.float64), -0.4, 2.0)
    return 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))


def temperature_to_rgb(kelvin) -> np.ndarray:
    """Cor de um corpo negro (aproximação de Tanner Helland), 0..1.

    Ajuste empírico sobre a tabela de Mitchell Charity, bom de 1000 K a
    40 000 K — o intervalo das estrelas a olho nu.
    """
    t = np.clip(np.asarray(kelvin, dtype=np.float64), 1000.0, 40000.0) / 100.0
    r = np.where(t <= 66, 255.0, 329.698727446 * np.power(np.maximum(t - 60, 1e-6), -0.1332047592))
    g = np.where(t <= 66, 99.4708025861 * np.log(t) - 161.1195681661,
                 288.1221695283 * np.power(np.maximum(t - 60, 1e-6), -0.0755148492))
    b = np.where(t >= 66, 255.0,
                 np.where(t <= 19, 0.0, 138.5177312231 * np.log(np.maximum(t - 10, 1e-6))
                          - 305.0447927307))
    return np.clip(np.stack([r, g, b], axis=-1) / 255.0, 0.0, 1.0)


def _bv_to_rgb(bv: np.ndarray, saturation: float = 0.75) -> np.ndarray:
    """Índice de cor B−V → RGB de exibição (v0.16 T4).

    Temperatura de Ballesteros → corpo negro → normalizado para o canal
    mais forte valer 1 (o brilho vem do tamanho e do alfa do sprite) →
    saturação reduzida, porque a cor das estrelas a olho nu é sutil:
    azul-esbranquiçada em Rigel, branca em Vega, amarela no Sol, laranja em
    Arcturus, alaranjado-avermelhada em Antares.
    """
    rgb = temperature_to_rgb(bv_to_temperature(bv))
    rgb = rgb / np.maximum(rgb.max(axis=-1, keepdims=True), 1e-6)
    gray = rgb.mean(axis=-1, keepdims=True)
    rgb = gray + (rgb - gray) * saturation
    return np.clip(rgb / np.maximum(rgb.max(axis=-1, keepdims=True), 1e-6),
                   0.0, 1.0).astype(np.float32)


class StarCatalog:
    """Catálogo estelar em arrays NumPy, ORDENADOS POR MAGNITUDE.

    A ordenação é a decisão estrutural do catálogo: "todas as estrelas até
    magnitude X" vira um prefixo do array obtido com ``searchsorted`` —
    sem máscaras, sem cópias. Duas camadas:

    * **HYG v4.1** (~120 mil, até mag ~9): com nomes próprios, Bayer,
      Flamsteed e constelação — participa de rótulos e seleção;
    * **profundo** (ATHYG/Tycho-2, ~740 mil, mag 8,5–12): anônimo, só
      pontos, carregado à parte e desenhado apenas quando o zoom pede.
    """

    def __init__(self, data_dir: Path) -> None:
        npz = np.load(data_dir / "stars_hyg.npz")
        self.xyz: np.ndarray = npz["xyz"].astype(np.float32)     # (N,3) ICRS
        self.mag: np.ndarray = npz["mag"]                        # crescente
        self.ci: np.ndarray = npz["ci"]
        self.hip: np.ndarray = npz["hip"]
        self.ra: np.ndarray = npz["ra"]                          # radianos J2000
        self.dec: np.ndarray = npz["dec"]
        # distância (pc, 0 = desconhecida) e tipo espectral — v0.15
        self.dist = npz["dist"] if "dist" in npz.files else np.zeros(len(self.mag), np.float32)
        self.spect = npz["spect"] if "spect" in npz.files else np.full(len(self.mag), "", "U12")
        self.colors = _bv_to_rgb(self.ci)                        # (N,3)

        self.deep_xyz = None
        self.load_deep(data_dir)

        names = json.loads((data_dir / "star_names.json").read_text("utf-8"))
        self.proper: dict[int, str] = {i: n for i, n in names["proper"]}
        self.bayer: dict[int, str] = {i: n for i, n in names["bayer"]}
        self.flam: dict[int, str] = {i: n for i, n in names["flam"]}
        self.con: dict[int, str] = {i: n for i, n in names["con"]}
        # Índices já vêm em ordem de magnitude: os primeiros são os mais brilhantes.
        self.proper_idx = np.array(sorted(self.proper), dtype=np.int64)
        self.bayer_idx = np.array(sorted(self.bayer), dtype=np.int64)

    def load_deep(self, data_dir: Path) -> bool:
        """Carrega o catálogo profundo (Tycho-2 via ATHYG), se presente.

        São estrelas fracas sem nomes, usadas apenas quando o zoom permite
        magnitudes além do alcance do HYG.
        """
        path = data_dir / "stars_deep.npz"
        if not path.exists():
            self.deep_xyz = None
            return False
        npz = np.load(path)
        self.deep_xyz = npz["xyz"].astype(np.float32)
        self.deep_mag = npz["mag"]
        self.deep_colors = _bv_to_rgb(npz["ci"])
        return True

    def deep_count_brighter_than(self, mag_limit: float) -> int:
        """Prefixo do catálogo profundo até a magnitude dada (0 sem ele)."""
        if getattr(self, "deep_xyz", None) is None:
            return 0
        return int(np.searchsorted(self.deep_mag, mag_limit, side="right"))

    def __len__(self) -> int:
        return len(self.mag)

    def count_brighter_than(self, mag_limit: float) -> int:
        """Quantas estrelas têm magnitude < limite (é um prefixo do array)."""
        return int(np.searchsorted(self.mag, mag_limit, side="right"))

    def label(self, idx: int, mode: str = "proper") -> str | None:
        """Rótulo da estrela para o mapa.

        mode 'proper': nome próprio (Sirius); cai para Bayer se não houver.
        mode 'bayer': designação de Bayer genitiva abreviada (α CMa).
        """
        con = self.con.get(idx)
        if mode == "proper":
            name = self.proper.get(idx)
            if name:
                return name
            code = self.bayer.get(idx)
            return bayer_display(code, con) if code else None
        code = self.bayer.get(idx)
        if code:
            return bayer_display(code, con)
        return self.proper.get(idx)

    def full_designation(self, idx: int) -> str:
        """Todas as designações da estrela numa linha (painel de informações):
        nome próprio, Bayer por extenso, Flamsteed e número HIP."""
        parts = []
        if idx in self.proper:
            parts.append(self.proper[idx])
        if idx in self.bayer:
            parts.append(bayer_display(self.bayer[idx], self.con.get(idx), full=True))
        if idx in self.flam and idx in self.con:
            parts.append(f"{self.flam[idx]} {GENITIVE.get(self.con[idx], '')}")
        if self.hip[idx]:
            parts.append(f"HIP {int(self.hip[idx])}")
        return " · ".join(parts) if parts else f"Estrela mag {self.mag[idx]:.1f}"
