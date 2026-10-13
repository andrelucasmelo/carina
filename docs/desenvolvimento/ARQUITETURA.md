# Arquitetura

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

## As camadas

```
┌──────────────────────────── ui/ (PySide6) ────────────────────────────┐
│ MainWindow · SkyWidget (QOpenGLWidget) · janelas e diálogos · player  │
│ de tours · modo noturno · ajuda                                       │
└───────────────┬──────────────────────────────────┬────────────────────┘
                │                                  │
     ┌──────────▼──────────┐            ┌──────────▼───────────────────┐
     │ render/             │            │ core/  (sem Qt)              │
     │ GLRenderer (OpenGL  │            │ SkyEngine (Skyfield) · câmera│
     │ 3.3) · temas · Lua e│            │ visibilidade · pontuação ·   │
     │ planetas na CPU ·   │            │ planejamento · Lua · planetas│
     │ molduras de carta   │            │ eventos · tours · userdata   │
     └──────────┬──────────┘            └──────────┬───────────────────┘
                │                                  │
     ┌──────────▼──────────────────────────────────▼───────────────────┐
     │ catalogs/  estrelas (HYG/ATHYG) · céu profundo (SQLite) ·        │
     │ constelações e Via Láctea · nomes · equipamentos · imagens       │
     └──────────────────────────────┬──────────────────────────────────┘
                                    │
                         data/processed/ (embarcado)
```

- **`core/`** não importa o Qt — a única exceção é o certificado em PDF
  (`certificate.py`), que desenha com o QPainter. Toda a astronomia, o
  planejamento e a lógica dos tours vivem aqui e são testados sem interface.
- **`catalogs/`** lê os dados embarcados e oferece arrays prontos para
  desenhar e consultas para a interface.
- **`render/`** desenha: o céu em OpenGL; a Lua e os planetas em detalhe na
  CPU (NumPy) para as janelas próprias; as molduras das cartas.
- **`ui/`** é a casca Qt: janelas, menus, o céu interativo e o player.

## Mapa dos módulos

### core/ — astronomia e lógica

| Módulo | Responsabilidade |
|---|---|
| `engine.py` | Envelope sobre o Skyfield: matriz ICRS→horizontal por instante, posições aparentes do Sistema Solar, relógio da simulação |
| `projection.py` | Câmera e projeção estereográfica vetorizada |
| `localtime.py` · `twilight.py` · `formats.py` | Hora local do observador, crepúsculos e limites da noite, formatação |
| `visibility.py` · `score.py` | Nasce, culmina e se põe; janela útil e melhor hora; nota de observabilidade 0–100 explicada |
| `observing.py` | Roteiros (maratonas) e a rota "como achar" a partir das estrelas |
| `tonight.py` · `dark_nights.py` · `tracking.py` | "Hoje à noite", calendário de noites escuras, trajetória da noite |
| `horizon.py` · `lightpollution.py` · `skybrightness.py` | Horizonte do quintal, Bortle automático, brilho do céu pela Lua |
| `objects.py` · `search.py` · `dsofilter.py` | Referência unificada a um objeto, busca e filtro do céu profundo |
| `moon.py` · `occultations.py` | Geometria lunar (libração, colongitude), formações, terminador, datas boas; ocultações |
| `planets.py` · `satellites.py` · `planetpath.py` · `sunpath.py` | Planetas, luas de Júpiter e Saturno, anéis, Grande Mancha Vermelha; trajetórias; analema |
| `eclipses.py` · `events.py` · `ics.py` · `notify.py` | Eclipses, motor do calendário, iCalendar, lembretes |
| `session.py` · `exposure.py` · `imageability.py` · `photo_align.py` | Sessão de astrofoto, exposição, horas úteis no ano, foto no mapa |
| `tours.py` · `tours_generated.py` · `skystate.py` · `lore.py` · `speech.py` | Tours (esquema, alvos, relógio, execução), tours gerados, estado do céu, histórias das constelações, narração |
| `programs.py` · `certificate.py` · `quiz.py` · `report.py` · `listformats.py` | Programas, certificado, quiz, relatório da noite, importar/exportar listas |
| `userdata.py` | Banco do usuário `carina.sqlite`: listas, diário, horizontes, perfis, progresso |
| `orbital.py` · `companion_server.py` · `qr.py` | Satélites por TLE, servidor do companheiro no celular, QR code |

### catalogs/ — dados

| Módulo | Responsabilidade |
|---|---|
| `stars.py` | Estrelas HYG + ATHYG (npz ordenado por magnitude), cores, nomes |
| `dso.py` · `names.py` · `images.py` | Céu profundo em SQLite (cópia editável do usuário), nomes comuns, imagens DSS |
| `skygeometry.py` · `constnames.py` | Linhas e limites das constelações, Via Láctea, grades; nomes das 88 |
| `equipment.py` | Telescópios, câmeras, oculares, setups e o cálculo do campo de visão |

### render/ — desenho

| Módulo | Responsabilidade |
|---|---|
| `glrenderer.py` | OpenGL 3.3 core: pontos, linhas, preenchimento por stencil, texturas |
| `options.py` · `themes.py` | Opções de um quadro (para render fora da tela) e temas escuro, claro e vermelho |
| `dsoimages.py` | Imagens DSS sobre o céu, por mistura aditiva |
| `moontex.py` · `moon_cpu.py` · `planet_cpu.py` | Texturas da Lua e desenho da Lua e dos planetas na CPU |
| `chart_frame.py` | Carta celeste para impressão: especificação e moldura |

### ui/ — interface

| Módulo | Responsabilidade |
|---|---|
| `mainwindow.py` | Janela principal, menus, docks, persistência, integração de tudo |
| `skywidget.py` | O céu: composição do quadro, camadas, rótulos, destaques (constelação, asterismo, alinhamento), seleção, pan e zoom |
| `object_card.py` · `infopanel.py` · `info_popup.py` · `object_window.py` | A ficha do objeto nas suas formas |
| `tonight_panel.py` · `plan_window.py` · `plan_pdf.py` · `finderchart.py` · `timeline` | Hoje à noite, planejamento, PDF de campo e cartas de localização |
| `chart_dialog.py` · `print_window.py` · `poster_dialog.py` · `planisphere.py` | Cartas, anotações, pôster, planisfério |
| `moon_window.py` · `moon_planner.py` · `planet_window.py` · `calendar_window.py` | Lua, planetas e calendário |
| `session_window.py` · `fov_dialog.py` · `photo_overlay.py` · `track_window.py` | Astrofotografia e rastreamento |
| `tour_player.py` · `tours_gallery.py` · `tour_object_card.py` · `quiz.py` | Tours e quiz |
| `lists_window.py` · `journal_dialog.py` · `programs_window.py` · `night_report.py` | Listas, diário, programas, relatório |
| `nightmode.py` · `observing_mode.py` · `help_viewer.py` · `first_run.py` | Modo noturno, modo observação, ajuda (F1), primeiro uso |

## O desenho de um quadro

1. O relógio da simulação dá o instante (`TimeController`).
2. `SkyEngine.horizontal_matrix(t)` calcula a matriz 3×3 ICRS→horizontal
   (norte, leste, zênite) com três `from_altaz` do Skyfield — embute
   precessão, nutação, rotação da Terra e movimento polar. É reaproveitada
   por meio segundo.
3. Cada camada transforma os seus vetores unitários com um único produto
   matricial (`V @ M.T`) — as 860 mil estrelas num `matmul` NumPy — e um
   cone de visada em ICRS descarta antes o que está fora do campo.
4. Refração (Sæmundsson) só no conteúdo celeste; projeção estereográfica.
5. Ordem: fundo e atmosfera → Via Láctea (textura na esfera) → grades →
   limites e linhas das constelações → destaques → horizonte e solo →
   estrelas → céu profundo e imagens → Sistema Solar → rótulos (QPainter
   por cima do GL).
6. As estrelas estão ordenadas por magnitude: o corte pela magnitude-limite
   (função do campo e do Bortle) é um `searchsorted` e um recorte, sem
   máscara.

O mesmo `_render` serve a janela e o **render fora da tela** (cartas,
pôster, planisfério, relatório), com `RenderOptions` próprias.

## Projeção e referenciais

- **Estereográfica**, como o padrão do Stellarium: um ponto a θ do centro da
  vista cai no raio `r = 2·tan(θ/2)`; conforme, boa até ~150° de campo.
- **Horizontal**: x = norte, y = leste, z = zênite; azimute do norte para o
  leste.
- **Lua**: referencial MOON_ME dos kernels da NAIF (o mesmo do gazetteer da
  IAU), para libração e coordenadas das formações.

## Aproximações assumidas

- Estrelas sem aberração anual (~20″), paralaxe ou movimento próprio na
  época atual (posições J2000), exceto onde importa: as ocultações usam
  movimento próprio.
- Sistema Solar pelo caminho completo `observe().apparent()` do Skyfield.
- Escala de tempo embutida do Skyfield (ΔT tabelado): erro abaixo de um
  segundo nas décadas próximas.

## Os tours

Um único motor serve aos tours **autorais** (Markdown em
`scripts/curated/tours/` → JSON embarcado) e aos **gerados** em Python para
a data e o local (`core/tours_generated.py`). `TourRun` resolve os alvos,
calcula o instante de cada passo e decide o que pular; o player só aplica ao
céu e guarda/restaura o estado (`SkyState`). Formato e autoria em
[Escrevendo tours](TOURS.md).

## Dados do usuário

- **Preferências**: QSettings (registro do Windows).
- **`carina.sqlite`**: listas, diário, horizontes, perfis e progresso, num
  único banco versionado.
- **`dso.sqlite`**: cópia editável do catálogo embarcado, mesclada quando o
  embarcado ganha versão nova.
- **`equipamentos.json`**: equipamentos e setups, com mescla dos padrões
  novos a cada versão do acervo.

Locais exatos em [Ambiente](AMBIENTE.md#onde-o-programa-guarda-os-dados-do-usuário).
