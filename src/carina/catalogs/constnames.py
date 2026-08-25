"""Nomes das 88 constelações: abreviação IAU, latim e português.

Usado para rotular as constelações no mapa em três formas (item 5 do pedido
do usuário): português, latim (nome oficial) ou abreviação de três letras.
"""

from __future__ import annotations

# abreviação IAU -> (latim, português)
CONSTELLATIONS: dict[str, tuple[str, str]] = {
    "And": ("Andromeda", "Andrômeda"),
    "Ant": ("Antlia", "Máquina Pneumática"),
    "Aps": ("Apus", "Ave-do-Paraíso"),
    "Aqr": ("Aquarius", "Aquário"),
    "Aql": ("Aquila", "Águia"),
    "Ara": ("Ara", "Altar"),
    "Ari": ("Aries", "Áries"),
    "Aur": ("Auriga", "Cocheiro"),
    "Boo": ("Boötes", "Boieiro"),
    "Cae": ("Caelum", "Buril"),
    "Cam": ("Camelopardalis", "Girafa"),
    "Cnc": ("Cancer", "Câncer"),
    "CVn": ("Canes Venatici", "Cães de Caça"),
    "CMa": ("Canis Major", "Cão Maior"),
    "CMi": ("Canis Minor", "Cão Menor"),
    "Cap": ("Capricornus", "Capricórnio"),
    "Car": ("Carina", "Quilha"),
    "Cas": ("Cassiopeia", "Cassiopeia"),
    "Cen": ("Centaurus", "Centauro"),
    "Cep": ("Cepheus", "Cefeu"),
    "Cet": ("Cetus", "Baleia"),
    "Cha": ("Chamaeleon", "Camaleão"),
    "Cir": ("Circinus", "Compasso"),
    "Col": ("Columba", "Pomba"),
    "Com": ("Coma Berenices", "Cabeleira de Berenice"),
    "CrA": ("Corona Australis", "Coroa Austral"),
    "CrB": ("Corona Borealis", "Coroa Boreal"),
    "Crv": ("Corvus", "Corvo"),
    "Crt": ("Crater", "Taça"),
    "Cru": ("Crux", "Cruzeiro do Sul"),
    "Cyg": ("Cygnus", "Cisne"),
    "Del": ("Delphinus", "Golfinho"),
    "Dor": ("Dorado", "Dourado"),
    "Dra": ("Draco", "Dragão"),
    "Equ": ("Equuleus", "Cavalo Menor"),
    "Eri": ("Eridanus", "Eridano"),
    "For": ("Fornax", "Fornalha"),
    "Gem": ("Gemini", "Gêmeos"),
    "Gru": ("Grus", "Grou"),
    "Her": ("Hercules", "Hércules"),
    "Hor": ("Horologium", "Relógio"),
    "Hya": ("Hydra", "Hidra Fêmea"),
    "Hyi": ("Hydrus", "Hidra Macho"),
    "Ind": ("Indus", "Índio"),
    "Lac": ("Lacerta", "Lagarto"),
    "Leo": ("Leo", "Leão"),
    "LMi": ("Leo Minor", "Leão Menor"),
    "Lep": ("Lepus", "Lebre"),
    "Lib": ("Libra", "Libra"),
    "Lup": ("Lupus", "Lobo"),
    "Lyn": ("Lynx", "Lince"),
    "Lyr": ("Lyra", "Lira"),
    "Men": ("Mensa", "Mesa"),
    "Mic": ("Microscopium", "Microscópio"),
    "Mon": ("Monoceros", "Unicórnio"),
    "Mus": ("Musca", "Mosca"),
    "Nor": ("Norma", "Esquadro"),
    "Oct": ("Octans", "Oitante"),
    "Oph": ("Ophiuchus", "Serpentário"),
    "Ori": ("Orion", "Órion"),
    "Pav": ("Pavo", "Pavão"),
    "Peg": ("Pegasus", "Pégaso"),
    "Per": ("Perseus", "Perseu"),
    "Phe": ("Phoenix", "Fênix"),
    "Pic": ("Pictor", "Cavalete do Pintor"),
    "Psc": ("Pisces", "Peixes"),
    "PsA": ("Piscis Austrinus", "Peixe Austral"),
    "Pup": ("Puppis", "Popa"),
    "Pyx": ("Pyxis", "Bússola"),
    "Ret": ("Reticulum", "Retículo"),
    "Sge": ("Sagitta", "Flecha"),
    "Sgr": ("Sagittarius", "Sagitário"),
    "Sco": ("Scorpius", "Escorpião"),
    "Scl": ("Sculptor", "Escultor"),
    "Sct": ("Scutum", "Escudo"),
    "Ser": ("Serpens", "Serpente"),
    "Sex": ("Sextans", "Sextante"),
    "Tau": ("Taurus", "Touro"),
    "Tel": ("Telescopium", "Telescópio"),
    "Tri": ("Triangulum", "Triângulo"),
    "TrA": ("Triangulum Australe", "Triângulo Austral"),
    "Tuc": ("Tucana", "Tucano"),
    "UMa": ("Ursa Major", "Ursa Maior"),
    "UMi": ("Ursa Minor", "Ursa Menor"),
    "Vel": ("Vela", "Velas"),
    "Vir": ("Virgo", "Virgem"),
    "Vol": ("Volans", "Peixe Voador"),
    "Vul": ("Vulpecula", "Raposa"),
}


def label_for(abbr: str, mode: str, latin_fallback: str = "") -> str:
    """Rótulo da constelação no modo pedido: 'pt', 'latin' ou 'abbr'."""
    entry = CONSTELLATIONS.get(abbr)
    if mode == "abbr":
        return abbr
    if entry is None:
        return latin_fallback or abbr
    return entry[1] if mode == "pt" else entry[0]
