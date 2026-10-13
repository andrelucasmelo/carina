# Escrevendo tours

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md) · para o
> usuário: [Tours guiados](../TOURS.md)

Um tour é uma sequência de **passos**. Cada passo leva o céu a um instante,
aponta para um alvo com um campo, acende figuras e mostra um texto curto. Há
dois tipos, servidos pelo mesmo motor (`core/tours.py`):

- **autorais** — Markdown em `scripts/curated/tours/<categoria>/<chave>.md`,
  convertido em JSON embarcado por `scripts/build_tours.py`;
- **gerados** — montados em Python para a data e o local do usuário
  (`core/tours_generated.py`): o céu do mês, os objetos do mês para
  fotografar, a Maratona Messier, a Lua no terminador e outros.

## O arquivo de um tour

```markdown
---
key: cruzeiro-polo
title: O Cruzeiro do Sul e o polo sul
subtitle: A cruz da bandeira, os Guardiões e o ponto vazio em volta do qual o céu gira
category: iniciante
level: 1
minutes: 8
when: data:05-15 hora:21:00
lat_range: -40, 5
tags: Cruzeiro do Sul, polo sul celeste, orientação
author: Carina / Astronomia no Quintal
---

## De frente para o sul
@kind: intro
@target: altaz:180,40
@fov: 110
@layers: const_lines=1, const_names=1, asterisms=1
@skip_if_below: -90

Texto do passo em Markdown.

## O polo sul pelos dois caminhos
@target: alignment:cruzeiro-polo
@fov: 70
@highlight: asterism:cruzeiro, asterism:apontadores

Texto. {lore:find:Cru} insere o "como achar" da constelação.
```

### Cabeçalho

| Campo | Valores |
|---|---|
| `key` | Igual ao nome do arquivo, em `kebab-case` |
| `category` | `iniciante`, `intermediario`, `astrofoto`, `extra` (`aplicativo` reservado) |
| `level` · `minutes` | Nível 1 a 3 e duração estimada |
| `when` | Relógio do tour: `agora`, `inicio_da_noite`, `hora:HH:MM` ou `data:MM-DD hora:HH:MM` (noite típica) |
| `lat_range` | Faixa de latitude para a qual foi escrito; fora dela, o tour avisa |

### Campos do passo (linhas `@` logo depois do título)

| Campo | O que faz |
|---|---|
| `@target` | O alvo — ver abaixo |
| `@time` | `+2h`, `-30m`, `21:30`, `melhor` (melhor hora do alvo), `data:MM-DD hora:HH:MM` (outra noite do ano) ou `em:AAAA-MM-DDTHH:MM` |
| `@fov` | Campo em graus; sem ele, um padrão pelo tipo e tamanho do alvo |
| `@highlight` | Figuras acesas: `const:Ori`, `asterism:bule`, `alignment:orion-sirius-aldebaran` |
| `@layers` | Camadas ligadas/desligadas a partir deste passo (cumulativo): `const_names=1, dso=0…` |
| `@kind` | `goto` (padrão), `intro`, `object`, `fim` — `intro` e `fim` nunca são pulados |
| `@image` | `dss:NGC 3372` (recorte embarcado) ou caminho em `data/processed/tours/` |
| `@fov_circle` | Campo circular desenhado (binóculo: 6) |
| `@setup_fov: sim` | Desenha o campo do setup ativo do usuário (com mosaico) |
| `@fov_rect` | Quadro fixo desenhado: `1.29x0.73 Seestar S50` |
| `@finder: sim` | Acrescenta a rota "como achar" a partir das estrelas |
| `@moon_feature` | Formação lunar marcada com um anel (alvo `body:Lua`) |
| `@bortle` | Força a classe de Bortle a partir deste passo |
| `@skip_if_below` | Altura mínima do alvo; abaixo dela o passo é pulado com aviso |

### Alvos

| Alvo | Exemplo |
|---|---|
| Estrela | `star:Sirius`, `star:alf Cen`, `star:mu-1 Sco`, `star:HIP 92202` |
| Céu profundo | `dso:M 42`, `dso:NGC 3372`, `dso:IC 2602`, `dso:C 99`, `dso:ESO056-115` (Grande Nuvem) |
| Constelação | `const:Cru` (sigla IAU) |
| Asterismo | `asterism:cruzeiro`, `asterism:bule`, `asterism:cabide`… (`scripts/curated/asterisms.tsv`) |
| Alinhamento | `alignment:cruzeiro-polo`… (`scripts/curated/alignments.tsv`) — a seta desenhada com o rótulo da ponta |
| Corpo | `body:Lua`, `body:Júpiter` |
| Direção | `altaz:180,40` (azimute, altura) — para introduções e panoramas |

### Os alinhamentos

`scripts/curated/alignments.tsv` define as "setas" com uma sintaxe curta,
convertida em arcos pré-calculados por `scripts/build_asterisms.py`:

```
cruzeiro-polo  Do Cruzeiro ao polo sul  Gacrux>Acrux*4.5@Polo Sul Celeste|mediatriz:Rigil Kentaurus+Hadar>polo_sul  Texto…
```

- `A>B` — arco de A até B; `*k` prolonga além de B por k vezes a distância
  A-B ("prolongue o braço quatro vezes e meia"); `@texto` rotula a ponta.
- Pontos: estrela, `dso:M 31`, `radec:266.4,-29.0`, `polo_sul`,
  `polo_norte`, `meio:A+B`.
- `mediatriz:A+B>alvo` — a perpendicular ao meio de A-B, até o ponto mais
  perto do alvo.

## Escrever bem um passo

- **60 a 120 palavras** (o teste aceita de 15 a 190). Uma ideia por passo:
  onde olhar, o que se vê a olho nu, no binóculo e no telescópio pequeno, e
  um fato que fique na memória.
- Português do Brasil, direto, sem jargão não explicado; a perspectiva de
  quem observa do Brasil (Órion de cabeça para baixo, as estações do sul).
- Cada passo na noite em que o alvo está alto (`@time: data:…`), não
  escondido perto do horizonte.
- Números conferidos (magnitudes, distâncias, tamanhos) — na dúvida,
  arredonde ou omita.
- Nunca copie texto de terceiros. Notas de pesquisa servem como fonte de
  fatos; o texto é próprio.

## Conferir e gerar

```bash
.venv/Scripts/python scripts/check_tour.py cruzeiro-polo
```

Lista cada passo com a data, a hora, a altura do alvo no Rio de Janeiro, as
palavras e o que seria pulado. Use `--lat -30` e `--lat -3` para Porto Alegre
e Fortaleza. Depois:

```bash
.venv/Scripts/python scripts/build_tours.py
```

O build valida o esquema, resolve **todos** os alvos no catálogo e falha se
algo não existir; `--check` só valida. Para ver o tour no programa, abra-o
já num passo:

```bash
.venv/Scripts/python scripts/run_isolated.py %TEMP%/carina-iso --at 2026-05-15T21:00 --dialog tours --dialog-text cruzeiro-polo:6
```

Tours novos entram em `SUGGESTED_ORDER` (`core/tours.py`) para a ordem da
galeria e do "próximo tour sugerido".

## Tours gerados

Um gerador recebe um `GenContext` (motor, catálogos, instante, latitude,
Bortle, setup ativo) e devolve um `Tour` com os textos já preenchidos pelos
números calculados. Trechos fixos (estrelas brilhantes, planetas, fases e
formações da Lua) vêm de `scripts/curated/tours/_textos.md`. Para criar um:
escreva a função em `core/tours_generated.py`, registre-a em `GENERATORS` e
acrescente um teste que gere o tour em mais de uma latitude e confira que
nenhum passo é pulado.

## Testes

`tests/test_tours*.py` conferem, entre outros: que todo tour embarcado
carrega e resolve os alvos; o tamanho dos textos; que os tours novos rodam no
Rio sem passo pulado; que as quatro noites das 88 constelações cobrem as 88;
que as setas apontam para onde dizem (a do Cruzeiro termina a menos de 4° do
polo).
