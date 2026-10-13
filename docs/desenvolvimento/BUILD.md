# Build e release

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

O Carina é distribuído como uma **pasta autocontida** para Windows
(PyInstaller em modo *onedir*): o Python, as bibliotecas, os dados, as
efemérides e a documentação vão juntos, e nada é instalado no sistema.

## 1. Preparar

- A suíte de testes passa (ver [Testes](TESTES.md)).
- `data/processed/` está completo, com as imagens, e `data/ephemeris/` tem o
  `de440s.bsp` e os kernels — tudo isso vai para dentro do pacote.
- A versão está atualizada em `pyproject.toml`, em `src/carina/__init__.py`
  (`__version__`) e no aviso do topo das páginas de `docs/`.
- `docs/NOVIDADES.md` descreve a versão.

## 2. Ícones

```bash
.venv/Scripts/python scripts/build_icon.py
```

Gera `icon.ico` (16 a 256 px) e os PNG a partir de
`assets/Astronomianoquintal.jpg`. Sem a imagem, o build segue com o ícone
padrão do Windows.

## 3. Executável

```bash
.venv/Scripts/python -m PyInstaller Carina.spec --noconfirm
```

O resultado sai em `dist/Carina/` (`Carina.exe` e `_internal/`), com cerca
de 320 MB. O `Carina.spec` embarca `data/processed`, `data/ephemeris`, `docs`
(a ajuda do `F1`), os dados do Skyfield e do tzdata e os submódulos do
PyOpenGL, que são importados dinamicamente.

Teste de fumaça — abre um tour e salva a captura:

```bash
dist/Carina/Carina.exe --at 2026-05-15T21:00 --dialog tours --dialog-text cruzeiro-polo:6 --screenshot fumaca.png
```

## 4. Pacote, checksum e notas

```bash
.venv/Scripts/python -c "import shutil; shutil.make_archive('release/Carina-0.23.0-windows-x64', 'zip', root_dir='dist', base_dir='Carina')"
```

```bash
sha256sum release/Carina-0.23.0-windows-x64.zip
```

O checksum entra em `release/SHA256.txt` e nas notas
`release/NOTAS-v0.23.0.md` (como usar, o que há de novo, verificação). A
pasta `release/` fica fora do git.

## 5. Tag e publicação

```bash
git tag -a v0.23.0 -m "Carina 0.23.0 — <nome da versão>"
```

```bash
git push origin main --follow-tags
```

```bash
gh release create v0.23.0 release/Carina-0.23.0-windows-x64.zip --title "Carina 0.23.0 — <nome da versão>" --notes-file release/NOTAS-v0.23.0.md --verify-tag
```

A publicação pelo `gh` exige `gh auth login` antes.

## Observações

- O executável não é assinado digitalmente: o SmartScreen pode avisar na
  primeira abertura ("Mais informações ▸ Executar assim mesmo").
- O programa nunca escreve dentro da própria pasta: tudo do usuário vai para
  o perfil dele (ver [Ambiente](AMBIENTE.md#onde-o-programa-guarda-os-dados-do-usuário)).
- Linux e macOS: rodam a partir do código; ainda não há pacote.
