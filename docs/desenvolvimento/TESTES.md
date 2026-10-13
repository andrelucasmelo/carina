# Testes e qualidade

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

Precisão astronômica é o compromisso central do projeto: cada cálculo novo
é conferido contra uma fonte independente e ganha teste.

## Rodar a suíte

```bash
.venv/Scripts/python -m pytest tests -q
```

São **517 testes** (versão 0.23.0), em cerca de cinco minutos. Para rodar
uma parte:

```bash
.venv/Scripts/python -m pytest tests/test_tours_v023.py -q
```

```bash
.venv/Scripts/python -m pytest tests -q -k "moon or eclipse"
```

## Como a suíte se protege

- **Dados do usuário isolados.** `tests/conftest.py` troca o QSettings por um
  `.ini` descartável e o `carina.sqlite` por um banco temporário antes de
  qualquer teste: a suíte nunca toca nas preferências nem no diário de quem
  roda.
- **Qt sem tela.** Uma única `QApplication` na plataforma `offscreen`:
  nada aparece, nenhum foco é roubado.
- **OpenGL num subprocesso.** A plataforma `offscreen` não tem framebuffer
  OpenGL; o que precisa desenhar de verdade (relatório, pôster, planisfério,
  as setas e o anel lunar dos tours) roda em `tests/gl_v022_script.py` e
  `tests/gl_v023_script.py`, com a plataforma real e os dados isolados, e
  devolve um JSON com o resultado. Esses testes são pulados com
  `CARINA_SKIP_GUI=1` em máquinas sem GPU.
- **Efemérides.** Testes que precisam do `de440s.bsp` são pulados se ele
  faltar em `data/ephemeris/`.

## O que é validado contra fontes independentes

- **Nascer, culminação e ocaso** contra o almanaque do Skyfield em três
  datas e duas latitudes: erro abaixo de um minuto.
- **Altitudes e horários** contra varreduras finas independentes: erro de
  0,003°.
- **Eclipses** contra o cânone da NASA: datas, tipos e magnitudes de
  2026–2028 batem.
- **Planetas**: oposições de Marte (19/02/2027) e de Saturno (04/10/2026) e
  elongações de Vênus nas datas publicadas; luas de Júpiter e Saturno a menos
  de 0,1″ do JPL Horizons.
- **Lua**: libração e colongitude contra o exemplo de Meeus (erro abaixo de
  0,05°); o perigeu da superlua de 14/11/2016; a ocultação de Antares de
  03/03/2024 (erro abaixo de dois minutos).
- **Via Láctea**: alinhamento da textura verificado estrela a estrela —
  erro mediano de cerca de um pixel de textura
  (`scripts/check_mwtex_alignment.py`).
- **Tours**: todo alvo existe no catálogo; os tours escritos para o Brasil
  rodam no Rio sem passo pulado; as setas apontam para onde dizem; a rota
  "como achar" diz o lado certo de cada estrela-guia.

## Capturas e desempenho

Validações visuais usam a linha de comando: cada recurso abre com uma opção
e `--screenshot` grava o PNG (ver [Ambiente](AMBIENTE.md#linha-de-comando-para-testes-e-capturas)).
Para medir o tempo de quadro em cenários pesados:

```bash
.venv/Scripts/python -m carina --bench
```

A regra do projeto: nenhuma otimização entra sem o número de antes e de
depois.

## Antes de um commit

1. A suíte inteira passa.
2. Recurso novo tem teste; correção de defeito tem o teste que o reproduz.
3. Conteúdo novo (tours, asterismos, alinhamentos) passa pelo build, que
   valida tudo.
4. A documentação do usuário (`docs/`) acompanha a mudança.
