---
key: conhecendo-o-carina
title: Conhecendo o Carina
subtitle: O essencial do programa em oito passos — o tour completo vem na versão 1.0
category: iniciante
level: 1
minutes: 6
when: inicio_da_noite
tags: programa, interface, primeiros passos
author: Carina
---

## O céu do seu local, agora
@kind: intro
@target: altaz:180,40
@skip_if_below: -90
@fov: 90

O Carina mostra o céu **do lugar e da hora** escolhidos — por padrão, o seu local e o agora; este tour começa no início desta noite. Arraste com o mouse para olhar em volta; a **roda** aproxima e afasta. O campo de visão atual aparece no canto da barra de estado ("FOV").

Este tour mostra o essencial em oito passos. Ao sair, tudo volta como estava.

## As camadas
@target: altaz:180,40
@skip_if_below: -90
@fov: 90
@layers: grid_altaz=1, const_lines=1, dso=1

A barra à esquerda liga e desliga o que aparece: estrelas, planetas, céu profundo, Via Láctea, linhas das constelações, grade e solo. O menu **Exibir** tem mais — fronteiras das constelações, eclíptica, rótulos — e cada camada tem uma tecla: **C** para as linhas das constelações, **G** para o solo, **M** para a Via Láctea.

Os asterismos, como as Três Marias e o Bule, ficam em *Exibir ▸ Linhas e grades* (`Shift+A`).

## O relógio
@target: altaz:90,30
@skip_if_below: -90
@fov: 90
@time: +3h

O céu gira com o tempo. A régua da noite, embaixo, mostra o crepúsculo e a noite escura; clique nela para mudar a hora. Os botões **Voltar** e **Avançar** dão saltos, e **Agora** volta ao tempo real.

Neste passo o relógio avançou três horas: repare como as estrelas do leste subiram. Clicar na hora, na barra de estado, permite escolher qualquer data.

## Buscar
@target: star:Sirius
@skip_if_below: -90
@fov: 40

**Buscar** (`Ctrl+F`) acha qualquer coisa pelo nome: estrelas ("Sirius", "alfa cen"), objetos ("M 42", "Caixinha de Joias"), constelações, asterismos e planetas. Enter leva o céu até lá; `Ctrl+Enter` guarda na sua lista.

A busca já mostra a altura agora e a nota da noite de cada resultado.

## A ficha do objeto
@target: dso:M 42
@skip_if_below: -90
@time: melhor
@fov: 4

Um clique num objeto abre a **ficha** à direita: o que é, a nota de observabilidade desta noite, nascer e ocaso, o gráfico de altura, a posição e o que esperar ver com o seu instrumento.

Os botões da ficha centralizam, seguem o objeto, mostram a melhor hora, enquadram com o seu equipamento e marcam como observado no diário.

## O botão direito
@target: const:Ori
@skip_if_below: -90
@time: melhor
@fov: 45

O botão direito no céu é um atalho para quase tudo: num objeto, rastrear pela noite, ir à melhor hora, acrescentar à lista ou à sessão de astrofoto; no céu vazio, **"Qual constelação é esta?"** — que destaca a constelação e mostra a história dela na ficha.

## Planejar
@target: altaz:180,50
@skip_if_below: -90
@fov: 100

O menu **Planejar** reúne o que ajuda a preparar a noite: **Hoje à noite** (tecla `T`), com os melhores alvos; o **Calendário do céu**, com eclipses, chuvas de meteoros e encontros; os **roteiros**, que montam a sequência de observação com cartas de localização; e, para quem fotografa, a **Sessão de astrofoto** e o **Campo de visão**.

## E agora?
@kind: fim
@target: altaz:180,45
@skip_if_below: -90
@fov: 100

A ajuda completa fica em `F1`; os atalhos, em `Ctrl+Shift+K`. Os outros tours estão em **Tours ▸ Galeria** (`Ctrl+Shift+T`).

Para começar a aprender o céu, o próximo tour sugerido é **Como se orientar no céu**.
