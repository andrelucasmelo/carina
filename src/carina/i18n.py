"""Traduções: as do próprio Qt (botões padrão dos diálogos) e, no futuro,
as do Carina (.qm gerados a partir dos ``tr()`` espalhados pela interface).

Sem o catálogo ``qtbase`` instalado, QDialogButtonBox e companhia mostram
"OK / Cancel / Close / Restore Defaults" em inglês no meio de uma interface
em português — achado D2 da revisão de usabilidade de 2026-10.
"""

from __future__ import annotations

from pathlib import Path


def qt_translations_dir() -> Path:
    """Pasta dos ``.qm`` do Qt que acompanham o PySide6.

    ``QLibraryInfo`` sabe onde está; o fallback (pasta ``translations`` ao
    lado do pacote) cobre builds congelados em que a consulta devolve um
    caminho inexistente.
    """
    from PySide6.QtCore import QLibraryInfo

    path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    if path.is_dir():
        return path
    import PySide6

    return Path(PySide6.__file__).resolve().parent / "translations"


def install_qt_translations(app, locale_name: str = "pt_BR") -> bool:
    """Instala ``qtbase`` (e ``qt``, quando existir) no idioma pedido.

    Devolve True se ao menos um catálogo foi carregado. Os tradutores
    ficam com o ``app`` como pai para não serem coletados.
    """
    from PySide6.QtCore import QLocale, QTranslator

    folder = str(qt_translations_dir())
    loaded = False
    for prefix in ("qtbase", "qt"):
        translator = QTranslator(app)
        if translator.load(QLocale(locale_name), prefix, "_", folder):
            app.installTranslator(translator)
            loaded = True
    return loaded
