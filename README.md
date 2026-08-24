# AstroPlanetary

Planetário desktop estilo Stellarium, escrito em Python com **PySide6 + OpenGL** para
renderização e **Skyfield** (efemérides JPL) para os cálculos astronômicos.

## Requisitos

- Python 3.12+ (desenvolvido em 3.14)
- Windows / Linux / macOS com OpenGL 3.3+

## Instalação (desenvolvimento)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
```

## Preparar os dados

Os catálogos processados ficam em `data/processed/` (versionados no git). Para
regenerá-los a partir das fontes originais:

```powershell
.venv\Scripts\python scripts\build_data.py
```

Na primeira execução o aplicativo baixa a efeméride JPL `de440s.bsp` (~32 MB)
para o diretório de dados do usuário.

## Executar

```powershell
.venv\Scripts\python -m astroplanetary
```

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Estrutura do código, pipeline de renderização, matemática das projeções |
| [docs/DECISOES.md](docs/DECISOES.md) | Registro de decisões de arquitetura (ADRs) |
| [docs/FONTES_DE_DADOS.md](docs/FONTES_DE_DADOS.md) | Catálogos usados, licenças e atribuições |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Histórico de versões |
| [docs/PENDENCIAS.md](docs/PENDENCIAS.md) | Roadmap e pendências |
| [docs/BUGS.md](docs/BUGS.md) | Bugs conhecidos |
