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
    name: str
    aperture_mm: float
    focal_mm: float
    kind: str = "telescopio"   # telescopio | lente

    @property
    def ratio(self) -> float:
        return self.focal_mm / self.aperture_mm if self.aperture_mm else 0.0


@dataclass
class Camera:
    name: str
    width_mm: float
    height_mm: float
    pixel_um: float = 0.0
    width_px: int = 0
    height_px: int = 0


@dataclass
class Eyepiece:
    name: str
    focal_mm: float
    afov_deg: float = 52.0


@dataclass
class Accessory:
    name: str
    factor: float = 1.0        # 2.0 = barlow 2x; 0.63 = redutor


@dataclass
class Mount:
    name: str
    kind: str = "equatorial"   # equatorial | altazimute
    payload_kg: float = 0.0


@dataclass
class FovShape:
    """Resultado do cálculo: geometria a desenhar no céu."""

    kind: str                  # 'rect' | 'circle'
    width: float               # radianos (ou diâmetro, se círculo)
    height: float              # radianos
    label: str
    details: list[tuple[str, str]] = field(default_factory=list)


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
        {"name": "Barlow 2×", "factor": 2.0},
        {"name": "Barlow 3×", "factor": 3.0},
        {"name": "Redutor 0,8×", "factor": 0.8},
        {"name": "Redutor 0,63×", "factor": 0.63},
        {"name": "Flattener 1,0×", "factor": 1.0},
    ],
    "mounts": [
        {"name": "Equatorial EQ3", "kind": "equatorial", "payload_kg": 5.0},
        {"name": "Equatorial EQ5/HEQ5", "kind": "equatorial", "payload_kg": 11.0},
        {"name": "Equatorial EQ6", "kind": "equatorial", "payload_kg": 18.0},
        {"name": "Star Adventurer", "kind": "equatorial", "payload_kg": 5.0},
        {"name": "Altazimutal Dobson", "kind": "altazimute", "payload_kg": 15.0},
        {"name": "Tripé fotográfico", "kind": "altazimute", "payload_kg": 3.0},
    ],
}

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
        raw = DEFAULT_DATA
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                raw = DEFAULT_DATA
        self.data = {
            key: [cls(**item) for item in raw.get(key, [])]
            for key, cls in _SECTIONS.items()
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: [asdict(item) for item in items]
            for key, items in self.data.items()
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def restore_defaults(self) -> None:
        self.data = {
            key: [cls(**item) for item in DEFAULT_DATA[key]]
            for key, cls in _SECTIONS.items()
        }
        self.save()

    # ------------------------------------------------------------------
    def items(self, section: str) -> list:
        return self.data.get(section, [])

    def find(self, section: str, name: str):
        for item in self.items(section):
            if item.name == name:
                return item
        return None

    def add(self, section: str, item) -> None:
        self.data.setdefault(section, []).append(item)
        self.save()

    def replace(self, section: str, index: int, item) -> None:
        self.data[section][index] = item
        self.save()

    def remove(self, section: str, index: int) -> None:
        del self.data[section][index]
        self.save()


# ---------------------------------------------------------------------------
# Cálculo do campo
# ---------------------------------------------------------------------------

def compute_camera_fov(scope: Telescope, camera: Camera,
                       accessory: Accessory | None = None) -> FovShape:
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
