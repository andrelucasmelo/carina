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


def package_ephemeris_dir() -> Path:
    """Diretório da efeméride embarcada no build (ADR-012)."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "data" / "ephemeris"
    return Path(__file__).resolve().parents[2] / "data" / "ephemeris"


def ephemeris_dir() -> Path:
    """Onde carregar a efeméride: a embarcada se existir; senão o diretório do
    usuário (com download automático pelo Skyfield como contingência)."""
    from .core.engine import EPHEMERIS

    bundled = package_ephemeris_dir()
    if (bundled / EPHEMERIS).exists():
        return bundled
    return user_data_path()


def app_icon_path() -> Path | None:
    """Ícone do aplicativo (logotipo do Astronomia no Quintal).

    Procura primeiro o ``.ico`` multi-resolução — o formato que o Windows
    usa na barra de tarefas e no Explorer — e cai no PNG quando ele não
    existe. Devolve ``None`` se nenhum estiver presente, para o aplicativo
    seguir com o ícone padrão do sistema em vez de falhar.
    """
    base = package_data_dir()
    for name in ("icon.ico", "icon.png"):
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def user_data_path() -> Path:
    """Pasta de dados do usuário (banco DSO editável, equipamentos…)."""
    p = Path(user_data_dir(APP_NAME, ORG_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_cache_path() -> Path:
    """Cache permanente do usuário (imagens baixadas em uso)."""
    p = Path(user_cache_dir(APP_NAME, ORG_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class ObserverLocation:
    """Onde o observador está: nome de exibição, coordenadas geográficas,
    elevação e o fuso horário IANA usado em todos os horários da UI."""

    name: str = "Rio de Janeiro, Brasil"
    latitude: float = -22.9068   # graus, sul negativo
    longitude: float = -43.1729  # graus, oeste negativo
    elevation: float = 15.0      # metros
    timezone: str = "America/Sao_Paulo"  # fuso IANA; vazio = fuso do sistema


class Settings:
    """Envelope fino sobre QSettings com valores tipados e padrões."""

    def __init__(self) -> None:
        self._s = QSettings(ORG_NAME, APP_NAME)

    # --- localização do observador -------------------------------------
    def location(self) -> ObserverLocation:
        """Localização persistida (ou o padrão, Rio de Janeiro)."""
        return ObserverLocation(
            name=self._s.value("observer/name", ObserverLocation.name, str),
            latitude=self._s.value("observer/lat", ObserverLocation.latitude, float),
            longitude=self._s.value("observer/lon", ObserverLocation.longitude, float),
            elevation=self._s.value("observer/elev", ObserverLocation.elevation, float),
            timezone=self._s.value("observer/tz", ObserverLocation.timezone, str),
        )

    def set_location(self, loc: ObserverLocation) -> None:
        self._s.setValue("observer/name", loc.name)
        self._s.setValue("observer/lat", loc.latitude)
        self._s.setValue("observer/lon", loc.longitude)
        self._s.setValue("observer/elev", loc.elevation)
        self._s.setValue("observer/tz", loc.timezone)

    # --- camadas visíveis ----------------------------------------------
    def layer(self, key: str, default: bool = True) -> bool:
        """Estado persistido de uma camada de exibição."""
        return self._s.value(f"layers/{key}", default, bool)

    def set_layer(self, key: str, value: bool) -> None:
        """Grava o estado de uma camada (grupo ``layers/`` do QSettings)."""
        self._s.setValue(f"layers/{key}", value)

    # --- genérico --------------------------------------------------------
    def value(self, key: str, default, type_):
        """Leitura tipada genérica (QSettings devolve strings sem o tipo)."""
        return self._s.value(key, default, type_)

    def set_value(self, key: str, value) -> None:
        """Gravação genérica de uma preferência."""
        self._s.setValue(key, value)
