# Decisões de arquitetura

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

As decisões que moldaram o Carina, no formato de ADR (*Architecture
Decision Record*), resumidas. Cada uma registra o contexto, a escolha e as
consequências; as marcadas com ★ foram definidas pelo autor do projeto.

## Fundamentos

| ADR | Decisão |
|---|---|
| 001 ★ | **PySide6 + OpenGL.** Qt 6 para toda a interface, céu num `QOpenGLWidget` com OpenGL 3.3 core via PyOpenGL |
| 002 ★ | **Estrelas HYG v4.1**, com espaço para um catálogo profundo depois (veio o ATHYG, ADR-028) |
| 003 ★ | **Português do Brasil**, com `tr()` em todos os textos para traduções futuras |
| 004 ★ · 012 ★ | **Tudo local.** Catálogos, imagens e efemérides embarcados; o que for baixado vira base local permanente |
| 007 | **Dados processados no git, brutos fora**; os scripts regeneram tudo de forma reprodutível |
| 009 | Efeméride DE440s baixada no primeiro uso — revista pela ADR-012: agora embarcada no build |
| 010 ★ | **O nome é Carina**; o repositório mantém o nome original AstroPlanetary |
| 011 | **PyInstaller onedir**: arranque mais rápido que o onefile, dados ao lado do executável |

## O céu

| ADR | Decisão |
|---|---|
| 005 | **Uma matriz por instante**: ICRS→horizontal calculada uma vez e aplicada a todas as estrelas num produto matricial |
| 006 | **Projeção estereográfica** como padrão, a mesma do Stellarium |
| 008 | Polígonos côncavos (isofotas) preenchidos por **stencil**, sem triangulação |
| 014 | Símbolos de céu profundo por classe e contornos elípticos em escala |
| 015 | **Refração de Sæmundsson** só no conteúdo celeste, não nas grades horizontais nem no solo |
| 016 | Lua com fase geométrica; solo por malha com descarte do que está fora da vista |
| 017 · 019 ★ | Via Láctea primeiro por isofotas, depois por **textura na esfera** (panorâmica do ESO, CC BY 4.0, em vez da do Stellarium, GPL) |
| 024 ★ · 025 ★ · 026 ★ | Contornos de nebulosas extraídos do DSS no build; **imagens DSS no céu por mistura aditiva**; manifesto de campo por objeto em destaque |
| 028 | Catálogo profundo pelo **subconjunto Tycho-2 do ATHYG**, deduplicado por proximidade contra o HYG |
| 029 | **Poluição luminosa pela escala de Bortle**: magnitude-limite e brilho de fundo |
| 034 | **Otimizações só com medição** (o `--bench`): cone de visada, cortes por magnitude, caches |
| 038 | Filtro de exibição do céu profundo por máscaras, sem recarregar o banco |
| 039 | `ObjectRef` (referência única a um objeto) e `RenderOptions` (opções de um quadro) |
| 040 | Nomes comuns dos objetos em português, inglês ou latim, por tabela curada |
| 044 | **Render fora da tela**: o mesmo desenho serve à janela, às cartas, ao pôster e ao relatório |
| 045 | Temas escuro, claro (carta) e **vermelho** (modo noturno) aplicados ao quadro inteiro |

## Planejar e observar

| ADR | Decisão |
|---|---|
| 013 | Céu profundo em **SQLite**: o embarcado é só leitura, o usuário edita uma cópia |
| 018 | Eclipses lunares pelo Skyfield; solares pelas luas novas e pelo γ de Meeus |
| 020 · 022 ★ · 023 ★ | Rastreamento noturno numa janela própria, em **carta polar orientada como bússola** |
| 021 | Equipamentos num **JSON editável** do usuário; campo de visão por projeção gnomônica local |
| 027 ★ | Mapa para impressão como imagem com **anotações vetoriais** por cima |
| 030 · 032 | Roteiros ordenados por **quando cada objeto sai de alcance**, não pela melhor altura; maratonas temáticas com ritmo por objeto |
| 031 | Botão direito identifica o objeto **sem mudar a seleção**; ficha em popup |
| 033 | **745 cidades embarcadas** (GeoNames) e todos os horários no fuso do observador |
| 035 | Janela de observação configurável: crepúsculo astronômico, civil, pôr do Sol ou hora fixa |
| 036 | Cartas de localização com **duas ou três estrelas-guia** — para triangular, não só apontar |
| 037 | Banco do usuário versionado e **mesclado ao abrir** quando o embarcado ganha objetos |
| 041 | Uma única medida de **visibilidade** e uma **nota de 0 a 100** explicada, usada em todo o programa |
| 042 | **`carina.sqlite`**: listas, diário, horizontes e perfis num banco do usuário |
| 043 | **Horizonte do quintal**: perfil azimute × altura que o céu, as notas e os roteiros respeitam |

## Sistema Solar, eventos e conteúdo

| ADR | Decisão |
|---|---|
| 046 | **Lua** com textura 8k, relevo, kernels da NAIF (referencial MOON_ME) e 904 formações da IAU |
| 047 | **Motor de eventos** único para o calendário, o "Hoje no céu", os lembretes e o `.ics` |
| 048 | **Planetas**: luas de Júpiter e Saturno pelas efemérides do JPL, orientação IAU, precisão conferida contra o Horizons |
| 049 | **Companheiro no celular** por um servidor HTTP local, sem aplicativo nem nuvem |
| 050 | **Bortle automático** pelo Black Marble da NASA (o atlas de Falchi é CC BY-NC) |
| 051 | **Tours**: um motor para autorais e gerados; o estado do céu é guardado e restaurado por inteiro |
| 052 | Narração dos tours pela voz do Windows, experimental e desligada por padrão |
| 053 | Zona de influência da Lua pelo modelo de **Krisciunas & Schaefer** (1991) |
| 054 | Lembretes pela bandeja do Qt, com o PowerShell como alternativa |
