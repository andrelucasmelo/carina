# Catálogos e dados

> Carina 0.13.2 — produto em desenvolvimento.

De onde vêm os dados, o que está embarcado, e como criar e editar os
seus próprios objetos.

---

## Tudo funciona offline

Um princípio do projeto: **tudo o que o programa baixa vira base local**.
Catálogos, efemérides e imagens são embarcados no instalador. Depois de
instalado, o Carina **não precisa de internet** para nada — o que importa
quando se observa de um sítio sem sinal.

Downloads em tempo de execução existem apenas para imagens de objetos que
não vieram no pacote, e mesmo esses viram **cache permanente**.

---

## O que vem embarcado

| Dado | Tamanho | Conteúdo |
|---|---|---|
| `stars_hyg.npz` | 2,6 MB | 119.625 estrelas com nomes e designações |
| `stars_deep.npz` | 9,3 MB | 741.189 estrelas de magnitude 8,5 a 12 |
| `star_names.json` | 1,7 MB | Nomes próprios, Bayer, Flamsteed, constelação |
| `dso.sqlite` | 2,4 MB | 18.632 objetos de céu profundo, 11 catálogos |
| `images/` | 97 MB | 1.179 imagens reais do levantamento DSS |
| `milkyway_pts.npz` | 623 KB | Via Láctea em pontos |
| `milkyway.npz` | 316 KB | Isofotas vetoriais da Via Láctea |
| `const_lines.npz` | 27 KB | Traçados das figuras das constelações |
| `const_bounds.npz` | 86 KB | Limites oficiais IAU |
| `outlines.json` | 39 KB | Contornos reais de 22 nebulosas |
| `cities.json` | 82 KB | 745 cidades com fuso horário |
| `de440s.bsp` | 32 MB | Efemérides JPL, 1849–2150 |

---

## As fontes

| Fonte | O que fornece | Licença |
|---|---|---|
| **HYG v4.1** (D. Nash) | Catálogo estelar principal | CC BY-SA |
| **ATHYG v3.2** | Catálogo profundo (Tycho-2) | CC BY-SA |
| **OpenNGC** | NGC e IC com tipos e dimensões | CC BY-SA 4.0 |
| **VizieR** (CDS) | Sharpless, Barnard, LDN, van den Bergh, Abell | pública, com atribuição |
| **SIMBAD** (CDS) | Melotte e Collinder | pública, com atribuição |
| **hips2fits / DSS2 color** (CDS) | Imagens dos objetos | pública, com atribuição |
| **JPL DE440s** | Efemérides do Sistema Solar | domínio público |
| **ESO / S. Brunier** | Panorâmica da Via Láctea | CC BY 4.0 |
| **d3-celestial** | Linhas e limites das constelações | BSD-3 |
| **GeoNames** | Base de cidades | CC BY 4.0 |
| **IAU** | Nomes oficiais de estrelas | pública |

Nenhum dado ou código do **Stellarium** foi usado — ele é GPL, e o Carina
é MIT.

### Créditos obrigatórios

Ao publicar imagens geradas pelo programa, mantenha os créditos:

- imagens de objetos: **DSS2 color, cortesia CDS/hips2fits**;
- Via Láctea: **ESO/S. Brunier (CC BY 4.0)**;
- catálogo estelar: **HYG Database (CC BY-SA)**.

A tela *Ajuda → Sobre o Carina* lista todas as fontes.

---

## Escolhendo o que aparece

### Catálogos inteiros

*Céu profundo → Configurar catálogos exibidos* (`Ctrl+Shift+C`).

Cada catálogo tem uma caixa e a contagem de objetos. Quatro vêm
**desligados de fábrica** — LDN, Collinder, van den Bergh e Abell —
porque somam mais de 4.800 objetos, na maioria fracos, e poluiriam a
tela sem acrescentar muito para observação visual.

Os botões **Marcar todos**, **Desmarcar todos** e **Padrão** ajudam a
voltar atrás.

### Objeto por objeto

`Ctrl+D` abre o gerenciador. Ali cada objeto tem uma caixa de
habilitação: desmarcado, ele some do céu e das buscas, mas continua no
banco.

---

## Criando os seus objetos

O gerenciador (`Ctrl+D`) faz o ciclo completo: **incluir, editar,
excluir**.

### Um objeto novo

Clique em **Novo** e preencha:

| Campo | Observação |
|---|---|
| **Nome** | Como aparecerá no céu |
| **Tipo** | Galáxia, aglomerado, nebulosa… — define o símbolo |
| **AR / Dec** | Coordenadas J2000, em horas e graus |
| **Magnitude** | Deixe vazio se não souber |
| **Tamanho maior / menor** | Em minutos de arco |
| **Ângulo de posição** | Para objetos alongados |
| **Constelação** | Sigla IAU de três letras |
| **Nome comum** | Nome popular, se houver |
| **Notas** | Texto livre, aparece na ficha |

Objetos criados por você ficam marcados como *criados pelo usuário* e
podem ser filtrados por isso.

### Categorias

Organize como quiser — "Alvos da primavera", "Já fotografei", "Difíceis".
Um objeto pode estar em várias. As categorias viram filtro no
gerenciador.

### Onde ficam as suas edições

O banco embarcado é **copiado para o seu perfil** na primeira execução:

```
%LOCALAPPDATA%\Carina\Carina\dso.sqlite
```

Todas as edições vão para essa cópia. **Atualizar o programa não apaga
seus dados.** Se quiser recomeçar do zero, o gerenciador tem
**Restaurar padrão** — o que descarta suas edições.

---

## Regenerando os dados

Só necessário para quem roda a partir do código e quer reconstruir tudo
das fontes originais.

```bash
.venv/Scripts/python scripts/build_data.py
```

Baixa e processa estrelas, constelações e Via Láctea.

```bash
.venv/Scripts/python scripts/build_dso.py
```

Monta o banco de céu profundo a partir do OpenNGC, VizieR e SIMBAD.

```bash
.venv/Scripts/python scripts/build_images.py
```

Baixa as imagens Messier e Caldwell.

```bash
.venv/Scripts/python scripts/build_large_images.py
```

Baixa as imagens dos objetos grandes (>30′) e das galáxias (>8′). São
787 alvos; o script é **incremental** — pode ser interrompido e retomado.

```bash
.venv/Scripts/python scripts/build_cities.py
```

Regenera a base de cidades a partir do GeoNames.

```bash
.venv/Scripts/python scripts/build_icon.py
```

Gera os ícones do aplicativo a partir de `assets/`.

> Os scripts acessam servidores públicos e podem demorar bastante — o de
> imagens grandes leva mais de uma hora. Rode-os só quando precisar.

---

## Precisão dos dados

- **Posições estelares**: J2000, com precessão e nutação aplicadas pela
  matriz de rotação do instante. A aberração anual (~20″) e a paralaxe
  estelar são desprezadas — invisíveis na escala de um planetário.
- **Sistema Solar**: caminho completo do Skyfield, com aberração e
  deflexão da luz.
- **Magnitudes planetárias**: modelo de Mallama.
- **Dimensões dos objetos**: como publicadas no catálogo de origem;
  variam de fonte para fonte, sobretudo para nebulosas difusas.
