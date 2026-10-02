"""Nomes comuns em português / inglês / latim (decisão 4 da revisão 2026-10)."""

import pytest

from carina.catalogs import names


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    names.set_language("pt")


def test_portuguese_is_default_and_translates_first_name():
    names.set_language("pt")
    assert names.common_label("Lagoon Nebula, Lagune") == "Nebulosa da Lagoa"
    assert names.common_label("Great Orion Nebula, Orion Nebula") == "Grande Nebulosa de Órion"
    assert names.all_labels("Great Orion Nebula, Orion Nebula") == [
        "Grande Nebulosa de Órion", "Nebulosa de Órion",
    ]


def test_english_keeps_original_without_article():
    names.set_language("en")
    assert names.common_label("the Witch Head Nebula") == "Witch Head Nebula"
    assert names.common_label("Lagoon Nebula") == "Lagoon Nebula"


def test_latin_falls_back_to_original():
    names.set_language("la")
    assert names.common_label("Beehive, Praesepe Cluster") == "Praesepe"
    assert names.common_label("Crab Nebula") == "Crab Nebula"


def test_unknown_name_passes_through_and_empty_is_empty():
    assert names.common_label("Nome Qualquer") == "Nome Qualquer"
    assert names.common_label(None) == ""
    assert names.common_label("") == ""


def test_invalid_language_resets_to_default():
    names.set_language("xx")
    assert names.language() == "pt"


def test_search_by_translation_returns_original_names():
    names.set_language("pt")
    hits = names.search_translations("lagoa")
    assert "lagoon nebula" in hits
    names.set_language("en")
    assert names.search_translations("lagoa") == []
