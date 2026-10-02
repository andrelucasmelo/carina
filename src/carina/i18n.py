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


# ---------------------------------------------------------------------------
# Idioma do programa (pré-0.17)
# ---------------------------------------------------------------------------

# código → (nome no próprio idioma, idioma dos nomes dos objetos, interface completa?)
LANGUAGES = {
    "pt_BR": ("Português (Brasil)", "pt", True),
    "en": ("English", "en", False),
}
DEFAULT_LANGUAGE = "pt_BR"
SETTING_KEY = "ui/language"


def language_label(code: str) -> str:
    name, _names, complete = LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])
    if complete:
        return name
    return f"{name} — prévia: nomes dos objetos e diálogos do sistema"


def app_translations_dir() -> Path:
    """Onde ficam os ``carina_<idioma>.qm`` (gerados a partir dos ``tr()``)."""
    from .config import package_data_dir

    return package_data_dir() / "i18n"


def apply_language(app, code: str) -> dict:
    """Instala as traduções do idioma escolhido.

    * catálogos do próprio Qt (botões padrão dos diálogos);
    * o catálogo do Carina, ``carina_<código>.qm``, quando existir — a
      tradução completa da interface para o inglês está planejada para a
      v1.0; até lá, o inglês é uma prévia;
    * devolve ``{"qt": bool, "app": bool, "names": "pt"|"en"|"la"}`` — o
      idioma sugerido para os nomes dos objetos.
    """
    from PySide6.QtCore import QTranslator

    code = code if code in LANGUAGES else DEFAULT_LANGUAGE
    qt_ok = install_qt_translations(app, code if code != "en" else "en_US")
    app_ok = False
    qm = app_translations_dir() / f"carina_{code}.qm"
    if qm.exists():
        translator = QTranslator(app)
        if translator.load(str(qm)):
            app.installTranslator(translator)
            app_ok = True
    return {"qt": qt_ok, "app": app_ok, "names": LANGUAGES[code][1]}
