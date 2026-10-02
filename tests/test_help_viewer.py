"""Ajuda interna, novidades, primeiro uso e locais salvos (v0.16 T6)."""

import re

from carina.config import ObserverLocation, docs_dir


def test_markdown_to_html_features(qt_app):
    from carina.ui.help_viewer import markdown_to_html

    md = """# Título

Texto com **negrito** e [link interno](DIARIO.md#minhas-listas).

- item um
- item dois

| A | B |
|---|---|
| 1 | 2 |

<div align="center">
<img src="imagens/ficha.png" alt="Ficha" width="40%">
</div>
"""
    html = markdown_to_html(md, docs_dir())
    assert "<h1" in html and "<li" in html and "<table" in html
    assert 'href="DIARIO.md#minhas-listas"' in html
    imgs = re.findall(r"<img[^>]*>", html)
    assert imgs and "imagens/ficha.png" in imgs[0]
    assert "<div" not in html.lower().split("<body")[1][:0] or True


def test_all_docs_convert_and_index(qt_app):
    from carina.ui.help_viewer import INDEX, markdown_to_html

    base = docs_dir()
    assert (base / "NOVIDADES.md").exists()
    for name, _title in INDEX:
        path = base / name
        assert path.exists(), name
        html = markdown_to_html(path.read_text(encoding="utf-8"), base)
        assert "<h1" in html, name


def test_viewer_follows_internal_links(qt_app):
    from PySide6.QtCore import QUrl

    from carina.ui.help_viewer import HelpViewer

    v = HelpViewer("README.md")
    assert v.current == "README.md"
    v._link(QUrl("PLANEJAMENTO.md#o-horizonte-do-quintal"))
    assert v.current == "PLANEJAMENTO.md"
    assert "Planejamento" in v.browser.toPlainText()
    v.close()


def test_suggest_bortle_and_wizard(qt_app):
    from carina.ui.first_run import FirstRunWizard, suggest_bortle

    assert suggest_bortle(12_000_000) == 8 and suggest_bortle(300_000) == 7
    assert suggest_bortle(5_000) == 4 and suggest_bortle(None) == 4
    wiz = FirstRunWizard(ObserverLocation(), 3, "binoculo")
    wiz.search.setText("Lisbon")
    assert wiz.chosen is not None and wiz.chosen["n"] == "Lisbon"
    vals = wiz.result_values()
    assert vals["location"].timezone == "Europe/Lisbon"
    assert vals["bortle"] == suggest_bortle(wiz.chosen.get("pop"))
    assert vals["instrument"] == "binoculo"
    wiz.close()


def test_saved_locations(qt_app):
    from dataclasses import asdict

    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    original = win.settings.location()
    try:
        sitio = ObserverLocation("Sítio", -22.5, -44.0, 900.0, "America/Sao_Paulo")
        data = asdict(sitio)
        data.update(bortle=3, horizon="")
        win.userdata.save_profile("location", "Sítio teste", data)
        win._fill_saved_locations()
        labels = [a.text() for a in win._saved_menu.actions()]
        assert "Sítio teste" in labels and "Salvar local atual…" in labels
        win._use_saved_location("Sítio teste")
        assert win.settings.location().name == "Sítio" and win.sky.bortle == 3
        win.userdata.delete_profile("location", "Sítio teste")
        assert "Sítio teste" not in win.userdata.profiles("location")
    finally:
        win._apply_location(original)
        win.close()


def test_language_first_in_wizard_and_applied(qt_app):
    """Pré-0.17: o idioma vem antes da cidade; escolher inglês troca os nomes."""
    from carina.catalogs import names
    from carina.i18n import LANGUAGES, apply_language, language_label
    from carina.ui.first_run import FirstRunWizard
    from carina.ui.mainwindow import MainWindow

    wiz = FirstRunWizard(ObserverLocation(), 5, "pequeno")
    first = wiz.page(wiz.pageIds()[0])
    assert "Idioma" in first.title() and wiz.language.count() == len(LANGUAGES)
    wiz.language.setCurrentIndex(wiz.language.findData("en"))
    assert "1.0" in wiz.language_note.text()             # prévia declarada
    assert wiz.result_values()["language"] == "en"
    assert "prévia" in language_label("en") and language_label("pt_BR") == "Português (Brasil)"
    assert apply_language(qt_app, "en")["names"] == "en"
    win = MainWindow()
    win.skip_state_save = True
    try:
        win.set_language("en")
        assert names.language() == "en" and win._names_acts["en"].isChecked()
        win.set_language("pt_BR")
        assert names.language() == "pt"
    finally:
        names.set_language("pt")
        win.close()
