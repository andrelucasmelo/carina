# Funcionalidades

> Carina 0.15.0 — produto em desenvolvimento.

O que o programa faz, recurso por recurso, e o que esperar de cada um.

---

## O céu

### Estrelas

São **860 mil estrelas** em duas camadas:

- **HYG v4.1** (119.625 estrelas) — a camada principal, com nomes
  próprios, designações de Bayer e Flamsteed e constelação. É a que
  participa dos rótulos, da busca e da seleção;
- **catálogo profundo** (741.189 estrelas, magnitudes 8,5 a 12) —
  derivado do Tycho-2 via ATHYG. São estrelas anônimas que só aparecem
  quando o zoom justifica, para dar textura ao campo.

O **tamanho do ponto cresce com o brilho** de forma acentuada, para que
as estrelas mais brilhantes dominem o campo como fazem no céu real. A
cor vem do índice B−V: azuladas as quentes, alaranjadas as frias.

**Quantas estrelas aparecem** é decidido pelo zoom: quanto mais fechado
o campo, mais fundo se enxerga — como acontece ao trocar por uma ocular
de maior aumento. O menu *Exibir → Magnitude máxima* impõe um **teto** a
esse valor automático, útil para simular um instrumento específico.

### Via Láctea

Uma **panorâmica fotográfica real** (ESO / Serge Brunier) mapeada sobre a
esfera celeste, convertida de coordenadas galácticas para equatoriais e
com as estrelas do próprio levantamento removidas por processamento — o
que sobra é só o brilho difuso, que continua fiel em qualquer zoom.

O alinhamento foi verificado estrela a estrela contra o catálogo: o erro
mediano é de cerca de um pixel de textura.

### Atmosfera e refração

- **Atmosfera** (`A`): o céu clareia ao amanhecer e escurece ao
  anoitecer, passando pelos tons do crepúsculo, e as estrelas somem
  gradualmente com a luz do dia.
- **Refração** (`R`): a atmosfera ergue os astros próximos ao horizonte
  (fórmula de Sæmundsson) — o mesmo efeito que faz o Sol ainda ser visto
  quando geometricamente já se pôs.

### Poluição luminosa (Bortle 1–9)

Simula o céu que você realmente tem. A classe escolhida afeta:

- a **magnitude limite** das estrelas (de 7,8 na classe 1 a 4,0 na 9);
- o **brilho do fundo**, com o tom alaranjado das lâmpadas urbanas;
- o **contraste das imagens** dos objetos;
- a **Via Láctea**, que **desaparece a partir da classe 7**, como na
  realidade.

### Solo, horizonte e grades

Solo opaco, linha do horizonte, pontos cardeais, grade horizontal
(altitude-azimute), grade equatorial, meridiano local, eclíptica e
equador celeste — cada um ligável à parte.

Desmarcando **Solo opaco** (`G` ou `V`), você passa a **ver o céu abaixo
do horizonte**, com a linha divisória marcada — útil para saber o que
está por nascer.

---

## Céu profundo

**18.632 objetos** de onze catálogos:

| Catálogo | Objetos | Conteúdo |
|---|---|---|
| **Messier** | 110 | Os clássicos, sempre rotulados |
| **Caldwell** | 109 | A lista complementar de Patrick Moore |
| **NGC** | 8.442 | O grande catálogo geral |
| **IC** | 5.596 | Index Catalogue |
| **Abell** | 2.712 | Aglomerados de galáxias e planetárias |
| **LDN** | 1.787 | Nebulosas escuras de Lynds |
| **Barnard** | 349 | Nebulosas escuras de Barnard |
| **Sharpless** | 313 | Regiões HII |
| **Collinder** | 171 | Aglomerados abertos |
| **van den Bergh** | 158 | Nebulosas de reflexão |
| **Melotte** | 77 | Aglomerados |

Os quatro últimos acrescentados (LDN, Collinder, vdB e Abell) vêm
**desligados** de fábrica, para não poluir a tela — ligue-os em *Exibir
→ Filtros do céu profundo* (`Ctrl+Shift+C`).

### Filtro de exibição

Uma tela única decide o que aparece no mapa: catálogos, tipos, faixa de
magnitude, faixa de tamanho angular, só nomeados, só Messier/Caldwell e
o tratamento das **regiões gigantes** (Sharpless, Barnard, LDN):
contorno tracejado, só o rótulo, ocultar em campo aberto ou normal.
Presets prontos (Binóculo, Astrofoto de grande campo…) e presets seus.
Os nomes populares aparecem em **português** (ou no inglês original, ou
em latim), inclusive na busca. Ver [CATALOGOS.md](CATALOGOS.md).

### Símbolos e contornos

Cada tipo tem seu símbolo, na convenção dos atlas impressos: elipse para
galáxias, círculo tracejado para aglomerados abertos, círculo com cruz
para globulares, quadrado para nebulosas, e assim por diante. Objetos
grandes ganham uma elipse orientada pelo ângulo de posição real.

Vinte e duas nebulosas famosas têm o **contorno real desenhado**,
extraído das imagens do levantamento, em vez de um círculo genérico.

### Imagens do levantamento

**1.179 imagens reais** do DSS2 color acompanham o programa (cerca de
97 MB), cobrindo todos os Messier e Caldwell, todos os objetos maiores
que 30′ e todas as galáxias maiores que 8′.

Ligadas com **`I`**, elas aparecem **no lugar e no tamanho corretos** — o
enquadramento de cada uma foi registrado no download, então a imagem
casa com as estrelas ao redor. A mistura é aditiva: onde a imagem é
preta, nada é somado, e não aparece o retângulo do recorte.

Com **`D`** você desliga as marcações e fica só com a imagem limpa.

### Gerenciamento

`Ctrl+D` abre o gerenciador: buscar, filtrar, **habilitar ou desabilitar**
objetos, **criar os seus próprios**, editar, excluir e organizar em
**categorias**. Suas edições ficam numa cópia pessoal do banco — uma
atualização do programa não as apaga.

---

## Sistema Solar

Sol, Lua e os oito planetas, calculados com as efemérides **JPL DE440s**
(cobertura de 1849 a 2150).

- O **Sol** é desenhado como disco no tamanho angular real, com halo.
- A **Lua** aparece com a **fase geométrica correta**: o terminadouro é
  calculado do ângulo Sol–Lua–Terra e a orientação do limbo iluminado
  segue o ângulo de posição real.
- Os **planetas** têm magnitude calculada pelo modelo de Mallama.

### Trajetórias anuais

*Ferramentas → Caminho dos planetas* traça o percurso de um planeta
pelos próximos 365 dias sobre o fundo de estrelas, com marcas de data,
trechos retrógrados em tom mais fraco e os eventos anotados:
**oposições**, **conjunções** e **elongações máximas**.

### Previsão da Lua

*Ferramentas → Previsão da Lua* desenha o caminho lunar dos próximos 28
dias, com **o disco na fase de cada dia**, a data, a porcentagem
iluminada e as quatro fases principais destacadas.

### Eclipses

`Ctrl+E` lista eclipses solares e lunares num intervalo de anos, com
tipo, magnitude e — o que importa — **se são visíveis do seu local**,
com a altura do astro no momento do máximo. Um duplo clique leva a
simulação ao instante do eclipse.

---

## Planejamento de observação

Detalhes completos em [PLANEJAMENTO.md](PLANEJAMENTO.md).

- **Hoje à noite** (`T`): crepúsculos, a Lua e as horas escuras sem ela,
  os cinco melhores alvos de céu profundo e os planetas que valem a pena,
  com ir para, melhor hora e roteiro dos melhores.
- **Pontuação de observabilidade**: nota de 0 a 100 para a noite em toda
  ficha, lista, busca e roteiro, com a explicação em português (altitude,
  tempo de janela, Lua e se o objeto aguenta o seu céu).
- **Nasce, culmina e se põe** de qualquer objeto, com a janela útil e a
  melhor hora, e um gráfico da noite na ficha.
- **Horizonte do quintal** (*Local → Horizonte do quintal…*): desenhe a
  silhueta de prédios e árvores sobre o céu do instante; o solo, as notas
  e os roteiros passam a respeitá-la.
- **Roteiros** (*Planejar → Roteiros*): maratonas Messier e Caldwell,
  temáticas, melhores objetos, **roteiro da minha lista**, destaques do mês
  e da estação, estrelas brilhantes.
- **Janela de planejamento**: tabela com designação e nome, nota e janela
  útil; carta de localização e gráfico da noite ao lado; **linha do tempo**
  arrastável; filtros por instrumento, tipo, altitude e Lua; ir para no
  mapa e na hora; reordenar e remover.
- **Calendário de noites escuras** (`Ctrl+Shift+N`): horas sem Lua de cada
  noite do mês, com as três melhores destacadas.
- **PDF de campo** com o mapa da noite (paradas numeradas por direção e altura), checklist e cartas de
  localização, em tema claro, escuro ou vermelho; exportação em CSV e
  texto.

## Diário e listas

Detalhes em [DIARIO.md](DIARIO.md).

- **Minhas listas** (`Ctrl+Shift+L`): várias listas com nome, a nota de
  cada item nesta noite, anotações e roteiro da lista. Acrescente com ★ na
  ficha, no botão direito, `Ctrl+B` ou `Ctrl+Enter` na busca.
- **Diário de observação** (`Ctrl+Shift+J`): registre data, local,
  instrumento, Bortle, seeing, transparência, avaliação e nota; o
  histórico aparece na ficha do objeto; exportação em CSV.

---

## Astrofotografia e equipamento

Detalhes em [ASTROFOTOGRAFIA.md](ASTROFOTOGRAFIA.md).

- **Simulador de enquadramento** (`Ctrl+K`): combine telescópio, câmera
  ou ocular e acessórios, e veja o campo desenhado sobre o céu, como no
  Aladin. Inclui **rotacionador de campo** e os telescópios inteligentes
  **Seestar S50, S30 e S30 Pro**. O acervo traz 67 equipamentos de
  fábrica e aceita os seus.
- **Zona de influência da Lua** (`U`): os anéis que mostram até onde o
  brilho lunar estraga a foto, com raio proporcional à fase.
- **Rastreamento noturno** (`Ctrl+R`): a trajetória do objeto na noite
  numa carta polar, com estilo de linha por faixa de crepúsculo, cores
  por altitude e marcadores de hora. Exporta em PNG, JPG, PDF e SVG.

---

## Impressão e exportação

Detalhes em [IMPRESSAO.md](IMPRESSAO.md).

- **Modo mapa** (`Ctrl+M`): inverte para traços escuros sobre fundo
  branco, próprio para papel;
- **Gerador de mapas** (`Ctrl+Shift+P`): anote livremente sobre a carta —
  textos, setas, formas e desenho à mão — e imprima ou exporte;
- **Exportar vista** (`Ctrl+S`): salva a tela em imagem ou PDF.

---

## Informações e ferramentas

- **Crepúsculos e noite** (`Ctrl+I`): os horários do pôr do sol, das três
  faixas de crepúsculo e do nascer, mais a situação da Lua;
- **Medição angular**: escolha a ferramenta na barra lateral e clique em
  dois pontos para medir a separação;
- **Zoom por área**: arraste um retângulo para enquadrar exatamente;
- **Ficha do objeto**: a mesma no painel lateral, no popup do botão
  direito (que pode ficar no topo) e na janela de detalhes — nota da
  noite, seção Hoje, posição ao vivo (J2000 e da data, ângulo horário,
  massa de ar), o que esperar, distância e tipo espectral das estrelas,
  seu diário e os botões de ação;
- **Busca** (`Ctrl+F`): nomes, designações, **Bayer** em várias grafias
  ("alfa ori", "α Ori", "alpha orionis") e **constelações** (vai ao centro
  e destaca), com a altitude agora e a nota da noite em cada resultado.
- **Navegação**: zoom ancorado no cursor, duplo clique para centralizar,
  setas e `+`/`−`, tooltip ao pairar, **seguir objeto** (`F`), voltar à
  vista anterior (`Backspace`), "Qual constelação é esta?" e "Ir para a
  melhor hora desta noite" no botão direito, barra de estado clicável;
- **Tempo ▸ Ir para**: pôr do sol, noite astronômica, meia-noite,
  amanhecer e nascer do sol com um clique;
- **Persistência**: direção, campo, Bortle, magnitude, rótulos, filtro e
  geometria da janela voltam como você deixou.

---

## O que ainda não existe

Para não criar expectativa errada, na versão 0.15.0 **não há**:

- cometas e asteroides;
- satélites artificiais (ISS, Starlink);
- controle de telescópio (ASCOM, INDI);
- modo de visão noturna (tela vermelha);
- tradução para outros idiomas — a interface é só em português, embora o
  código já esteja preparado para tradução.
