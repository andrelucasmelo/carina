# Como contribuir

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

O Carina está em desenvolvimento ativo. O retorno de quem observa de verdade
é o mais valioso.

## Relatar um problema

Abra uma *issue* no GitHub com:

- a **versão** (*Ajuda ▸ Sobre o Carina*);
- a **cidade** configurada e a **data e hora** simuladas;
- o que você esperava ver e o que apareceu;
- se possível, uma captura (`Ctrl+S` exporta a vista).

Os mais úteis: **erros de céu** (algo fora de lugar, um horário estranho, um
objeto ausente), **usabilidade no escuro e no campo** e **listas e textos**
(objetos que faltam, um fato errado num tour).

## Convenções de código

- **Python 3.12+**, `from __future__ import annotations`, tipagem nas
  assinaturas públicas.
- **Comentários e docstrings em português**, explicando o *porquê*; cada
  módulo abre com uma docstring que diz o que ele faz e a que versão ou
  decisão pertence.
- **Textos da interface** sempre por `self.tr(...)`.
- **`core/` sem Qt**: a lógica fica testável sem interface.
- **Vetorizado**: cálculos sobre muitos objetos ou instantes em NumPy, não em
  laços Python.
- **Recurso novo = opção de linha de comando** que o aciona e permite a
  captura (`--dialog`, `--dialog-text`, `--screenshot`).
- **Dados do usuário são sagrados**: nada de teste ou script tocando no
  `carina.sqlite` ou nas preferências reais (use `scripts/run_isolated.py`).

## Conteúdo

- Tours, asterismos, alinhamentos e histórias ficam em `scripts/curated/`,
  em formatos de texto revisáveis; o build valida tudo
  ([Escrevendo tours](TOURS.md)).
- Fatos conferidos em mais de uma fonte; na dúvida, arredonde ou omita.
- Só texto próprio ou com licença compatível com MIT, com a fonte registrada
  em [Componentes e dados](COMPONENTES.md).

## Documentação

- Mudou o que o usuário vê? Atualize a página correspondente em `docs/` (é a
  mesma ajuda do `F1`) e o `docs/NOVIDADES.md`.
- Decisão de arquitetura nova? Registre-a como ADR e resuma em
  [Decisões](DECISOES.md).

## Commits

- Mensagens em português, no imperativo, com prefixo: `feat:`, `fix:`,
  `docs:`, `chore:` (versão, build), `test:`.
- Corpo com a lista do que mudou e o número de testes ao fim.
- Uma versão costuma ter dois commits: o da funcionalidade e o
  `chore: versão X.Y.Z` com a documentação.
- A suíte inteira passa antes de cada commit.
