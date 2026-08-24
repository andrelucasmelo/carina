"""Configuração, caminhos e preferências persistentes do aplicativo."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_dir, user_data_dir
from PySide6.QtCore import QSettings

APP_NAME = "Carina"
ORG_NAME = "Carina"


def package_data_dir() -> Path:
    """Diretório dos dados processados que acompanham o aplicativo.

    Em desenvolvimento é ``<repo>/data/processed``; num build PyInstaller os
    dados são incluídos ao lado do executável (sys._MEIPASS).
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "data" / "processed"
    return Path(__file__).resolve().parents[2] / "data" / "processed"


def user_data_path() -> Path:
    p = Path(user_data_dir(APP_NAME, ORG_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_cache_path() -> Path:
    p = Path(user_cache_dir(APP_NAME, ORG_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class ObserverLocation:
    name: str = "Rio de Janeiro, Brasil"
    latitude: float = -22.9068   # graus, sul negativo
    longitude: float = -43.1729  # graus, oeste negativo
    elevation: float = 15.0      # metros


class Settings:
    """Envelope fino sobre QSettings com valores tipados e padrões."""

    def __init__(self) -> None:
        self._s = QSettings(ORG_NAME, APP_NAME)

    # --- localização do observador -------------------------------------
    def location(self) -> ObserverLocation:
        return ObserverLocation(
            name=self._s.value("observer/name", ObserverLocation.name, str),
            latitude=self._s.value("observer/lat", ObserverLocation.latitude, float),
            longitude=self._s.value("observer/lon", ObserverLocation.longitude, float),
            elevation=self._s.value("observer/elev", ObserverLocation.elevation, float),
        )

    def set_location(self, loc: ObserverLocation) -> None:
        self._s.setValue("observer/name", loc.name)
        self._s.setValue("observer/lat", loc.latitude)
        self._s.setValue("observer/lon", loc.longitude)
        self._s.setValue("observer/elev", loc.elevation)

    # --- camadas visíveis ----------------------------------------------
    def layer(self, key: str, default: bool = True) -> bool:
        return self._s.value(f"layers/{key}", default, bool)

    def set_layer(self, key: str, value: bool) -> None:
        self._s.setValue(f"layers/{key}", value)

    # --- genérico --------------------------------------------------------
    def value(self, key: str, default, type_):
        return self._s.value(key, default, type_)

    def set_value(self, key: str, value) -> None:
        self._s.setValue(key, value)
