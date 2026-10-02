"""Infraestrutura da aplicação: traduções padrão do Qt (achado D2)."""


def test_qt_base_translations_load(qt_app):
    from PySide6.QtCore import QCoreApplication

    from carina.i18n import install_qt_translations, qt_translations_dir

    assert (qt_translations_dir() / "qtbase_pt_BR.qm").exists()
    assert install_qt_translations(qt_app, "pt_BR")
    # QDialogButtonBox busca os textos neste contexto
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancelar"
    assert QCoreApplication.translate("QPlatformTheme", "Close") == "Fechar"
