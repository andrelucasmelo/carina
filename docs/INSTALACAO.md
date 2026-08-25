# Instalação

> Carina 0.13.2 — produto em desenvolvimento.

Há dois caminhos: usar o **executável pronto** (recomendado para
observar) ou rodar **a partir do código** (para acompanhar o
desenvolvimento e modificar o programa).

---

## 1. Windows — executável pronto

O jeito mais simples. O executável é **autocontido**: traz o Python, as
bibliotecas, os catálogos, as efemérides e as imagens dos objetos.

1. Copie a pasta `Carina` inteira para onde quiser — por exemplo
   `C:\Programas\Carina`.
2. Execute **`Carina.exe`**.

Pronto. Não instala nada no sistema, não exige Python e **funciona sem
internet**.

### O que fica onde

O programa nunca escreve dentro da própria pasta. Seus dados pessoais vão
para o perfil do usuário:

| O quê | Onde |
|---|---|
| Preferências (camadas, local, configurações) | Registro do Windows, em `HKCU\Software\Carina\Carina` |
| Seu catálogo de objetos, com as edições | `%LOCALAPPDATA%\Carina\Carina\dso.sqlite` |
| Seus equipamentos | `%LOCALAPPDATA%\Carina\Carina\equipamentos.json` |
| Imagens baixadas em uso | `%LOCALAPPDATA%\Carina\Carina\Cache\images\` |

Para **desinstalar**, apague a pasta do programa. Para apagar também os
dados pessoais, remova a pasta `%LOCALAPPDATA%\Carina`.

### Aviso do Windows ao abrir

Como o executável não é assinado digitalmente, o SmartScreen pode exibir
"O Windows protegeu o computador". Clique em **Mais informações →
Executar assim mesmo**. Isso acontece com qualquer programa sem
certificado de assinatura, que custa caro para um projeto pessoal.

---

## 2. A partir do código

Necessário para desenvolver, e a forma de usar em Linux e macOS.

### Requisitos

- **Python 3.12 ou mais novo** (desenvolvido em 3.14)
- **OpenGL 3.3+** — qualquer GPU dos últimos quinze anos atende
- ~2 GB livres em disco para o ambiente e os dados

### Passo a passo

```bash
git clone <url-do-repositorio> AstroPlanetary
cd AstroPlanetary
python -m venv .venv
```

Ative o ambiente e instale:

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
```

No Linux e no macOS o interpretador fica em `.venv/bin/python`.

Execute:

```bash
.venv/Scripts/python -m carina
```

### As efemérides

Os cálculos do Sistema Solar usam o arquivo **DE440s** do JPL
(`de440s.bsp`, cerca de 32 MB), que cobre de 1849 a 2150.

- No **executável**, ele já vem embarcado.
- Rodando **do código**, coloque-o em `data/ephemeris/de440s.bsp`. Se não
  estiver lá, o Skyfield baixa automaticamente para a pasta do usuário na
  primeira execução — o que exige internet uma única vez.

### Os catálogos

Os dados processados ficam em `data/processed/` e **acompanham o
repositório**, com uma exceção: as imagens dos objetos, que somam quase
100 MB e são geradas localmente.

Para regenerar tudo a partir das fontes originais:

```bash
.venv/Scripts/python scripts/build_data.py
```

```bash
.venv/Scripts/python scripts/build_dso.py
```

```bash
.venv/Scripts/python scripts/build_images.py
```

Os scripts baixam dos servidores públicos (HYG, OpenNGC, VizieR, SIMBAD,
CDS) e convertem para os formatos internos. São demorados — o de imagens
pode levar mais de uma hora — mas só precisam rodar uma vez. Detalhes em
[CATALOGOS.md](CATALOGOS.md).

---

## 3. Compilar o próprio executável

```bash
.venv/Scripts/python scripts/build_icon.py
```

```bash
.venv/Scripts/python -m PyInstaller Carina.spec --noconfirm
```

O primeiro comando gera os ícones a partir de `assets/`; o segundo
empacota tudo. O resultado sai em `dist/Carina/`, com cerca de 320 MB —
a maior parte são as imagens dos objetos e as efemérides.

---

## 4. Linux e macOS

O Carina é escrito em Python com Qt e **deve funcionar**, mas ainda não
passou por testes sistemáticos fora do Windows. Siga o caminho "a partir
do código". Duas observações:

- **Linux**: pode ser necessário instalar as bibliotecas de sistema do
  Qt (`libxcb`, `libgl1`) pelo gerenciador de pacotes.
- **macOS**: a Apple depreciou o OpenGL, mas ele continua funcionando; o
  desempenho pode ser inferior ao do Windows com GPU dedicada.

Relatos de uso nesses sistemas são muito bem-vindos.

---

## Verificando a instalação

Rode a suíte de testes — 130 testes que conferem desde a projeção
matemática até a geração dos roteiros:

```bash
.venv/Scripts/python -m pytest tests -q
```

Para conferir a renderização sem abrir a janela:

```bash
.venv/Scripts/python -m carina --screenshot teste.png --at "2026-08-24T22:00"
```

Se o PNG sair com o céu desenhado, está tudo certo.

Problemas? Veja [SOLUCAO_DE_PROBLEMAS.md](SOLUCAO_DE_PROBLEMAS.md).
