"""Imagens dos objetos de céu profundo (item 8) — política ADR-004/ADR-012.

Ordem de resolução:
  1. imagens embarcadas no pacote (Messier/Caldwell, pré-baixadas no build);
  2. cache local do usuário;
  3. download em segundo plano do hips2fits (DSS2 color) para o cache — a
     partir daí o objeto funciona offline.
"""

from __future__ import annotations

import math
import threading
import urllib.parse
from pathlib import Path

from ..config import package_data_dir, user_cache_path

# Mirror primeiro: o servidor principal (alasky.cds) costuma estrangular.
HIPS2FITS_SERVERS = [
    "https://alaskybis.unistra.fr/hips-image-services/hips2fits",
    "https://alasky.cds.unistra.fr/hips-image-services/hips2fits",
]
SURVEY = "CDS/P/DSS2/color"

_inflight: set[str] = set()
_lock = threading.Lock()


def image_filename(name: str) -> str:
    return name.replace(" ", "").replace("/", "_") + ".jpg"


def _bundled_dir() -> Path:
    return package_data_dir() / "images"


def _cache_dir() -> Path:
    p = user_cache_path() / "images"
    p.mkdir(parents=True, exist_ok=True)
    return p


def image_path_for(name: str) -> Path | None:
    """Caminho local da imagem, se já existir (pacote ou cache)."""
    fn = image_filename(name)
    for base in (_bundled_dir(), _cache_dir()):
        p = base / fn
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def _fov_for(maj_arcmin: float | None) -> float:
    if not maj_arcmin:
        return 0.5
    return min(6.0, max(0.25, maj_arcmin * 2.5 / 60.0))


def request_image(name: str, ra_rad: float, dec_rad: float,
                  maj_arcmin: float | None) -> None:
    """Dispara o download em segundo plano (uma vez por objeto por sessão).

    O painel de informações se atualiza a cada segundo e captura o arquivo
    assim que ele aparece no cache.
    """
    fn = image_filename(name)
    with _lock:
        if fn in _inflight:
            return
        _inflight.add(fn)

    def worker() -> None:
        try:
            import requests

            params = {
                "hips": SURVEY,
                "ra": f"{math.degrees(ra_rad):.6f}",
                "dec": f"{math.degrees(dec_rad):.6f}",
                "fov": f"{_fov_for(maj_arcmin):.4f}",
                "width": "512", "height": "512",
                "projection": "TAN", "format": "jpg",
            }
            content = None
            for server in HIPS2FITS_SERVERS:
                try:
                    url = f"{server}?{urllib.parse.urlencode(params)}"
                    resp = requests.get(url, timeout=45)
                    resp.raise_for_status()
                    content = resp.content
                    break
                except Exception:
                    continue
            if content is None:
                raise RuntimeError("hips2fits indisponível")
            tmp = _cache_dir() / (fn + ".part")
            tmp.write_bytes(content)
            tmp.replace(_cache_dir() / fn)
        except Exception:
            with _lock:
                _inflight.discard(fn)  # permite tentar de novo depois

    threading.Thread(target=worker, daemon=True).start()
