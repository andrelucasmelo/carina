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
| **Roda** do mouse | Aproxima e afasta (campo de 0,25° a 100°) |
| **Clique** | Seleciona o objeto — ou o rótulo — mais próximo |
| **Clique direito** | Menu de contexto do objeto sob o cursor |
| **`Esc`** | Cancela a seleção |

O clique tem prioridades: corpos do Sistema Solar primeiro, depois
rótulos, depois estrelas e objetos de céu profundo.

### Menu do botão direito

- **Informações de X** — ficha em janela flutuante, atualizada ao vivo
- **Janela de detalhes de X** — imagem grande e gráfico anual de altitude
- **Selecionar e centralizar** — leva a câmera até o objeto
- **Rastrear na noite** — abre o rastreamento noturno
- **Centralizar aqui** — centra no ponto clicado, sem selecionar nada
- **Medir a partir daqui** — inicia uma medição angular
- **Limpar seleção**

---

## Barra lateral

De cima para baixo:

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

### Arquivo

| Item | Atalho | O que faz |
|---|---|---|
| Exportar vista… | `Ctrl+S` | Salva a tela atual em PNG, JPG ou PDF |
| Sair | | Fecha o programa |

### Tempo

| Item | Atalho | O que faz |
|---|---|---|
| Agora | `8` | Volta ao instante presente, em velocidade normal |
| Pausar / continuar | `K` | Congela ou retoma o relógio |
| Mais devagar | `J` | Divide a velocidade por 10 (e inverte, se insistir) |
| Mais rápido | `L` | Multiplica a velocidade por 10 |
| Velocidade normal | `7` | Volta a 1× |
| Ir para data/hora… | `Ctrl+T` | Salta para um instante, na **hora do observador** |
| Passo dos botões | | De 1 minuto a 1 ano |
| Retroceder / avançar | `Ctrl+←` `Ctrl+→` | Um passo para trás ou para frente |

### Exibir

**Camadas** — cada uma com seu atalho de uma tecla:

| Camada | Tecla | Camada | Tecla |
|---|---|---|---|
| Planetas, Sol e Lua | `P` | Via Láctea | `M` |
| Objetos de céu profundo | `D` | Linha do horizonte | `H` |
| Zona de influência da Lua | `U` | Solo opaco | `G` ou `V` |
| Linhas das constelações | `C` | Pontos cardeais | `Q` |
| Fronteiras das constelações | `B` | Nomes das estrelas | `N` |
| Grade horizontal | `Z` | Imagens DSS no céu | `I` |
| Grade equatorial | `E` | Atmosfera | `A` |
| | | Refração atmosférica | `R` |

Sem atalho: Estrelas, Meridiano local, Eclíptica, Equador celeste,
Nomes dos planetas e Rótulos do céu profundo.

**Rótulos**: estrelas por nome próprio ou por designação de Bayer; céu
profundo por número de catálogo ou por nome.

**Magnitude máxima das estrelas**: *Automática (pelo zoom)* — o padrão —
ou um teto fixo de 3,0 a 12,0.

**Nomes das constelações**: não exibir, português, latim oficial ou
abreviação IAU.

**Poluição luminosa (Bortle)**: as nove classes, de "céu perfeito" a
"centro de cidade".

**Modo mapa para impressão** (`Ctrl+M`) e a exibição dos painéis
*Informações* e *Ferramentas*.

### Céu profundo

| Item | Atalho | O que faz |
|---|---|---|
| Gerenciar objetos e catálogos… | `Ctrl+D` | CRUD completo, categorias, habilitar/desabilitar |
| Configurar catálogos exibidos… | `Ctrl+Shift+C` | Liga e desliga catálogos inteiros |
| Detalhes do objeto selecionado… | `Ctrl+Shift+D` | Imagem grande e gráfico anual |
| Rotular Caldwell pela designação C | | "C 14" em vez de "NGC 7000" |

### Ferramentas

| Item | Atalho | O que faz |
|---|---|---|
| Buscar objeto… | `Ctrl+F` | Busca unificada com ir-para |
| Eclipses… | `Ctrl+E` | Previsão de eclipses solares e lunares |
| Campo de visão (equipamentos)… | `Ctrl+K` | Simulador de enquadramento |
| Rastrear objeto na noite… | `Ctrl+R` | Carta polar da trajetória |
| Caminho dos planetas (365 dias)… | | Traça a trajetória anual |
| Exibir caminhos dos planetas | `Shift+P` | Mostra ou esconde sem recalcular |
| Limpar caminhos dos planetas | | Descarta os caminhos |
| Previsão da Lua (28 dias)… | | Calcula o caminho lunar |
| Exibir previsão da Lua no céu | `Shift+M` | Mostra ou esconde |
| Gerar mapa para impressão… | `Ctrl+Shift+P` | Editor de mapa anotado |

### Planejar

| Item | Atalho | O que faz |
|---|---|---|
| Visual → (dez roteiros) | | Ver [PLANEJAMENTO.md](PLANEJAMENTO.md) |
| Configurar planejamento… | `Ctrl+Shift+O` | Ritmo, janela da noite e altitude mínima |

### Informações · Observador · Ajuda

| Item | Atalho | O que faz |
|---|---|---|
| Crepúsculos e noite… | `Ctrl+I` | Horários do Sol e das três faixas de crepúsculo |
| Objeto selecionado | `Ctrl+J` | Abre o painel lateral de informações |
| Localização… | `Ctrl+L` | Escolha da cidade e coordenadas |
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

Da esquerda para a direita: **local**, **data e hora do observador**,
**velocidade do tempo** (ou "pausado"), **campo de visão** e, quando o
cursor está sobre o céu, o **azimute e a altitude** sob ele.
