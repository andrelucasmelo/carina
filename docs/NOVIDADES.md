# O que há de novo

> Carina 0.20.0 — produto em desenvolvimento.

## 0.20 — Tours guiados

**Tours** (menu *Tours*, `Ctrl+Shift+T`). O céu passo a passo: o relógio vai
à hora certa, a vista voa até o alvo, a figura se acende e um texto curto
explica. Ao sair, o céu volta exatamente como estava. Nesta versão:

- **Iniciantes**: Como se orientar no céu, As estrelas mais brilhantes de
  hoje, Constelações que todo mundo reconhece, Os famosos do céu profundo,
  A Lua e os planetas desta noite e Conhecendo o Carina;
- **Intermediário**: O céu de primavera e **O céu deste mês**, montado
  para o mês e o seu local;
- **Astrofotografia**: **Objetos do mês para fotografar** — os alvos com
  pelo menos 4 h úteis por noite, em aglomerados, nebulosas e galáxias, na
  ordem em que ficam bons, com o gráfico da noite, as horas de cada noite
  do mês e "+ Sessão".

**Asterismos** (`Shift+A`): Três Marias, Bule de Sagitário, Falsa Cruz,
Hexágono de Verão e outros 14, no céu e na busca.

**Histórias das constelações**: a origem, o mito, como achar do Brasil e
uma curiosidade das 88 constelações, na ficha ao perguntar "Qual
constelação é esta?". Veja [Tours guiados](TOURS.md).

## 0.19.1 — Ajustes da astrofotografia

- **Rótulos que sumiam** com um campo de visão centrado num objeto
  selecionado: estrelas, objetos e pontos cardeais voltam a aparecer.
- **Setups**: botão **Salvar** (grava por cima do setup escolhido), aviso de
  que o setup foi salvo e o Campo de visão volta ao último conjunto usado,
  mesmo sem nome.
- **Telescópio inteligente** nas montagens: modo **Alt-Az** (evita o zênite,
  subs de até 30 s) ou modo **EQ** na cunha (sem flip no meridiano).
- **Sessão de astrofoto**: a lista de setups se atualiza sozinha; botão
  **Campo de visão…** ao lado; **sub-exposição** com o número de subs para a
  meta e uma **margem de perda** por faixa de duração, editável;
  **✨ Sugestões de alvos** com as fotos dos mais bem posicionados da noite;
  linhas de hora e dica ao passar o mouse no gráfico de horas úteis.
- **Botão direito** num objeto: **📷 Adicionar à sessão de astrofotografia**.
- Erros inesperados agora ficam registrados em `erros.log`, na pasta do
  usuário, e aparecem numa mensagem.

## 0.19 — Astrofotografia e companheiro

**Sessão de astrofoto** (`Ctrl+Shift+S`). Os alvos da noite divididos em
blocos de integração, sem atravessar o meridiano numa montagem equatorial
(com o aviso de virar a montagem) e fora da zona do zênite numa altazimutal
como o Seestar. Sub-exposição sugerida para o seu céu, quantas noites para
juntar as horas desejadas e o **calendário de imageabilidade** de cada alvo
no ano. Veja [Astrofotografia](ASTROFOTOGRAFIA.md).

**Campo de visão**: **setups salvos** com nome, **mosaico** N×M no céu,
**"cabe no meu campo?"** na ficha e a imagem na ocular conforme o trem
óptico (marcas N e L).

**Minha foto no mapa**: clique em duas estrelas de uma foto sua e ela é
sobreposta ao céu, alinhada.

**Companheiro no celular**: o roteiro em vermelho no celular, pelo QR code,
com o botão "observado" que vai para o diário. Veja [Companheiro no
celular](CELULAR.md).

**Bortle automático**: ao escolher a cidade, o brilho estimado do céu pelo
mapa de luzes noturnas da NASA.

**ISS e satélites**: importe os elementos orbitais (arquivo da CelesTrak) e
veja as passagens visíveis, com a trilha no céu; o cartão "Hoje no céu" avisa
quando a ISS passa.

## 0.18 — Planetas

**Janela de planetas** (`Ctrl+Shift+E`, ou **Detalhes** na ficha de um
planeta). Os sete planetas com o estado de cada um e o disco como no
telescópio:

- **Mercúrio e Vênus** com a fase do dia e a série de fases dos próximos
  meses, em escala;
- **Marte** com o meridiano central e o disco crescendo até a oposição;
- **Júpiter** com as faixas, a **Grande Mancha Vermelha** na longitude do
  dia e as **quatro luas galileanas como vistas da Terra** — com trânsitos,
  sombras, ocultações e eclipses da noite e as passagens da Mancha pelo centro;
- **Saturno** com os **anéis na inclinação do dia** e as luas, de Titã a Jápeto.

A aba **Melhor época** mostra a temporada de visibilidade no seu céu e as
próximas oposições ou maiores elongações, com a altura que o planeta terá no
seu local. Veja [Os planetas](PLANETAS.md).

**No céu**, os planetas viram discos ao aproximar, e as luas de Júpiter e
Saturno aparecem com nome. **Na ficha**, diâmetro, fase, elongação e melhor
época.

## 0.17.1 — Lua mais leve

- A Lua não trava mais a tela: o globo só é carregado quando ela fica
  grande, a leitura das texturas acontece em segundo plano e a resolução
  máxima só entra no zoom extremo. Enquanto carrega, aparece o disco
  simples.
- **A Lua em detalhe** responde na hora ao arrastar e ao dar zoom; a imagem
  em resolução cheia chega um instante depois, sem bloquear a janela.
- Menos memória: as texturas são liberadas depois de usadas.

## 0.17 — Lua e calendário do céu

**A Lua de verdade.** Ao aproximar, a Lua vira um globo com o relevo da sonda
LRO: terminador com sombras, a libração da noite, a luz cinérea nas fases
finas e os nomes das crateras, mares e montanhas iluminados.

**A Lua em detalhe** (`Ctrl+Shift+M`). Uma janela só para ela: zoom de até
16×, orientação conforme o instrumento (como no céu, norte para cima,
telescópio invertido ou espelhado), a lista do que está **no terminador**
hoje e, para cada formação, as **próximas noites boas** para vê-la.
Veja [A Lua](LUA.md).

**Planejador de foto lunar.** Noite a noite: fase, nascer e ocaso com o
azimute, altura no escuro, o tipo de foto que a fase favorece e quantos
quadros de mosaico o seu conjunto precisa.

**Lunar 100.** Os cem alvos de Charles Wood com descrições em português e o
progresso tirado do diário.

**Calendário do céu** (`Ctrl+Shift+A`). Fases e eventos da Lua (superlua,
Lunar X, Alça Dourada, libração favorável), eclipses, oposições e
elongações, encontros da Lua com planetas e estrelas, **ocultações
visíveis do seu local**, os picos de 25 chuvas de meteoros com a Lua na
noite, noites escuras e estações. Filtros, lembretes e exportação **.ics**
para a agenda do celular; o cartão **Hoje no céu** avisa ao abrir.
Veja [Calendário do céu](CALENDARIO.md).

## 0.16.1 — Ajustes

- **Idioma** no primeiro passo do assistente e nas Preferências.
- **Via Láctea** sem o aspecto quadriculado nos campos amplos.
- **Sem atmosfera, sem poluição luminosa**: desligar a atmosfera mostra o
  céu de Bortle 1; ao religar, volta o seu Bortle.
- **Catálogos inteiros** de uma vez em *Exibir → Objetos → Catálogos do céu
  profundo*.
- **Rastreamento**: traçado branco, Lua em azul, vista do céu, fonte maior,
  horários em negrito com contorno, janela com a altura da tela — e as
  configurações agora ficam salvas.
- **Calendário de noites escuras** no menu *Planejar*, destacando as noites
  com mais de 8 horas sem Lua.

## 0.16 — Carta, beleza e campo

**Cartas celestes para imprimir.** *Arquivo → Gerar carta celeste…*
(`Ctrl+Shift+P`) monta uma carta de verdade: enquadre a vista atual, o
objeto selecionado, uma constelação inteira ou o campo do seu equipamento;
escolha o papel (A4, A3, Carta), o tema (papel, escuro ou vermelho), o que
aparece (estrelas e nomes até uma magnitude, linhas, fronteiras, grades,
Via Láctea, céu profundo com filtro próprio) e a moldura (título, bússola,
escala e legenda). Salve o estilo como perfil e gere um **atlas** com uma
página por parada do roteiro, por item da sua lista ou por constelação.
Veja [Impressão e cartas](IMPRESSAO.md).

**Modo noturno** (`Ctrl+N`). Céu e interface inteiros em vermelho escuro,
sem nenhum azul ou verde, para não perder a adaptação ao escuro.

**No campo.** *Tela cheia* (`F11`); *Modo observação* (`Ctrl+Shift+F`):
painéis escondidos, rótulos maiores e um cartão com o próximo alvo do
roteiro e um cronômetro; e a **linha do tempo da noite** no rodapé — clique
ou arraste para percorrer a noite.

**Um céu mais bonito.** Estrelas com a cor certa pela temperatura, halo nas
mais brilhantes, estrelas que se apagam perto do horizonte como no céu de
verdade, o brilho alaranjado do crepúsculo e a Via Láctea em resolução
maior.

**Primeiros passos e ajuda.** Na primeira abertura, um assistente pede a
cidade, sugere o Bortle e pergunta o seu instrumento. Esta ajuda (`F1`)
agora abre dentro do programa. Em *Local → Locais salvos* você guarda o
quintal, o sítio e a viagem e troca com um clique.

**Preferências** (`Ctrl+,`): tamanho da fonte da interface e dos rótulos
do céu, e o instrumento que a nota da noite considera.

## 0.15 — Informar e planejar

- **Hoje à noite** (`T`): a noite, a Lua e os melhores alvos para o seu céu.
- **Nota de 0 a 100** com explicação em toda ficha, busca, lista e roteiro.
- **Nasce, culmina, se põe** e janela útil de qualquer objeto.
- **Horizonte do quintal**: desenhe prédios e árvores; notas e roteiros
  passam a respeitá-los.
- **Ficha nova**, **busca melhor**, **Minhas listas** e **diário de
  observação**.
- **Nova janela de planejamento** com linha do tempo arrastável,
  **calendário de noites escuras** e **PDF** com mapa da noite e temas.

Detalhes em [Planejamento](PLANEJAMENTO.md) e [Diário e listas](DIARIO.md).
