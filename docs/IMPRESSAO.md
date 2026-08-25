# Impressão e exportação

> Carina 0.13.2 — produto em desenvolvimento.

Tudo o que o Carina desenha pode sair da tela: em imagem, em PDF ou em
papel.

---

## Modo mapa

`Ctrl+M` ou o botão de mapa na barra lateral.

Inverte o esquema de cores: **traços escuros sobre fundo branco**, como
num atlas impresso. Estrelas viram pontos pretos dimensionados pelo
brilho; as linhas ficam finas e escuras.

Neste modo, as **imagens do levantamento não são desenhadas** — elas
ficariam pretas no papel e gastariam tinta sem informar nada.

---

## Exportar a vista

`Ctrl+S` (*Arquivo → Exportar vista*).

Salva exatamente o que está na tela, em **PNG**, **JPG** ou **PDF**. No
PDF, a orientação (retrato ou paisagem) acompanha o formato da janela e
a imagem é centrada na página.

Combine com o modo mapa para gerar uma carta limpa para impressão.

---

## Gerador de mapas anotados

`Ctrl+Shift+P` (*Ferramentas → Gerar mapa para impressão*).

Abre um editor com a vista atual já em modo carta, onde você **anota à
mão livre** antes de imprimir.

### As ferramentas

| Ferramenta | Uso |
|---|---|
| **Selecionar** | Clique numa anotação para movê-la; `Del` apaga |
| **Texto** | Clique e digite — para nomear alvos, anotar horários |
| **Seta** | Arraste da origem ao destino |
| **Linha** | Reta simples |
| **Retângulo** | Delimita uma região |
| **Elipse** | Circunda um objeto ou campo |
| **Desenho livre** | Traço à mão, para contornos e caminhos |

Cada anotação tem **cor**, **espessura** e, no caso do texto, **fonte**
próprias — escolhidas antes de desenhar e alteráveis depois.

### Imprimir e exportar

- **Imprimir** abre o diálogo do sistema, com escolha de impressora,
  papel e margens;
- **Exportar** salva em **PNG**, **PDF** ou **SVG**.

O SVG é vetorial: as anotações continuam editáveis em Inkscape ou
Illustrator, útil para preparar material didático.

> Céu e anotações passam pelo mesmo caminho de renderização, então o que
> você vê na tela é exatamente o que sai no papel.

---

## PDF dos roteiros

Descrito em detalhe em [PLANEJAMENTO.md](PLANEJAMENTO.md).

Na janela de qualquer plano:

- **`Ctrl+Shift+V`** — pré-visualiza o PDF gerado, com rolagem contínua
  e três níveis de zoom (largura, página inteira, tamanho real);
- **`Ctrl+P`** — salva o arquivo.

O documento traz o **checklist** com caixas de marcação e **um cartão por
objeto** com a carta de localização.

---

## Exportação do rastreamento

Na janela de rastreamento (`Ctrl+R`), *Arquivo → Exportar*:

| Formato | Quando usar |
|---|---|
| **PNG** | Uso geral, com fundo transparente preservado |
| **JPG** | Quando o tamanho do arquivo importa |
| **PDF** | Impressão em retrato, carta centrada |
| **SVG** | Edição posterior em vetor |

A imagem sai **quadrada**, porque a carta é redonda.

Antes de exportar, ajuste em *Configurações*: o **tamanho da fonte** (até
2,5×, para cartazes ou para leitura no escuro), a **posição da legenda**
e o **tema claro**, que economiza tinta.

---

## Dicas para impressão

**Use o tema claro** nas cartas de rastreamento que forem para o papel —
o tema escuro consome muita tinta e as linhas finas somem.

**Aumente a fonte** para 1,4× ou 1,6× em material que será lido no campo,
sob luz vermelha: o que é confortável no monitor fica pequeno demais no
escuro.

**Não economize páginas** no PDF dos roteiros. O texto é medido antes de
desenhado justamente para nunca se sobrepor, e um cartão por página
sobrando é melhor que um roteiro ilegível.

**Plastifique ou use saco plástico** — orvalho é o inimigo natural do
papel no campo.
