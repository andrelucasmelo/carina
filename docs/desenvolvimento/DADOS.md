# Pipeline de dados

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

O programa só **lê** `data/processed/`. Tudo o que está lá é gerado por
scripts em `scripts/`, a partir de downloads (guardados em `data/raw/`, fora
do git) ou de conteúdo escrito à mão (`scripts/curated/`). Os scripts são
reprodutíveis: rodar de novo gera o mesmo resultado. Quase todos aceitam
`--force` para refazer o que já existe.

Só é preciso rodá-los para reconstruir os dados das fontes ou depois de
mudar o conteúdo curado. Alguns acessam servidores públicos e demoram — os
de imagens podem levar mais de uma hora e são **incrementais** (podem ser
interrompidos e retomados).

## Ordem sugerida

| # | Script | Gera | De onde |
|---|---|---|---|
| 1 | `build_data.py` | `stars_hyg.npz`, `star_names.json`, linhas, limites e centros das constelações, Via Láctea vetorial | HYG v4.1, d3-celestial |
| 2 | `build_deep_stars.py` | `stars_deep.npz` (até magnitude 12) | ATHYG v3.2 |
| 3 | `build_mwtex.py` | `milkyway_tex.jpg` (textura na esfera, galáctico → equatorial) | ESO/S. Brunier |
| 4 | `build_dso.py` | `dso.sqlite` (NGC, IC, Messier, Caldwell, Sharpless, Barnard, Melotte) | OpenNGC, VizieR, SIMBAD |
| 5 | `build_extra_catalogs.py` | LDN, Collinder, van den Bergh e Abell no `dso.sqlite` | VizieR, SIMBAD |
| 6 | `build_images.py` | Imagens Messier e Caldwell | hips2fits (DSS2 color) |
| 7 | `build_large_images.py` · `build_galaxy_images.py` · `build_featured.py` | Imagens dos objetos grandes, das galáxias até magnitude 11 e dos destaques (Nuvens de Magalhães…) | hips2fits |
| 8 | `build_outlines.py` | `outlines.json` — contornos reais de 22 nebulosas | as imagens embarcadas |
| 9 | `build_cities.py` | `cities.json` (745 cidades com fuso) | GeoNames |
| 10 | `build_moon.py --download` | `moon/` — texturas, relevo, 904 formações, Lunar 100, estrelas para ocultações; `meteors.json`; kernels da NAIF | NASA SVS, IAU/USGS, NAIF, HYG, `curated/lunar100.tsv` e `meteors.tsv` |
| 11 | `build_planets.py` | `planets/` — texturas, luas de Júpiter e Saturno, Grande Mancha Vermelha | Solar System Scope, JPL, JUPOS |
| 12 | `build_lightpollution.py --download` | `lightpollution.npz` | NASA Black Marble |
| 13 | `build_lore.py` | `constellation_lore_pt.json` | `scripts/curated/constellation_lore_pt.md` |
| 14 | `build_asterisms.py` | `asterisms.json` e `alignments.json` | `scripts/curated/asterisms.tsv` e `alignments.tsv` |
| 15 | `build_tours.py` | `tours/*.json` | `scripts/curated/tours/**` |
| 16 | `build_programs.py` | `programs/*.json` | catálogos, `curated/herschel400.txt` e `curated/tours/_binoculo.tsv` |
| — | `build_icon.py` | Ícones do executável | `assets/Astronomianoquintal.jpg` |

Os quatro scripts de conteúdo (13 a 16) são rápidos e **validam** o que leem:
uma estrela, um objeto ou uma constelação que não exista no catálogo faz o
script falhar com a lista do que está errado — um dado embarcado nunca
aponta para o vazio.

## Conteúdo curado

`scripts/curated/` guarda o que é escrito à mão, em formatos fáceis de
revisar no git:

| Arquivo | Conteúdo |
|---|---|
| `tours/<categoria>/<chave>.md` | Os tours autorais — ver [Escrevendo tours](TOURS.md) |
| `tours/_textos.md` | Trechos dos tours gerados: estrelas brilhantes, planetas, fases e formações da Lua |
| `tours/_binoculo.tsv` | Alvos do tour "O céu ao binóculo" |
| `asterisms.tsv` | Asterismos: chave, nome, constelações, polilinhas de estrelas (nome, Bayer ou HIP), texto |
| `alignments.tsv` | Alinhamentos: segmentos `A>B*k@rótulo`, ponto médio, mediatriz, polos |
| `constellation_lore_pt.md` | Origem, história, como achar e curiosidade das 88 |
| `lunar100.tsv` · `meteors.tsv` · `herschel400.txt` | Listas factuais com textos próprios |

## Ferramentas de verificação

| Script | Para quê |
|---|---|
| `check_tour.py` | Confere um tour antes do build: alvos, palavras por passo e a altura de cada alvo no Rio (ou noutra latitude) |
| `check_mwtex_alignment.py` | Confere o alinhamento da textura da Via Láctea contra as estrelas |
| `run_isolated.py` | Roda o programa com dados isolados do usuário, para capturas e testes manuais |

## Versionamento dos dados

- `data/processed/` está no git (exceto `images/` e os ícones), para o
  repositório rodar logo depois do clone.
- O `dso.sqlite` embarcado declara uma versão; ao abrir, a cópia editável do
  usuário recebe os objetos novos sem perder as edições dele.
- O acervo de equipamentos tem `DATA_VERSION` em `catalogs/equipment.py`:
  ao subir, os itens novos dos padrões entram uma vez no arquivo do usuário.
