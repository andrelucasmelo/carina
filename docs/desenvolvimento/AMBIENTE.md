# Ambiente de desenvolvimento

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

## Requisitos

| | |
|---|---|
| **Python** | 3.12 ou mais novo (o projeto é desenvolvido em 3.14) |
| **Gráficos** | OpenGL 3.3 core — qualquer GPU dos últimos quinze anos |
| **Sistema** | Windows 10/11 (principal); Linux e macOS devem funcionar, sem testes sistemáticos |
| **Disco** | ~2 GB para o ambiente, os dados e o build |

## Clonar, instalar e rodar

```bash
git clone https://github.com/andrelucasmelo/carina.git AstroPlanetary
```

```bash
cd AstroPlanetary
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
```

```bash
.venv/Scripts/python -m carina
```

No Linux e no macOS o interpretador fica em `.venv/bin/python`. No Linux
pode ser preciso instalar as bibliotecas de sistema do Qt (`libxcb`,
`libgl1`); no macOS o OpenGL está depreciado mas funciona.

O extra `dev` traz o `pytest`, o `pyinstaller` e o `pillow`. O repositório
mantém o nome original `AstroPlanetary`; o pacote Python e o aplicativo se
chamam `carina`.

## O que precisa estar no lugar

- **`data/processed/`** — os dados processados que o programa lê. Estão no
  git, **exceto as imagens** dos objetos (`data/processed/images/`, ~100 MB),
  que são geradas pelos scripts de imagens. Sem elas o programa roda; a
  ficha mostra a imagem só quando ela existe ou foi baixada.
- **`data/ephemeris/`** — `de440s.bsp` (JPL, ~32 MB) e os kernels da Lua e
  das luas dos planetas. Ficam fora do git. Rodando do código, se o
  `de440s.bsp` faltar, o Skyfield o baixa para a pasta do usuário no
  primeiro uso; os demais vêm com `scripts/build_moon.py --download` e
  `scripts/build_planets.py`.
- **`data/raw/`** — downloads brutos das fontes, usados só pelos scripts de
  dados. Fora do git.

Como regenerar cada arquivo: [Pipeline de dados](DADOS.md).

## Estrutura do repositório

```
src/carina/           o aplicativo
  core/               astronomia, planejamento, tours, dados do usuário — sem Qt
  catalogs/           estrelas, céu profundo, constelações, equipamentos, imagens
  render/             OpenGL, temas, Lua e planetas na CPU, molduras de carta
  ui/                 janelas, diálogos e o céu (SkyWidget)
  __main__.py         ponto de entrada e linha de comando de testes
scripts/              pipeline de dados, build de conteúdo e ferramentas
  curated/            conteúdo escrito à mão: tours, asterismos, alinhamentos,
                      histórias das constelações, Lunar 100, chuvas de meteoros
data/processed/       dados embarcados (gerados pelos scripts)
tests/                suíte pytest e scripts de teste com OpenGL
docs/                 documentação do usuário (também abre no programa, F1)
docs/desenvolvimento/ esta documentação
Carina.spec           receita do PyInstaller
```

O mapa de cada módulo está em [Arquitetura](ARQUITETURA.md).

## Onde o programa guarda os dados do usuário

| O quê | Onde (Windows) |
|---|---|
| Preferências (camadas, local, janelas) | Registro, `HKCU\Software\Carina\Carina` (QSettings) |
| Listas, diário, horizontes, perfis, progresso dos tours | `%LOCALAPPDATA%\Carina\Carina\carina.sqlite` |
| Cópia editável do catálogo de céu profundo | `%LOCALAPPDATA%\Carina\Carina\dso.sqlite` |
| Equipamentos e setups | `%LOCALAPPDATA%\Carina\Carina\equipamentos.json` |
| Imagens baixadas | `%LOCALAPPDATA%\Carina\Carina\Cache\images\` |

## Linha de comando para testes e capturas

O padrão do projeto: **cada recurso ganha uma opção que o aciona ao abrir**,
e `--screenshot` grava o resultado num PNG e fecha o programa. É assim que
as validações visuais, as capturas da documentação e o `--bench` rodam.

| Opção | O que faz |
|---|---|
| `--screenshot ARQ.png` | Renderiza, salva o PNG (da janela ou do diálogo aberto) e sai |
| `--at 2026-08-24T22:00` | Congela o relógio da simulação nesse instante (sem fuso, vale a hora do computador; aceita `-03:00`) |
| `--size 1400x860` | Tamanho da janela |
| `--look AZ,ALT` · `--fov GRAUS` | Direção e campo da câmera |
| `--select NOME` | Seleciona um objeto ao abrir |
| `--bortle N` | Classe de Bortle (1 a 9) |
| `--enable-layer` · `--disable-layer CAMADA` | Liga ou desliga uma camada (`grid_altaz`, `asterisms`, `dso`…) |
| `--dialog NOME` | Abre uma janela ao iniciar: `tonight`, `calendar`, `moon`, `planets`, `session`, `tours`, `toursgallery`, `programs`, `quiz`, `poster`, `planisphere`… |
| `--dialog-text TEXTO` | Parâmetro da janela: o tour e o passo (`cruzeiro-polo:6`), o planeta (`Júpiter`), o modo do quiz (`asterism`)… |
| `--marathon TIPO` · `--marathon-pdf ARQ` | Abre um roteiro e exporta o PDF |
| `--chart-pdf ARQ` · `--chart-const SIGLA` | Gera uma carta celeste em PDF |
| `--night` · `--observe` · `--chart` | Modo noturno, modo observação, modo mapa |
| `--offscreen ARQ` | Também grava um quadro renderizado fora da tela |
| `--bench` | Mede o tempo de quadro em cenários de estresse |

A lista completa sai em `python -m carina --help`.

### Isolar os dados do usuário

Qualquer execução que abre a janela lê e pode gravar as preferências e o
banco **reais** do usuário. Para capturas e experimentos, use o executor
isolado, que troca as pastas e o QSettings por uma pasta descartável:

```bash
.venv/Scripts/python scripts/run_isolated.py %TEMP%/carina-iso --at 2026-06-10T21:00 --look 120,40 --fov 75 --bortle 1 --disable-layer grid_altaz --screenshot ceu.png
```

Trocar só a variável `LOCALAPPDATA` **não** isola: o `platformdirs` consulta
a API do Windows. A suíte de testes já se isola sozinha (`tests/conftest.py`).

## IDE

O projeto é desenvolvido no PyCharm, com o interpretador em `.venv`. Marque
`src/` como raiz de código-fonte. Os testes rodam pelo próprio pytest
(ver [Testes e qualidade](TESTES.md)).
