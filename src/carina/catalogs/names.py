"""Nomes comuns dos objetos de céu profundo em português, inglês ou latim.

A base OpenNGC traz os nomes populares em inglês — às vezes em francês
("Amas de l'Ecu de Sobieski") ou com artigo ("the Witch Head Nebula").
O usuário escolhe o idioma em Exibir ▸ Idioma dos nomes dos objetos, e
mapa, ficha, busca e roteiros passam todos por :func:`common_label`.

A tabela (``data/processed/common_names.json``) é curada à mão: chave =
nome original da base, valor = tradução. O que não tem tradução aparece
no original, sem artigo.
"""

from __future__ import annotations

import json

LANGUAGES = {"pt": "Português", "en": "Inglês (original)", "la": "Latim"}
DEFAULT_LANGUAGE = "pt"

_language = DEFAULT_LANGUAGE
_tables: dict[str, dict[str, str]] | None = None
_ARTICLES = ("the ", "The ")


def _load() -> dict[str, dict[str, str]]:
    """Carrega a tabela uma vez (chaves em minúsculas para casar sem
    diferenciar maiúsculas)."""
    global _tables
    if _tables is None:
        from ..config import package_data_dir

        path = package_data_dir() / "common_names.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        _tables = {
            lang: {k.lower(): v for k, v in raw.get(lang, {}).items()}
            for lang in ("pt", "la")
        }
    return _tables


def set_language(lang: str) -> None:
    """Idioma dos nomes: 'pt', 'en' ou 'la' (inválido → padrão)."""
    global _language
    _language = lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def language() -> str:
    return _language


def first_name(common: str | None) -> str:
    """Primeiro nome da lista separada por vírgulas, sem traduzir."""
    return (common or "").split(",")[0].strip()


def _strip_article(name: str) -> str:
    for art in _ARTICLES:
        if name.startswith(art):
            return name[len(art):]
    return name


def translate(name: str, lang: str | None = None) -> str:
    """Um nome comum no idioma pedido (ou no escolhido globalmente)."""
    lang = lang or _language
    name = name.strip()
    if not name:
        return ""
    if lang == "en":
        return _strip_article(name)
    table = _load().get(lang, {})
    hit = table.get(name.lower()) or table.get(_strip_article(name).lower())
    return hit or _strip_article(name)


def common_label(common: str | None) -> str:
    """Primeiro nome comum do objeto, no idioma escolhido ("" se não há)."""
    return translate(first_name(common))


def all_labels(common: str | None) -> list[str]:
    """Todos os nomes comuns do objeto traduzidos, sem repetições."""
    out: list[str] = []
    for part in (common or "").split(","):
        label = translate(part)
        if label and label not in out:
            out.append(label)
    return out


def search_translations(text: str, lang: str | None = None) -> list[str]:
    """Nomes ORIGINAIS cujas traduções contêm ``text`` (para a busca).

    Permite digitar "lagoa" e achar a "Lagoon Nebula" da base.
    """
    lang = lang or _language
    needle = text.strip().lower()
    if len(needle) < 2 or lang == "en":
        return []
    table = _load().get(lang, {})
    return [orig for orig, tr in table.items() if needle in tr.lower()]
