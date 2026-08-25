<div align="center">

<img src="docs/imagens/icone.png" alt="Carina" width="140">

# Carina

**Planetário de código aberto para quem observa o céu do quintal.**

Mostra o céu real do seu lugar e da sua hora — e o transforma em um plano
de observação: o que olhar hoje, a que horas, com qual instrumento e como
encontrar cada objeto.

[![status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)](#estado-do-projeto)
[![versao](https://img.shields.io/badge/vers%C3%A3o-0.13.2-blue)](#estado-do-projeto)
[![testes](https://img.shields.io/badge/testes-130%20passando-brightgreen)](#qualidade)
[![licenca](https://img.shields.io/badge/licen%C3%A7a-MIT-lightgrey)](#licença)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](#requisitos)

</div>

---

## Estado do projeto

> ### Versão 0.13.2 — **em desenvolvimento**
>
> **Este produto ainda está em desenvolvimento e não teve uma versão
> estável (1.0) lançada.** Ele já é plenamente usável para observação
> real — os cálculos astronômicos foram validados contra efemérides
> oficiais — mas ainda **não** é um produto acabado:
>
> - a interface e os formatos de arquivo **podem mudar** entre versões;
> - recursos novos entram a cada versão, e alguns ainda estão incompletos;
> - foi testado principalmente no **Windows 11**; Linux e macOS devem
>   funcionar, mas não passaram por testes sistemáticos;
> - podem existir defeitos ainda não descobertos.
>
> **Use para planejar e observar à vontade** — apenas não conte com
> estabilidade de interface entre uma versão e outra. Se algo parecer
> errado no céu ou nos horários, [reporte](#como-contribuir): precisão é
> a prioridade número um do projeto.

---

## O que o Carina faz

Um planetário mostra o céu. O Carina também **planeja a sua noite**.

| | Recurso | Resumo |
|---|---|---|
| 🌌 | **Céu realista** | 860 mil estrelas, Via Láctea fotográfica, atmosfera, refração e simulação de poluição luminosa (Bortle 1–9) |
| 🔭 | **Céu profundo** | 18.632 objetos de 11 catálogos, com 1.179 imagens reais do levantamento DSS embarcadas |
| 🪐 | **Sistema Solar** | Planetas, Sol e Lua com fase geométrica; trajetórias anuais, oposições e elongações máximas |
| 🌑 | **Eclipses** | Previsão de eclipses solares e lunares, com a visibilidade calculada para o seu local |
| 📋 | **Planejamento** | Dez tipos de roteiro — maratonas Messier e Caldwell, destaques do mês e da estação, melhores objetos da noite |
| 🗺️ | **Cartas de campo** | PDF com checklist e uma carta de localização por objeto: setas, distâncias em graus e rota de star-hopping |
| 📷 | **Astrofotografia** | Simulador de enquadramento (inclusive Seestar S50/S30), zona de influência da Lua e rastreamento noturno |
| 🖨️ | **Impressão** | Mapas anotáveis à mão livre, exportáveis em PNG, PDF e SVG |

<div align="center">
<img src="docs/imagens/tela-principal.png" alt="Tela principal do Carina" width="90%">
<br><em>Sagitário e o centro da Via Láctea, com as imagens do levantamento DSS sobrepostas</em>
</div>

---

## Instalação rápida

### Windows — executável pronto

Abra a pasta `Carina` e execute **`Carina.exe`**. Não é preciso instalar
Python nem baixar catálogos: **tudo já vem embutido** e funciona
offline, inclusive as efemérides e as imagens dos objetos.

### A partir do código

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m carina
```

O guia completo — preparação dos dados, Linux, macOS e build do
executável — está em **[docs/INSTALACAO.md](docs/INSTALACAO.md)**.

---

## Primeiros cinco minutos

1. **Diga onde você está** — `Ctrl+L` e escolha sua cidade entre as 745
   disponíveis. Todos os horários passam a ser os do seu fuso.
2. **Ajuste o céu ao seu quintal** — *Exibir → Poluição luminosa* e
   escolha sua classe de Bortle. O céu na tela passa a mostrar o que
   você realmente enxerga daí.
3. **Peça um plano** — *Planejar → Visual → Melhores Objetos da Noite*.
4. **Leve para o campo** — na janela do plano, `Ctrl+Shift+V`
   pré-visualiza e `Ctrl+P` gera o PDF com as cartas de busca.

O passeio guiado completo está em
**[docs/PRIMEIROS_PASSOS.md](docs/PRIMEIROS_PASSOS.md)**.

---

## Documentação

Toda a documentação de uso está na pasta **[`docs/`](docs/)**:

| Documento | Para quem quer… |
|---|---|
| **[Instalação](docs/INSTALACAO.md)** | instalar no Windows, Linux ou macOS — ou compilar o próprio executável |
| **[Primeiros passos](docs/PRIMEIROS_PASSOS.md)** | um passeio guiado da primeira abertura até a primeira noite planejada |
| **[Funcionalidades](docs/FUNCIONALIDADES.md)** | conhecer tudo o que o programa faz, recurso por recurso |
| **[Interface](docs/INTERFACE.md)** | a referência completa: cada menu, botão e painel |
| **[Planejamento de observação](docs/PLANEJAMENTO.md)** | dominar as maratonas, os roteiros e as cartas de busca |
| **[Observação e astrofotografia](docs/ASTROFOTOGRAFIA.md)** | enquadrar com seu equipamento, fugir da Lua e rastrear alvos |
| **[Catálogos e dados](docs/CATALOGOS.md)** | saber de onde vêm os dados e como criar seus próprios objetos |
| **[Impressão e exportação](docs/IMPRESSAO.md)** | gerar cartas, mapas anotados e PDFs |
| **[Atalhos de teclado](docs/ATALHOS.md)** | uma folha de referência para imprimir |
| **[Solução de problemas](docs/SOLUCAO_DE_PROBLEMAS.md)** | resolver travamentos, dados faltando e dúvidas frequentes |
| **[Glossário](docs/GLOSSARIO.md)** | destrinchar magnitude, azimute, Bortle, star-hopping e afins |

---

## Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| **Sistema** | Windows 10, Linux ou macOS | Windows 11 |
| **Python** (só para rodar do código) | 3.12 | 3.14 |
| **Gráficos** | OpenGL 3.3 | GPU dedicada |
| **Memória** | 4 GB | 8 GB |
| **Disco** | 400 MB | 500 MB |

O executável embarca tudo e **não exige Python instalado**.

---

## Qualidade

Precisão astronômica é o compromisso central do projeto — cada cálculo é
conferido contra fontes independentes:

- **130 testes automatizados** cobrindo projeção, efemérides, eclipses,
  crepúsculos, rastreamento, planejamento e renderização;
- **eclipses** validados contra o cânone da NASA: datas, tipos e
  magnitudes de 2026–2028 batem exatamente;
- **oposição de Marte** em 20/02/2027 e elongações de Vênus entre 40° e
  48°, coerentes com as efemérides publicadas;
- **alinhamento da Via Láctea** verificado estrela a estrela contra o
  catálogo — erro mediano de cerca de um pixel de textura;
- **altitudes e horários** conferidos contra varreduras finas
  independentes, com erro de 0,003°.

```bash
.venv/Scripts/python -m pytest tests -q
```

---

## Como contribuir

O projeto está em desenvolvimento ativo, e o retorno de quem observa de
verdade é o mais valioso — principalmente:

- **erros de céu**: algo fora de lugar, horário estranho, objeto ausente;
- **usabilidade**: o que atrapalhou na hora de usar no escuro, no campo;
- **listas curadas**: objetos que faltam nos roteiros do mês e da estação.

Ao relatar um problema, ajuda muito informar a **versão**, a **cidade
configurada**, a **data e hora simuladas** e, se possível, uma captura
de tela (`Ctrl+S` exporta a vista atual).

---

## Créditos e dados

O Carina se apoia em dados públicos de astronomia, todos com atribuição:

- **HYG v4.1** e **ATHYG v3.2** — catálogos estelares
- **OpenNGC**, **VizieR** e **SIMBAD** (CDS) — objetos de céu profundo
- **JPL DE440s** — efemérides do Sistema Solar
- **ESO / S. Brunier** — panorâmica da Via Láctea (CC BY 4.0)
- **DSS2 color via hips2fits** (CDS) — imagens dos objetos
- **GeoNames** — base de cidades (CC BY 4.0)
- **d3-celestial** — traçados e limites das constelações

A lista completa, com licenças e o que foi feito com cada fonte, está
detalhada na documentação de dados do projeto.

Nenhum código ou dado do Stellarium (GPL) foi utilizado — o Carina é um
projeto independente e permanece sob licença MIT.

---

## Licença

**MIT.** Os **dados de terceiros** mantêm suas próprias licenças,
listadas acima e detalhadas em [docs/CATALOGOS.md](docs/CATALOGOS.md).

---

<div align="center">
<sub>Feito para o <b>Astronomia no Quintal</b> — céu limpo e boas observações 🔭</sub>
</div>
