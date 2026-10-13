"""Roda o Carina com preferências e dados ISOLADOS do usuário.

Para capturas de documentação e testes manuais: troca a pasta de dados, a
de cache e o QSettings (formato .ini) por uma pasta descartável ANTES de
importar a janela. Assim nada toca no ``carina.sqlite`` real nem no
registro do Windows — trocar só a variável LOCALAPPDATA não basta, porque o
platformdirs consulta a API do Windows diretamente.

Uso:
    python scripts/run_isolated.py <pasta-isolada> [opções do carina...]

Exemplo (captura do céu de junho, céu escuro, sem a grade):
    python scripts/run_isolated.py %TEMP%/carina-iso --at 2026-06-10T21:00 \\
        --look 120,40 --fov 75 --bortle 1 --disable-layer grid_altaz \\
        --screenshot ceu.png
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    iso = Path(sys.argv[1]).resolve()
    iso.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "src"))

    from PySide6.QtCore import QSettings

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(iso / "ini"))
    import carina.config as cfg

    cfg.user_data_dir = lambda *a, **k: str(iso / "data")
    cfg.user_cache_dir = lambda *a, **k: str(iso / "cache")
    from carina.core import userdata

    userdata.set_instance(userdata.UserData(iso / "carina.sqlite"))
    from carina.__main__ import main as carina_main

    return carina_main(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
