# Referência da interface

> Carina 0.13.2 — produto em desenvolvimento.

Cada menu, botão e painel, com o que faz e o atalho correspondente.

---

## A janela

```
┌──────────────────────────────────────────────────────────┐
│  Arquivo  Tempo  Exibir  Céu profundo  Ferramentas  …     │ ← menus
├────┬─────────────────────────────────────────┬───────────┤
│ 🔘 │                                          │           │
│ 🔘 │                                          │ Informa-  │
│ 🔘 │              O CÉU                       │  ções     │
│ 🔘 │                                          │ (dock,    │
│ ⋮  │                                          │  opcional)│
├────┴─────────────────────────────────────────┴───────────┤
│  Rio de Janeiro · 24/08/2026 22:00 · pausado · FOV 30°   │ ← estado
└──────────────────────────────────────────────────────────┘
   ↑ barra lateral
```

---

## Mouse e teclado no céu

| Ação | Resultado |
|---|---|
| **Arrastar** com o botão esquerdo | Gira a vista; o ponto sob o cursor acompanha o cursor |
| **Roda** do mouse | Aproxima e afasta **ancorado no ponto sob o cursor** (campo de 0,25° a 100°) |
| **Clique** | Seleciona o objeto — ou o rótulo — mais próximo |
| **Duplo clique** | Centraliza o ponto do céu sob o cursor, com animação |
| **Pairar** o mouse | Tooltip com nome, magnitude e altitude do objeto |
| **Clique direito** | Menu de contexto do objeto, ou do céu vazio |
| **Setas** ← → ↑ ↓ | Deslocam a vista |
| **`+` `−`** (ou `PgUp` `PgDn`) | Aproximam e afastam |
| **`Backspace`** | Volta à vista anterior (as últimas 30 ficam guardadas) |
| **`F`** | Liga e desliga **Seguir objeto**: a câmera acompanha a seleção enquanto o tempo corre (desliga sozinho ao arrastar) |
| **`Esc`** | Cancela a seleção |

O clique tem prioridades: corpos do Sistema Solar primeiro, depois
rótulos, depois estrelas e objetos de céu profundo. Ao centralizar um
objeto que está **abaixo do horizonte**, uma faixa no alto do céu avisa
e diz a hora em que ele nasce.

### Menu do botão direito

**Sobre um objeto**

- **Informações de X** — ficha em janela flutuante, atualizada ao vivo
- **Janela de detalhes…** — imagem grande e gráfico anual de altitude
- **Selecionar e centralizar** · **Seguir X** · **Rastrear na noite…**
- **Ir para a melhor hora desta noite** — salta o relógio para a maior
  altitude com céu escuro nas próximas 24 h (e pausa)
- **Ir para quando nasce** — aparece quando o objeto está sob o horizonte
- **Enquadrar com equipamento…** — abre o simulador de campo centrado nele
- **Copiar nome** · **Copiar coordenadas** (AR/Dec J2000 e Az/Alt atuais)

**Sobre o céu vazio**

- **Qual constelação é esta?** — destaca por alguns segundos as linhas e
  a fronteira da constelação sob o cursor e diz o nome
- **Centralizar aqui** · **Zoom aqui** · **Medir a partir daqui**
- **Olhar para** ▸ Norte, Leste, Sul, Oeste, Zênite
- **Camadas** ▸ interruptores rápidos (estrelas, planetas, céu profundo,
  imagens, Via Láctea, linhas, fronteiras, grades, solo)
- **Agora** · **Limpar seleção**

---

## Barra lateral

De cima para baixo (com *Exibir ▸ Rótulos na barra lateral* cada botão
ganha um texto curto embaixo do ícone):

### Camadas (botões que acendem quando ativos)

| Botão | Camada |
|---|---|
| Estrelas | Liga e desliga todas as estrelas |
| Sistema Solar | Sol, Lua e planetas |
| **Céu profundo** | Marcações **e** imagens, juntas (controle mestre) |
| Via Láctea | A textura de fundo |
| Constelações | As linhas das figuras |
| Grade horizontal | Círculos de altitude e azimute |
| **Solo opaco** | Marcado: solo; desmarcado: vê abaixo do horizonte |

> O botão de céu profundo é um **mestre**: apaga marcações e imagens de
> uma vez. No menu *Exibir*, as duas são independentes — dá para ver a
> imagem da nebulosa sem os círculos por cima.

### Tempo

**◀◀** retrocede um passo · **▶▶** avança um passo · **🕐** volta ao agora.
O tamanho do passo sai de *Tempo → Passo dos botões*.

### Ferramentas

| Botão | Função |
|---|---|
| Medir | Clique em dois pontos para medir a separação angular |
| Zoom por área | Arraste um retângulo para enquadrar |
| Modo mapa | Alterna para o esquema de impressão |
| Previsão da Lua | Liga e desliga o caminho lunar de 28 dias |
| Buscar | Abre a busca |
| Rastrear | Rastreamento noturno do objeto selecionado |
| Campo de visão | Simulador de enquadramento |
| Planejar | Escolha rápida de um roteiro |
| Imprimir | Gerador de mapas anotados |
| Informações | Crepúsculos e noite |

---

## Barra de menus

Oito menus, agrupados por tarefa. A lista completa de atalhos está em
[ATALHOS.md](ATALHOS.md) e em *Ajuda ▸ Atalhos do teclado e do mouse*.

### Arquivo

| Item | Atalho | O que faz |
|---|---|---|
| Exportar vista… | `Ctrl+S` | Salva a tela atual em PNG, JPG ou PDF |
| Gerar mapa para impressão… | `Ctrl+Shift+P` | Editor de mapa anotado |
| Sair | | Fecha o programa |

### Exibir

Quatro submenus de camadas e os controles gerais da vista.

| Submenu | Conteúdo |
|---|---|
| **Objetos** | Estrelas · Planetas, Sol e Lua (`P`) · Objetos de céu profundo (`D`) · Imagens DSS (`I`) · Via Láctea (`M`) |
| **Linhas e grades** | Linhas (`C`) e fronteiras (`B`) das constelações · Grade horizontal (`Z`) · Grade equatorial (`E`) · Meridiano · Eclíptica · Equador · Linha do horizonte (`H`) · Pontos cardeais (`Q`) |
| **Rótulos** | Nomes das estrelas (`N`), dos planetas e do céu profundo · estrelas por nome próprio ou Bayer · céu profundo por número ou nome · Caldwell pela designação C · **Nomes das constelações** (não exibir, português, latim, abreviado) · **Idioma dos nomes dos objetos** (português, inglês original, latim) |
| **Céu** | Atmosfera (`A`) · Refração (`R`) · Solo opaco (`G`/`V`) · **Poluição luminosa (Bortle)** · **Magnitude máxima das estrelas** |

Abaixo dos submenus: **Filtros do céu profundo…** (`Ctrl+Shift+C`, ver
[CATALOGOS.md](CATALOGOS.md)), **Modo mapa para impressão** (`Ctrl+M`),
**Seguir objeto selecionado** (`F`), **Voltar à vista anterior**
(`Backspace`), **Rótulos na barra lateral** e a exibição dos painéis.

### Tempo

| Item | Atalho | O que faz |
|---|---|---|
| Agora | `8` | Volta ao instante presente, em velocidade normal |
| Pausar / continuar | `K` | Congela ou retoma o relógio |
| Mais devagar / Mais rápido | `J` / `L` | Divide ou multiplica a velocidade por 10 |
| Velocidade normal | `7` | Volta a 1× |
| Ir para data/hora… | `Ctrl+T` | Salta para um instante, na **hora do observador** |
| **Ir para ▸** | | Pôr do sol · Início da noite astronômica · Meia-noite local · Fim da noite astronômica · Nascer do sol (pausa no instante) |
| Passo dos botões | | De 1 minuto a 1 ano |
| Retroceder / avançar | `Ctrl+←` `Ctrl+→` | Um passo para trás ou para frente |

### Local

| Item | Atalho | O que faz |
|---|---|---|
| Localização… | `Ctrl+L` | Escolha da cidade (745 embarcadas) e coordenadas |
| Crepúsculos e noite… | `Ctrl+I` | Horários do Sol e das três faixas de crepúsculo, Lua |

### Objetos

| Item | Atalho | O que faz |
|---|---|---|
| Buscar… | `Ctrl+F` | Busca unificada com ir-para (aceita nomes em português) |
| Informações do objeto selecionado | `Ctrl+J` | Abre o painel lateral |
| Detalhes e gráfico anual… | `Ctrl+Shift+D` | Imagem grande e gráfico anual |
| Rastrear na noite… | `Ctrl+R` | Carta polar da trajetória |
| Ir para a melhor hora desta noite | | Salta o relógio para a maior altitude com céu escuro |
| Ir para quando nasce | | Salta o relógio para pouco depois do nascer |
| Gerenciar catálogo de céu profundo… | `Ctrl+D` | CRUD completo, categorias, habilitar/desabilitar |

### Sistema Solar

| Item | Atalho | O que faz |
|---|---|---|
| Eclipses… | `Ctrl+E` | Previsão de eclipses solares e lunares |
| Caminho dos planetas (365 dias)… | | Traça a trajetória anual |
| Exibir caminhos dos planetas | `Shift+P` | Mostra ou esconde sem recalcular |
| Limpar caminhos dos planetas | | Descarta os caminhos |
| Previsão da Lua (28 dias)… | | Calcula o caminho lunar |
| Exibir previsão da Lua no céu | `Shift+M` | Mostra ou esconde |
| Zona de influência da Lua | `U` | Anéis de prejuízo para astrofotografia |

### Planejar

| Item | Atalho | O que faz |
|---|---|---|
| Roteiros ▸ (dez roteiros) | | Ver [PLANEJAMENTO.md](PLANEJAMENTO.md) |
| Campo de visão (equipamentos)… | `Ctrl+K` | Simulador de enquadramento |
| Configurar planejamento… | `Ctrl+Shift+O` | Ritmo, janela da noite e altitude mínima |

### Ajuda

| Item | Atalho | O que faz |
|---|---|---|
| Documentação | `F1` | Abre esta documentação |
| Atalhos do teclado e do mouse… | `Ctrl+Shift+K` | Tabela pesquisável, lida dos próprios menus |
| Sobre o Carina | | Versão e créditos dos dados |

---

## Painéis e janelas

### Painel de informações (direita)

Mostra a ficha do objeto selecionado, atualizada a cada segundo: nome,
designações, tipo, magnitude, tamanho, constelação, coordenadas J2000 e
a posição **agora** (azimute e altitude). Para objetos de céu profundo,
traz também a miniatura da imagem.

Abra com `Ctrl+J` ou em *Exibir → Informações*.

### Janela de detalhes

Imagem grande, ficha completa e o **gráfico de altitude ao longo do ano**,
amostrado a cada dez dias, com duas curvas:

- **laranja** — a altitude no meio da noite astronômica. O pico é a
  melhor época do ano para o objeto;
- **azul** — a altitude máxima que ele alcança naquela noite.

A barra de estado resume: *"Melhor época: 12/12 — 72° no meio da noite"*.

### Janela de planejamento

Lista do roteiro com horário, objeto, tipo, magnitude, tamanho, altitude,
**instrumento recomendado**, constelação e distância à Lua. Cores:

- **laranja** — o objeto está perto da Lua e será prejudicado;
- **azul** — foi agendado com o céu ainda claro (só entrou por ser
  bem brilhante).

Duplo clique leva ao objeto no mapa. O menu **Configurar** ajusta e
recalcula na hora; **Arquivo** pré-visualiza (`Ctrl+Shift+V`) e exporta
o PDF (`Ctrl+P`).

### Janela de rastreamento

Carta polar do céu — zênite no centro, horizonte na borda — com a
trajetória da noite. Ver [ASTROFOTOGRAFIA.md](ASTROFOTOGRAFIA.md).

---

## Barra de estado

Da esquerda para a direita: **local**, **data e hora do observador** com a
**velocidade do tempo** (ou "pausado"), **campo de visão** e, quando o
cursor está sobre o céu, o **azimute e a altitude** sob ele. Três campos
são clicáveis: o local abre *Localização*, a hora abre *Ir para
data/hora* e o campo de visão volta a 90°. Avisos temporários
(exportações, "objeto abaixo do horizonte, nasce às…") aparecem à
esquerda.
