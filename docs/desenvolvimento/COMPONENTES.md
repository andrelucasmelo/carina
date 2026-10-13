# Componentes e dados

> Carina 0.23.0 — [Documentação de desenvolvimento](README.md)

## Bibliotecas

| Biblioteca | Versão mínima | Para quê | Licença |
|---|---|---|---|
| **PySide6** (Qt 6) | 6.8 | Toda a interface; `QOpenGLWidget` para o céu; QPainter para rótulos, PDFs e cartas | LGPL |
| **PyOpenGL** | 3.1.7 | Chamadas OpenGL 3.3 core | BSD |
| **NumPy** | 1.26 | Todo o cálculo vetorizado: projeção, visibilidade, Lua e planetas na CPU | BSD |
| **Skyfield** | 1.49 | Astrometria: precessão, nutação, rotação da Terra, posições aparentes, almanaques, eclipses lunares | MIT |
| **requests** | 2.31 | Downloads dos scripts de dados e das imagens sob demanda | Apache 2.0 |
| **platformdirs** | 4.0 | Pastas de dados e cache do usuário | MIT |
| **tzdata** | 2024.1 | Fusos horários IANA no Windows | domínio público |

Só para desenvolvimento (extra `dev`): **pytest** (testes), **PyInstaller**
(executável) e **Pillow** (scripts de imagens).

O companheiro no celular usa o `http.server` da biblioteca padrão; o QR code,
o iCalendar e a leitura de shapefiles são implementados no próprio projeto,
sem dependências.

## O que vem embarcado

Em `data/processed/` (cerca de 140 MB) e `data/ephemeris/` (cerca de 34 MB):

| Arquivo | Conteúdo |
|---|---|
| `stars_hyg.npz` · `star_names.json` | 119.625 estrelas com nomes próprios, Bayer, Flamsteed e constelação |
| `stars_deep.npz` | 741.189 estrelas de magnitude 8,5 a 12 (Tycho-2 via ATHYG) |
| `dso.sqlite` | 18.632 objetos de céu profundo de 11 catálogos (NGC, IC, Messier, Caldwell, Sharpless, Barnard, LDN, Melotte, Collinder, van den Bergh, Abell) |
| `images/` | 1.179 recortes DSS dos objetos (fora do git; gerados pelos scripts) |
| `milkyway_tex.jpg` · `milkyway*.npz` | Textura e isofotas da Via Láctea |
| `const_lines.npz` · `const_bounds.npz` · `constellations.json` | Figuras, limites IAU e centros das constelações |
| `constellation_lore_pt.json` | Histórias das 88 constelações |
| `asterisms.json` · `alignments.json` | 27 asterismos e 14 alinhamentos (as setas dos tours) |
| `tours/` | 34 tours autorais e os textos dos tours gerados |
| `programs/` | Messier, Caldwell, Herschel 400, Céu ao binóculo |
| `moon/` | Textura e relevo da Lua, 904 formações, Lunar 100 |
| `planets/` | Texturas dos planetas, luas de Júpiter e Saturno |
| `meteors.json` | 25 chuvas de meteoros |
| `cities.json` | 745 cidades com coordenadas e fuso |
| `lightpollution.npz` | Brilho artificial do céu para o Bortle automático |
| `outlines.json` · `featured_images.json` · `common_names.json` | Contornos de nebulosas, manifesto das imagens, nomes comuns em português |
| `de440s.bsp` e kernels da NAIF | Efemérides do Sistema Solar (1849–2150) e orientação da Lua |

## Fontes e licenças

| Fonte | Uso | Licença |
|---|---|---|
| **HYG v4.1** (D. Nash) | Catálogo estelar principal | CC BY-SA |
| **ATHYG v3.2** | Catálogo profundo (Tycho-2), deduplicado contra o HYG | CC BY-SA |
| **OpenNGC** | NGC e IC: tipos, tamanhos, magnitudes, nomes | CC BY-SA 4.0 |
| **VizieR** (CDS) | Sharpless, Barnard, LDN, van den Bergh, Abell | dados públicos, com atribuição |
| **SIMBAD** (CDS) | Melotte e Collinder | dados públicos, com atribuição |
| **hips2fits / DSS2 color** (CDS) | Imagens dos objetos | uso educacional, com atribuição |
| **JPL DE440s** · **NAIF** | Efemérides e orientação da Lua | domínio público |
| **JPL** `jup365` · `sat441` | Luas de Júpiter e Saturno | domínio público |
| **NASA SVS CGI Moon Kit** | Textura (LROC) e relevo (LOLA) da Lua | domínio público |
| **IAU/USGS Gazetteer** | Nomes das formações lunares | domínio público |
| **Lunar 100** (C. A. Wood, *Sky & Telescope*) | Programa de 100 alvos lunares | lista factual, descrições próprias |
| **IMO Meteor Shower Working List** | Chuvas de meteoros | dados factuais |
| **Solar System Scope** | Texturas dos planetas | CC BY 4.0 |
| **JUPOS** | Longitude da Grande Mancha Vermelha | dados factuais |
| **ESO / S. Brunier** (`eso0932a`) | Panorâmica da Via Láctea | CC BY 4.0 |
| **NASA Black Marble 2016** (VIIRS) | Luzes noturnas → Bortle automático | domínio público |
| **d3-celestial** (O. Frohn) | Linhas, limites e centros das constelações; isofotas da Via Láctea | BSD-3 |
| **GeoNames** `cities15000` | Base de cidades | CC BY 4.0 |
| **IAU** | Nomes oficiais de estrelas | pública |
| Fichas dos fabricantes | Equipamentos padrão (Seestar, Dwarf, Vespera, Origin, ZWO…) | valores nominais |
| **Astronomia no Quintal** (do mesmo autor) | Textos dos tours, asterismos e alinhamentos | MIT (cessão do autor) |

### Créditos obrigatórios

- **HYG/ATHYG**: atribuição e compartilhamento pela mesma licença nos dados
  derivados (`stars_*.npz`, `star_names.json`).
- **ESO/S. Brunier** pela Via Láctea e **Solar System Scope** pelas texturas
  dos planetas (CC BY 4.0).
- **GeoNames** pelas cidades (CC BY 4.0).
- A tela **Sobre** do programa lista todas as fontes.

### O que não usamos, e por quê

- **Nada do Stellarium** (código, texturas ou dados): é GPL, incompatível com
  a licença MIT do Carina. A Via Láctea usa a panorâmica do ESO; os traçados
  das constelações vêm do d3-celestial.
- **Atlas de Falchi et al. (2016)**: sob CC BY-NC e por formulário — o Bortle
  automático usa o Black Marble da NASA, calibrado por referências.
- Nos tours, as notas de pesquisa que resumem livros de terceiros serviram
  só como fonte de fatos; o texto é próprio.
