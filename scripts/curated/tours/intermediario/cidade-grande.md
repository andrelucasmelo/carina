---
key: cidade-grande
title: Astronomia na cidade grande
subtitle: O que dá para ver sob as luzes da cidade, em cada estação — e o binóculo como aliado
category: intermediario
level: 2
minutes: 20
when: inicio_da_noite
tags: poluição luminosa, Bortle, cidade, binóculo, estações
author: Carina / Astronomia no Quintal
---

## O céu de uma cidade grande
@kind: intro
@target: altaz:180,45
@fov: 110
@bortle: 9
@layers: const_lines=1, const_names=1, asterisms=1, dso=0, grid_altaz=0
@skip_if_below: -90

O céu agora está simulado em **Bortle 9**, o do centro de uma metrópole: só as estrelas mais brilhantes sobrevivem, e a Via Láctea some. A escala de Bortle vai de 1 (céu perfeito, longe de tudo) a 9.

Pelo mapa de luzes noturnas da NASA, o céu em **{local}** tem brilho de cerca de **{sqm_local} mag/arcsec²** — algo como **Bortle {bortle_local}**. Quanto menor esse número, mais claro o fundo do céu.

## O que sobra a olho nu
@kind: pause
@target: altaz:180,45
@fov: 110
@skip_if_below: -90

Num céu de cidade grande, a magnitude-limite fica entre 3 e 4: em vez de milhares de estrelas, algumas dezenas. Parece pouco, mas é justamente o que torna as constelações principais **mais fáceis** de reconhecer — as estrelas fracas, que confundem, somem.

Nos próximos passos o relógio vai a uma noite típica de cada estação para mostrar as figuras que resistem à luz da cidade.

## Verão: Órion e o Hexágono
@target: const:Ori
@time: data:01-15 hora:21:30
@fov: 90
@highlight: asterism:tres-marias, asterism:hexagono
@skip_if_below: -90

Em janeiro, a cidade tem o seu melhor céu: as **Três Marias** e o grande retângulo de Órion aparecem mesmo entre prédios, e em volta delas o **Hexágono de Verão** — Sirius, Procyon, Pollux, Capella, Aldebaran e Rigel, seis estrelas que vencem qualquer poste.

Comece sempre pelas Três Marias: dali se chega a Sirius de um lado e a Aldebaran do outro.

## Outono: o Cruzeiro e os Guardiões
@target: const:Cru
@time: data:04-15 hora:20:30
@fov: 60
@highlight: asterism:cruzeiro, asterism:apontadores
@skip_if_below: -90

Em abril, o **Cruzeiro do Sul** passa alto e é visível no céu de qualquer cidade brasileira — a Intrometida, a quinta estrela, já é mais difícil. Os **Guardiões**, Alfa e Beta do Centauro, são das estrelas mais brilhantes do céu e confirmam a cruz verdadeira.

A leste, **Spica** e **Arcturus** completam o céu de outono da cidade.

## Inverno: o Escorpião
@target: const:Sco
@time: data:07-15 hora:20:00
@fov: 70
@highlight: asterism:ferrao, asterism:cabeca-escorpiao
@skip_if_below: -90

Em julho, o **Escorpião** passa quase sobre a cabeça, com **Antares** vermelha no coração. Na cidade, a cauda aparece incompleta, mas a curva é inconfundível. A leste, o **Bule de Sagitário** se mantém, mesmo sem a Via Láctea que sai do bico.

Nas noites de inverno, mais secas, o céu da cidade costuma estar mais limpo.

## Primavera: Fomalhaut e as estrelas solitárias
@target: star:Fomalhaut
@time: data:10-15 hora:21:00
@fov: 80
@highlight: const:PsA
@skip_if_below: -90

Em outubro, o céu da cidade fica quase vazio: o alto é ocupado por constelações de estrelas fracas. Sobram poucas referências — **Fomalhaut**, solitária no alto; **Achernar**, ao sul; e, ao norte, os cantos do **Grande Quadrado de Pégaso**, que às vezes resistem.

É a estação de olhar os **planetas** e a **Lua**, que não se importam com a poluição luminosa.

## O que é a poluição luminosa
@kind: pause
@target: altaz:0,10
@fov: 110
@skip_if_below: -90

A luz que escapa para cima — de postes sem cúpula, fachadas, anúncios — é espalhada pelo ar e acende o próprio céu. Um poste mal direcionado ilumina o céu a dezenas de quilômetros: por isso cidades inteiras aparecem como domos de luz no horizonte, mesmo vistas do campo.

Além de esconder as estrelas, a luz à noite desorienta aves e insetos e atrapalha o sono das pessoas.

## Como melhorar o seu céu
@kind: pause
@target: altaz:180,60
@fov: 110
@skip_if_below: -90

- **Esconda as luzes diretas**: um muro, uma árvore ou o próprio prédio entre você e os postes ajudam muito.
- **Dê tempo aos olhos**: 15 a 20 minutos no escuro, sem olhar a tela do celular (ou com o modo noturno vermelho do Carina, `Ctrl+N`).
- **Olhe para o alto**: perto do zênite o céu é mais escuro que no horizonte.
- **Escolha a hora**: depois da meia-noite muitas luzes se apagam.
- **Use o binóculo**: ele junta muito mais luz que o olho.

## O binóculo na cidade
@kind: intro
@target: altaz:180,50
@fov: 110
@skip_if_below: -90

Um binóculo 10×50 ou 7×50 é o melhor instrumento para começar na cidade: leve, sem montagem e com um campo largo, de uns 6°. O círculo laranja que aparece a seguir mostra esse campo.

Os próximos passos visitam alvos que funcionam mesmo sob céu claro — os que estão no céu desta noite. Apoie os cotovelos ou encoste num muro: a imagem treme menos.

## A Lua
@target: body:Lua
@time: melhor
@fov: 8
@fov_circle: 6

O melhor alvo para binóculo em qualquer céu. Com o Sol iluminando de lado — fora da Lua cheia —, as crateras perto da linha entre o dia e a noite aparecem cheias de sombras. Repare também nos mares escuros, que formam o "rosto" da Lua.

## Júpiter e as luas de Galileu
@target: body:Júpiter
@time: melhor
@fov: 8
@fov_circle: 6

Com o binóculo bem apoiado, Júpiter mostra até quatro pontinhos em linha: **Io, Europa, Ganimedes e Calisto**, as luas que Galileu descobriu em 1610. Elas mudam de posição de uma noite para outra — vale desenhar o que vê.

## As Plêiades
@target: dso:M 45
@time: melhor
@fov: 8
@fov_circle: 6
@image: dss:M 45

A olho nu, na cidade, talvez só três ou quatro estrelas; ao binóculo, as **Plêiades** voltam a ser um aglomerado cheio de estrelas azuladas. Cabem inteiras no campo — é o alvo perfeito para ele.

## As Híades e Aldebaran
@target: dso:Mel 25
@time: melhor
@fov: 8
@fov_circle: 6

O **V do Touro** é grande demais para o telescópio e ideal para o binóculo: dezenas de estrelas, várias duplas, e Aldebaran alaranjada na ponta.

## A Nebulosa de Órion
@target: dso:M 42
@time: melhor
@fov: 8
@fov_circle: 6
@image: dss:M 42

Mesmo na cidade, o binóculo mostra a **Nebulosa de Órion** como uma mancha clara em volta das estrelas da espada. É uma das poucas nebulosas que resistem à luz urbana.

## O Presépio
@target: dso:M 44
@time: melhor
@fov: 8
@fov_circle: 6
@image: dss:M 44

Invisível a olho nu na cidade, o **Presépio** aparece ao binóculo como uma nuvem de estrelas entre Gêmeos e o Leão — com o campo do binóculo, ele fica todo no círculo.

## Ômega Centauri
@target: dso:NGC 5139
@time: melhor
@fov: 8
@fov_circle: 6
@image: dss:NGC 5139

Uma bola de luz difusa no Centauro: **Ômega Centauri**, o maior aglomerado globular da Galáxia. Na cidade aparece pequeno, mas inconfundível — bem diferente de uma estrela.

## M 7, no ferrão do Escorpião
@target: dso:M 7
@time: melhor
@fov: 8
@fov_circle: 6
@image: dss:M 7

Perto do ferrão do Escorpião, **M 7** é um punhado de estrelas brilhantes que o binóculo separa bem, mesmo com o céu claro.

## As Plêiades do Sul
@target: dso:IC 2602
@time: melhor
@fov: 8
@fov_circle: 6

Junto da Quilha, perto do Cruzeiro, um aglomerado de estrelas azuladas parecido com as Plêiades, mas maior: **IC 2602**, as **Plêiades do Sul**. Ao binóculo, a sensação é a de uma joia no meio da Via Láctea.

## Bons céus, mesmo na cidade
@kind: fim
@target: altaz:180,60
@fov: 110
@skip_if_below: -90

A cidade esconde muito, mas não tudo: as constelações principais, a Lua, os planetas e uma dúzia de objetos ao binóculo dão anos de observação. Quando puder, compare com um céu escuro — no Carina, desligue a atmosfera (`A`) para ver o céu sem poluição.

O tour **O céu ao binóculo** monta uma lista de alvos para a estação em que você está.
