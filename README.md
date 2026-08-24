# Carina

Planetário desktop estilo Stellarium, escrito em Python com **PySide6 + OpenGL**
para renderização e **Skyfield** (efemérides JPL) para os cálculos astronômicos.

> O repositório mantém o nome original `AstroPlanetary`; o aplicativo chama-se
> **Carina** (decisão do usuário, ADR-010).

## Requisitos

- Python 3.12+ (desenvolvido em 3.14)
- Windows / Linux / macOS com OpenGL 3.3+

## Instalação (desenvolvimento)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
```

## Preparar os dados

Os catálogos processados ficam em `data/processed/` (versionados no git,
exceto as imagens). Para regenerá-los a partir das fontes originais:

```powershell
.venv\Scripts\python scripts\build_data.py
```

```powershell
.venv\Scripts\python scripts\build_dso.py
```

```powershell
.venv\Scripts\python scripts\build_images.py
```

O terceiro passo pré-baixa as imagens Messier/Caldwell que serão embarcadas no
instalador (ADR-012). A efeméride JPL `de440s.bsp` (~32 MB) deve estar em
`data/ephemeris/` para ser embarcada no build; em desenvolvimento, se ausente,
o aplicativo baixa para o diretório do usuário no primeiro uso.

## Executar

```powershell
.venv\Scripts\python -m carina
```

Opções úteis para testes: `--screenshot arquivo.png`, `--at "2026-08-24T22:00"`,
`--look az,alt`, `--fov graus`, `--size 1280x800`.

## Build desktop (Windows)

```powershell
.venv\Scripts\python -m PyInstaller Carina.spec --noconfirm
```

O aplicativo final fica em `dist/Carina/Carina.exe`.

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Estrutura do código, pipeline de renderização, matemática das projeções |
| [docs/DECISOES.md](docs/DECISOES.md) | Registro de decisões de arquitetura (ADRs) |
| [docs/FONTES_DE_DADOS.md](docs/FONTES_DE_DADOS.md) | Catálogos usados, licenças e atribuições |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Histórico de versões |
| [docs/PENDENCIAS.md](docs/PENDENCIAS.md) | Roadmap e pendências |
| [docs/BUGS.md](docs/BUGS.md) | Bugs conhecidos |
