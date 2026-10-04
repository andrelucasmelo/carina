"""Equipamentos astronômicos e cálculo de campo de visão (item 7).

Modelo: telescópios/lentes, câmeras (sensor), oculares e acessórios
(redutores, barlows, flatteners) + montagens. Um "setup" combina um
telescópio, um acessório opcional e uma câmera OU uma ocular, produzindo o
retângulo/círculo de campo desenhado sobre o céu.

Fórmulas:
  f_efetiva = f_telescópio × fator_do_acessório
  Câmera:  FOV_eixo = 2·atan(dimensão_sensor / (2·f_efetiva))
           escala de placa = 206,265 × tamanho_pixel_µm / f_efetiva  ["/px]
  Ocular:  ampliação = f_efetiva / f_ocular
           FOV_real  = campo_aparente / ampliação
           pupila de saída = abertura / ampliação
Os dados ficam num JSON no diretório do usuário (editável pela interface).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

ARCSEC_PER_RAD = 206264.806


@dataclass
class Telescope:
    """Telescópio ou lente fotográfica: abertura e distância focal."""

    name: str
    aperture_mm: float
    focal_mm: float
    kind: str = "telescopio"   # telescopio | lente

    @property
    def ratio(self) -> float:
        """Razão focal (f/D) — o "f/5" das conversas de astrofotografia."""
        return self.focal_mm / self.aperture_mm if self.aperture_mm else 0.0


@dataclass
class Camera:
    """Câmera: o sensor define o campo (mm) e a escala de pixel (µm)."""

    name: str
    width_mm: float
    height_mm: float
    pixel_um: float = 0.0
    width_px: int = 0
    height_px: int = 0


@dataclass
class Eyepiece:
    """Ocular: focal própria + campo aparente (52° é o Plössl clássico)."""

    name: str
    focal_mm: float
    afov_deg: float = 52.0


@dataclass
class Accessory:
    """Barlow/redutor: multiplica a focal efetiva pelo ``factor``."""

    name: str
    factor: float = 1.0        # 2.0 = barlow 2x; 0.63 = redutor


@dataclass
class Mount:
    """Montagem — não entra no cálculo de campo, mas compõe o setup."""

    name: str
    kind: str = "equatorial"   # ver MOUNT_KINDS
    payload_kg: float = 0.0


# tipos de montagem: chave gravada no JSON → rótulo
MOUNT_KINDS = {
    "equatorial": "Equatorial alemã (vira no meridiano)",
    "altazimute": "Altazimutal",
    "smart-altaz": "Telescópio inteligente — modo Alt-Az",
    "smart-eq": "Telescópio inteligente — modo EQ (cunha)",
}


def mount_is_altaz(kind: str) -> bool:
    return kind in ("altazimute", "smart-altaz")


def mount_flips(kind: str) -> bool:
    """Só a equatorial alemã precisa virar no meridiano."""
    return kind == "equatorial"


@dataclass
class FovShape:
    """Resultado do cálculo: geometria a desenhar no céu."""

    kind: str                  # 'rect' | 'circle'
    width: float               # radianos (ou diâmetro, se círculo)
    height: float              # radianos
    label: str
    details: list[tuple[str, str]] = field(default_factory=list)
    offset: tuple[float, float] = (0.0, 0.0)   # painel de mosaico (rad, no plano do campo)
    orientation: str = ""      # ocular: direta | invertida | espelhada (v0.19)


DEFAULT_DATA = {
    "telescopes": [
        {"name": "Newtoniano 150/750", "aperture_mm": 150, "focal_mm": 750},
        {"name": "Newtoniano 200/1000", "aperture_mm": 200, "focal_mm": 1000},
        {"name": "Maksutov 127/1500", "aperture_mm": 127, "focal_mm": 1500},
        {"name": "Schmidt-Cassegrain 8\" (203/2032)", "aperture_mm": 203,
         "focal_mm": 2032},
        {"name": "Refrator ED 80/600", "aperture_mm": 80, "focal_mm": 600},
        {"name": "Refrator 70/700", "aperture_mm": 70, "focal_mm": 700},
        {"name": "RedCat 51/250", "aperture_mm": 51, "focal_mm": 250},
        # --- telescópios inteligentes (conjunto fechado: use a câmera
        #     homônima na lista de câmeras) ---
        {"name": "Seestar S50 (50/250)", "aperture_mm": 50, "focal_mm": 250},
        {"name": "Seestar S30 (30/150)", "aperture_mm": 30, "focal_mm": 150},
        {"name": "Seestar S30 Pro (30/150)", "aperture_mm": 30,
         "focal_mm": 150},
        # --- outros modelos populares ---
        {"name": "Evostar 72ED (72/420)", "aperture_mm": 72, "focal_mm": 420},
        {"name": "Askar FRA400 (72/400)", "aperture_mm": 72, "focal_mm": 400},
        {"name": "Esprit 100ED (100/550)", "aperture_mm": 100,
         "focal_mm": 550},
        {"name": "Newtoniano 130/650", "aperture_mm": 130, "focal_mm": 650},
        {"name": "Celestron C6 (150/1500)", "aperture_mm": 150,
         "focal_mm": 1500},
        {"name": "C9.25 (235/2350)", "aperture_mm": 235, "focal_mm": 2350},
        {"name": "C11 (280/2800)", "aperture_mm": 280, "focal_mm": 2800},
        {"name": "RASA 8 (203/400)", "aperture_mm": 203, "focal_mm": 400},
        {"name": "Dobson 8\" (203/1200)", "aperture_mm": 203,
         "focal_mm": 1200},
        {"name": "Dobson 10\" (254/1250)", "aperture_mm": 254,
         "focal_mm": 1250},
        {"name": "Dobson 12\" (305/1500)", "aperture_mm": 305,
         "focal_mm": 1500},
        {"name": "Teleobjetiva 200 mm f/2.8", "aperture_mm": 71.4,
         "focal_mm": 200, "kind": "lente"},
        {"name": "Objetiva 50 mm f/1.8", "aperture_mm": 27.8,
         "focal_mm": 50, "kind": "lente"},
        {"name": "Grande-angular 24 mm f/2.8", "aperture_mm": 8.6,
         "focal_mm": 24, "kind": "lente"},
    ],
    "cameras": [
        {"name": "ZWO ASI533MC (1\")", "width_mm": 11.31, "height_mm": 11.31,
         "pixel_um": 3.76, "width_px": 3008, "height_px": 3008},
        {"name": "ZWO ASI294MC (4/3\")", "width_mm": 19.1, "height_mm": 13.0,
         "pixel_um": 4.63, "width_px": 4144, "height_px": 2822},
        {"name": "ZWO ASI2600MC (APS-C)", "width_mm": 23.5, "height_mm": 15.7,
         "pixel_um": 3.76, "width_px": 6248, "height_px": 4176},
        {"name": "ZWO ASI183MC (1\")", "width_mm": 13.2, "height_mm": 8.8,
         "pixel_um": 2.4, "width_px": 5496, "height_px": 3672},
        {"name": "ZWO ASI120MC (1/3\")", "width_mm": 4.8, "height_mm": 3.6,
         "pixel_um": 3.75, "width_px": 1280, "height_px": 960},
        {"name": "DSLR APS-C (Canon)", "width_mm": 22.3, "height_mm": 14.9,
         "pixel_um": 3.72, "width_px": 6000, "height_px": 4000},
        {"name": "DSLR full-frame", "width_mm": 36.0, "height_mm": 24.0,
         "pixel_um": 5.94, "width_px": 6060, "height_px": 4040},
        {"name": "Micro 4/3", "width_mm": 17.3, "height_mm": 13.0,
         "pixel_um": 3.3, "width_px": 5240, "height_px": 3912},
        # --- sensores dos telescópios inteligentes ---
        {"name": "Seestar S50 — IMX462", "width_mm": 5.57, "height_mm": 3.13,
         "pixel_um": 2.9, "width_px": 1920, "height_px": 1080},
        {"name": "Seestar S30 — IMX662", "width_mm": 5.57, "height_mm": 3.13,
         "pixel_um": 2.9, "width_px": 1920, "height_px": 1080},
        {"name": "Seestar S30 Pro — IMX585", "width_mm": 11.14,
         "height_mm": 6.26, "pixel_um": 2.9, "width_px": 3840,
         "height_px": 2160},
        # --- câmeras planetárias e de céu profundo populares ---
        {"name": "ZWO ASI224MC (1/3\")", "width_mm": 4.9, "height_mm": 3.7,
         "pixel_um": 3.75, "width_px": 1304, "height_px": 976},
        {"name": "ZWO ASI662MC (1/2.8\")", "width_mm": 5.57,
         "height_mm": 3.13, "pixel_um": 2.9, "width_px": 1920,
         "height_px": 1080},
        {"name": "ZWO ASI585MC (1/1.2\")", "width_mm": 11.14,
         "height_mm": 6.26, "pixel_um": 2.9, "width_px": 3840,
         "height_px": 2160},
        {"name": "ZWO ASI174MM (1/1.2\")", "width_mm": 11.34,
         "height_mm": 7.13, "pixel_um": 5.86, "width_px": 1936,
         "height_px": 1216},
        {"name": "ZWO ASI6200MC (full-frame)", "width_mm": 36.0,
         "height_mm": 24.0, "pixel_um": 3.76, "width_px": 9576,
         "height_px": 6388},
    ],
    "eyepieces": [
        {"name": "Plössl 32 mm (52°)", "focal_mm": 32, "afov_deg": 52},
        {"name": "Plössl 25 mm (52°)", "focal_mm": 25, "afov_deg": 52},
        {"name": "Plössl 10 mm (52°)", "focal_mm": 10, "afov_deg": 52},
        {"name": "Grande campo 14 mm (82°)", "focal_mm": 14, "afov_deg": 82},
        {"name": "Grande campo 9 mm (66°)", "focal_mm": 9, "afov_deg": 66},
        {"name": "Ortoscópica 6 mm (45°)", "focal_mm": 6, "afov_deg": 45},
    ],
    "accessories": [
        {"name": "(nenhum)", "factor": 1.0},
        {"name": "Barlow 1,5×", "factor": 1.5},
        {"name": "Barlow 2×", "factor": 2.0},
        {"name": "Barlow 2,5×", "factor": 2.5},
        {"name": "Barlow 3×", "factor": 3.0},
        {"name": "Powermate 4×", "factor": 4.0},
        {"name": "Redutor 0,8×", "factor": 0.8},
        {"name": "Redutor 0,7× (EdgeHD)", "factor": 0.7},
        {"name": "Redutor 0,63× (SCT)", "factor": 0.63},
        {"name": "Redutor 0,5×", "factor": 0.5},
        {"name": "Flattener 1,0×", "factor": 1.0},
        # não altera a focal: a rotação é ajustada no controle "Rotação
        # do campo (rotacionador)" da aba de enquadramento
        {"name": "Rotacionador de campo (1,0×)", "factor": 1.0},
    ],
    "mounts": [
        {"name": "Equatorial EQ3", "kind": "equatorial", "payload_kg": 5.0},
        {"name": "Equatorial EQ5/HEQ5", "kind": "equatorial", "payload_kg": 11.0},
        {"name": "Equatorial EQ6/EQ6-R", "kind": "equatorial", "payload_kg": 20.0},
        {"name": "ZWO AM5 (harmônica)", "kind": "equatorial", "payload_kg": 13.0},
        {"name": "iOptron CEM40", "kind": "equatorial", "payload_kg": 18.0},
        {"name": "Star Adventurer", "kind": "equatorial", "payload_kg": 5.0},
        {"name": "AZ-GTi", "kind": "altazimute", "payload_kg": 5.0},
        {"name": "Altazimutal Dobson", "kind": "altazimute", "payload_kg": 15.0},
        {"name": "Tripé fotográfico", "kind": "altazimute", "payload_kg": 3.0},
        {"name": "Telescópio inteligente (Alt-Az)", "kind": "smart-altaz",
         "payload_kg": 0.0},
        {"name": "Telescópio inteligente (EQ, cunha)", "kind": "smart-eq",
         "payload_kg": 0.0},
    ],
}

# Versão do acervo padrão: ao subir, os itens NOVOS dos padrões são
# mesclados no JSON de quem já usava o aplicativo (sem duplicar por nome e
# sem ressuscitar itens que o usuário apagou de versões anteriores — a
# mescla acontece uma única vez por versão).
DATA_VERSION = 3

_SECTIONS = {
    "telescopes": Telescope, "cameras": Camera, "eyepieces": Eyepiece,
    "accessories": Accessory, "mounts": Mount,
}


class EquipmentStore:
    """Persistência dos equipamentos do usuário (JSON) e cálculo de campo."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, list] = {}
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Carrega o JSON do usuário; arquivo ausente/corrompido → padrões.

        Se o arquivo veio de uma versão anterior do acervo padrão, os
        equipamentos ADICIONADOS desde então (Seestars, novas câmeras…)
        são mesclados uma única vez, preservando tudo que o usuário criou
        ou apagou.
        """
        raw = DEFAULT_DATA
        from_user = False
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                from_user = True
            except (json.JSONDecodeError, OSError):
                raw = DEFAULT_DATA
        self.data = {
            key: [cls(**item) for item in raw.get(key, [])]
            for key, cls in _SECTIONS.items()
        }
        if from_user and int(raw.get("version", 1)) < DATA_VERSION:
            self._merge_new_defaults()
            self.save()

    def _merge_new_defaults(self) -> None:
        """Acrescenta os itens dos padrões que o usuário ainda não tem."""
        for key, cls in _SECTIONS.items():
            have = {item.name for item in self.data.get(key, [])}
            for spec in DEFAULT_DATA[key]:
                if spec["name"] not in have:
                    self.data.setdefault(key, []).append(cls(**spec))

    def save(self) -> None:
        """Grava tudo de volta (chamado após cada mutação)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: [asdict(item) for item in items]
            for key, items in self.data.items()
        }
        payload["version"] = DATA_VERSION
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def restore_defaults(self) -> None:
        """Descarta o acervo do usuário e volta ao kit de fábrica."""
        self.data = {
            key: [cls(**item) for item in DEFAULT_DATA[key]]
            for key, cls in _SECTIONS.items()
        }
        self.save()

    # ------------------------------------------------------------------
    def items(self, section: str) -> list:
        """Itens de uma seção ('telescopes', 'cameras', 'eyepieces'…)."""
        return self.data.get(section, [])

    def find(self, section: str, name: str):
        """Primeiro item da seção com o nome exato, ou None."""
        for item in self.items(section):
            if item.name == name:
                return item
        return None

    def add(self, section: str, item) -> None:
        """Acrescenta um equipamento e persiste."""
        self.data.setdefault(section, []).append(item)
        self.save()

    def replace(self, section: str, index: int, item) -> None:
        """Substitui o item na posição (edição pela lista) e persiste."""
        self.data[section][index] = item
        self.save()

    def remove(self, section: str, index: int) -> None:
        """Remove o item na posição e persiste."""
        del self.data[section][index]
        self.save()


# ---------------------------------------------------------------------------
# Cálculo do campo
# ---------------------------------------------------------------------------

def compute_camera_fov(scope: Telescope, camera: Camera,
                       accessory: Accessory | None = None) -> FovShape:
    """Campo retangular de telescópio + câmera (astrofotografia).

    Campo = 2·atan(sensor/2f); a ficha traz também a escala de placa
    (″/px) e um veredito de amostragem — o número que decide se o conjunto
    resolve o seeing típico (~2″) ou desperdiça pixels.
    """
    focal = scope.focal_mm * (accessory.factor if accessory else 1.0)
    w = 2.0 * math.atan(camera.width_mm / (2.0 * focal))
    h = 2.0 * math.atan(camera.height_mm / (2.0 * focal))
    details = [
        ("Focal efetiva", f"{focal:.0f} mm  (f/{focal / scope.aperture_mm:.1f})"),
        ("Campo", f"{math.degrees(w):.2f}° × {math.degrees(h):.2f}°"),
    ]
    if camera.pixel_um:
        scale = ARCSEC_PER_RAD * (camera.pixel_um / 1000.0) / focal
        details.append(("Escala de placa", f"{scale:.2f}″/px"))
        if scale > 0:
            details.append(
                ("Amostragem",
                 "subamostrado" if scale > 2.0
                 else ("adequada" if scale >= 1.0 else "superamostrado"))
            )
    if camera.width_px and camera.height_px:
        details.append(
            ("Resolução", f"{camera.width_px} × {camera.height_px} px")
        )
    label = f"{scope.name} + {camera.name}"
    if accessory and accessory.factor != 1.0:
        label += f" + {accessory.name}"
    return FovShape("rect", w, h, label, details)


def compute_eyepiece_fov(scope: Telescope, eyepiece: Eyepiece,
                         accessory: Accessory | None = None) -> FovShape:
    """Campo circular de telescópio + ocular (observação visual).

    Ampliação = focal do telescópio / focal da ocular; campo real ≈ campo
    aparente / ampliação. A pupila de saída (D/ampliação) diz se a imagem
    fica escura demais (< 0,5 mm) ou desperdiça abertura (> 7 mm).
    """
    focal = scope.focal_mm * (accessory.factor if accessory else 1.0)
    mag = focal / eyepiece.focal_mm if eyepiece.focal_mm else 0.0
    fov = math.radians(eyepiece.afov_deg / mag) if mag else 0.0
    exit_pupil = scope.aperture_mm / mag if mag else 0.0
    details = [
        ("Ampliação", f"{mag:.0f}×"),
        ("Campo real", f"{math.degrees(fov):.2f}°"),
        ("Pupila de saída", f"{exit_pupil:.1f} mm"),
        ("Focal efetiva", f"{focal:.0f} mm"),
    ]
    # magnitude-limite aproximada (céu escuro): 7,5 + 5·log10(D_cm)
    if scope.aperture_mm:
        mag_lim = 7.5 + 5.0 * math.log10(scope.aperture_mm / 10.0)
        details.append(("Mag. limite (estimada)", f"{mag_lim:.1f}"))
    label = f"{scope.name} + {eyepiece.name}"
    if accessory and accessory.factor != 1.0:
        label += f" + {accessory.name}"
    return FovShape("circle", fov, fov, label, details)


# ---------------------------------------------------------------------------
# v0.19: setups salvos, mosaico, "cabe no campo?" e trem óptico
# ---------------------------------------------------------------------------

@dataclass
class Setup:
    """Conjunto com nome ("Seestar no quintal", "80ED + 533"): guardado no
    ``carina.sqlite`` como perfil ``kind='setup'``."""

    name: str
    telescope: str = ""
    camera: str = ""
    eyepiece: str = ""
    accessory: str = ""
    mount: str = ""
    rotation_deg: float = 0.0
    mosaic_cols: int = 1
    mosaic_rows: int = 1
    overlap: float = 0.15
    train: str = "direta"      # ocular: direta | invertida | espelhada

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Setup":
        fields_ = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (d or {}).items() if k in fields_})

    def mount_kind(self, store: "EquipmentStore") -> str:
        """Tipo da montagem (MOUNT_KINDS); sem montagem, o Seestar é
        inteligente em Alt-Az e o resto, equatorial alemã."""
        m = store.find("mounts", self.mount) if self.mount else None
        if m is not None:
            return m.kind if m.kind in MOUNT_KINDS else "equatorial"
        return "smart-altaz" if "seestar" in self.telescope.lower() else "equatorial"

    def is_altaz(self, store: "EquipmentStore") -> bool:
        return mount_is_altaz(self.mount_kind(store))

    def camera_shape(self, store: "EquipmentStore") -> FovShape | None:
        scope = store.find("telescopes", self.telescope)
        cam = store.find("cameras", self.camera)
        if scope is None or cam is None:
            return None
        return compute_camera_fov(scope, cam, store.find("accessories", self.accessory))

    def shapes(self, store: "EquipmentStore") -> list[FovShape]:
        out = []
        cam = self.camera_shape(store)
        if cam is not None:
            out += mosaic_shapes(cam, self.mosaic_cols, self.mosaic_rows, self.overlap)
        scope = store.find("telescopes", self.telescope)
        eye = store.find("eyepieces", self.eyepiece) if self.eyepiece else None
        if scope is not None and eye is not None:
            shape = compute_eyepiece_fov(scope, eye, store.find("accessories", self.accessory))
            shape.orientation = self.train
            shape.details.append(("Imagem na ocular", TRAIN_LABEL.get(self.train, self.train)))
            out.append(shape)
        return out


TRAIN_LABEL = {
    "direta": "como no céu (binóculo, prisma ereto)",
    "invertida": "girada 180° (refletor ou SCT sem diagonal)",
    "espelhada": "espelhada (refrator ou SCT com diagonal)",
}

SETUP_KIND = "setup"


def save_setup(setup: Setup, data=None) -> None:
    from ..core import userdata

    db = data if data is not None else userdata.get()
    db.save_profile(SETUP_KIND, setup.name, setup.to_dict())


def load_setup(name: str, data=None) -> Setup | None:
    from ..core import userdata

    db = data if data is not None else userdata.get()
    d = db.profile(SETUP_KIND, name)
    return Setup.from_dict(d) if d else None


def setup_names(data=None) -> list[str]:
    from ..core import userdata

    db = data if data is not None else userdata.get()
    return db.profiles(SETUP_KIND)


def delete_setup(name: str, data=None) -> None:
    from ..core import userdata

    db = data if data is not None else userdata.get()
    db.delete_profile(SETUP_KIND, name)


def mosaic_shapes(base: FovShape, cols: int, rows: int,
                  overlap: float = 0.15) -> list[FovShape]:
    """Painéis de um mosaico cols × rows com sobreposição (fração do quadro)."""
    cols, rows = max(1, int(cols)), max(1, int(rows))
    if cols == 1 and rows == 1:
        return [base]
    sw = base.width * (1.0 - overlap)
    sh = base.height * (1.0 - overlap)
    out = []
    for r in range(rows):
        for c in range(cols):
            dx = (c - (cols - 1) / 2.0) * sw
            dy = ((rows - 1) / 2.0 - r) * sh
            label = f"{base.label} — painel {r * cols + c + 1}/{cols * rows}"
            out.append(FovShape(base.kind, base.width, base.height, label,
                                list(base.details) if r == c == 0 else [], (dx, dy)))
    return out


def mosaic_extent(base: FovShape, cols: int, rows: int, overlap: float = 0.15) -> tuple[float, float]:
    """Largura e altura totais (rad) cobertas pelo mosaico."""
    return (base.width + (max(1, cols) - 1) * base.width * (1 - overlap),
            base.height + (max(1, rows) - 1) * base.height * (1 - overlap))


def fit_in_field(maj_arcmin: float, min_arcmin: float | None, shape: FovShape,
                 overlap: float = 0.15) -> dict:
    """O objeto cabe no campo? Considera girar o quadro (eixo maior no lado
    maior). Devolve {"fits", "fill" (fração da área), "mosaic": (c, r)}."""
    maj = math.radians(maj_arcmin / 60.0)
    mnr = math.radians((min_arcmin or maj_arcmin) / 60.0)
    w, h = max(shape.width, shape.height), min(shape.width, shape.height)
    if shape.kind == "circle":
        w = h = shape.width
    margin = 1.1                                      # 10% de folga
    fits = maj * margin <= w and mnr * margin <= h
    fill = (math.pi / 4 * maj * mnr) / (w * h if shape.kind != "circle"
                                          else math.pi / 4 * w * w)
    cols = 1 if maj * margin <= w else math.ceil((maj * margin - w) / (w * (1 - overlap))) + 1
    rows = 1 if mnr * margin <= h else math.ceil((mnr * margin - h) / (h * (1 - overlap))) + 1
    return {"fits": fits, "fill": min(fill, 9.99), "mosaic": (cols, rows)}

