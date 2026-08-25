# Solução de problemas

> Carina 0.13.2 — produto em desenvolvimento. Se o seu problema não
> estiver aqui, ele pode ser um defeito ainda desconhecido: reporte com o
> máximo de detalhes.

---

## O programa não abre

### "O Windows protegeu o computador"

O SmartScreen bloqueia executáveis sem assinatura digital. Clique em
**Mais informações → Executar assim mesmo**. Assinar um executável exige
um certificado pago, fora do alcance de um projeto pessoal.

### A janela abre preta ou fecha sozinha

Quase sempre é OpenGL. O Carina exige **OpenGL 3.3**.

1. Atualize o driver da placa de vídeo pelo site do fabricante — não pelo
   Windows Update, que costuma trazer versões antigas.
2. Em notebooks com duas GPUs, force o uso da dedicada: clique direito no
   executável → *Executar com processador gráfico* → placa de alto
   desempenho.
3. Máquinas virtuais e acesso remoto muitas vezes não oferecem OpenGL 3.3.

### "de440s.bsp não encontrado"

Rodando a partir do código, coloque o arquivo em
`data/ephemeris/de440s.bsp`. Sem ele e sem internet, os cálculos do
Sistema Solar não funcionam. No executável, ele já vem embarcado.

---

## O céu está errado

### As estrelas não batem com o que vejo

Confira, nesta ordem:

1. **A localização** (`Ctrl+L`). É o erro mais comum: o padrão de fábrica
   é o Rio de Janeiro.
2. **A data e a hora** na barra de estado. Se você viajou no tempo, `8`
   volta ao agora.
3. **O fuso horário**, no diálogo de localização. Se você digitou
   coordenadas à mão sem escolher cidade, o fuso pode ter ficado o
   anterior.

### Não vejo a Via Láctea

Verifique a **classe de Bortle** (*Exibir → Poluição luminosa*). A partir
da **classe 7** ela desaparece — de propósito, porque é o que acontece no
céu real de uma cidade. Volte para 1–4 se quiser vê-la.

Confirme também se a camada está ligada (tecla `M`).

### Poucas estrelas aparecem

Três causas possíveis:

- **Bortle alto** — a magnitude limite cai muito na classe 8 ou 9;
- **teto de magnitude** — em *Exibir → Magnitude máxima*, volte para
  *Automática (pelo zoom)*;
- **campo muito aberto** — em 100° de campo o programa mostra menos
  estrelas, porque é o que a escala permite distinguir. Aproxime.

### As imagens dos objetos não aparecem

- Ligue a camada com **`I`**;
- Objetos pequenos na tela não recebem imagem: **aproxime**;
- No **modo mapa** as imagens nunca são desenhadas;
- Em **Bortle alto** elas ficam bem esmaecidas, como no céu real.

### Um objeto não aparece

- O **catálogo** dele pode estar desligado (`Ctrl+Shift+C`);
- O **objeto** pode estar desabilitado no gerenciador (`Ctrl+D`);
- Ele pode estar **abaixo do horizonte** — desmarque *Solo opaco* (`G`)
  para ver o céu inteiro.

---

## Desempenho

### O céu está travando

Em ordem de eficácia:

1. **Desligue as imagens do levantamento** (`I`) — é a camada mais cara;
2. **Baixe o teto de magnitude** para 9 ou 10 — o catálogo profundo tem
   741 mil estrelas;
3. **Desligue a Via Láctea** (`M`) em máquinas com vídeo integrado;
4. **Reduza a janela** — o custo cresce com o número de pixels.

Para referência, numa máquina comum o programa desenha o céu em cerca de
8 ms por quadro; com imagens e magnitude 12 em campo fechado, perto de
17 ms. Se você está muito acima disso, o problema é o driver de vídeo.

### O programa demora a abrir

São cerca de dois segundos para carregar 860 mil estrelas, o banco de
objetos e as efemérides. Depois disso tudo fica em memória.

### Um roteiro demora a calcular

O planejamento avalia todos os objetos do catálogo escolhido em dezenas
de instantes da noite. Alguns segundos é normal; as maratonas Messier e
Caldwell são as mais rápidas, as temáticas demoram um pouco mais.

---

## Interface

### As camadas mudam sozinhas

Os atalhos de camada são **teclas simples** (`P`, `D`, `M`…). Se a
janela tem foco e você digita, elas alternam. Clique no céu antes de usar
atalhos, e lembre que ao fechar um diálogo o foco volta para a janela.

### Um botão não corresponde ao menu

O botão de **céu profundo** da barra lateral é um **controle mestre**:
apaga marcações e imagens juntas. No menu *Exibir*, "Objetos de céu
profundo" (`D`) e "Imagens DSS" (`I`) são independentes — isso é
proposital, para você ver a imagem sem os círculos por cima.

### Os horários não batem com o meu relógio

O Carina usa o fuso da **cidade escolhida**, não o do computador. É o
comportamento correto para planejar observações em outro lugar. Confira
o fuso em `Ctrl+L`.

### O gráfico anual está estranho

Se a curva de altitude máxima tiver quedas bruscas no meio de uma rampa,
é defeito — foi corrigido na versão 0.13.2. Confirme sua versão em
*Ajuda → Sobre o Carina*.

---

## Dados e arquivos

### Perdi minhas edições de objetos

Elas ficam em `%LOCALAPPDATA%\Carina\Carina\dso.sqlite`. Se você usou
*Restaurar padrão* no gerenciador, foram descartadas — não há desfazer.
Vale copiar esse arquivo de tempos em tempos se você mantém uma lista
pessoal grande.

### Quero recomeçar do zero

- **Objetos**: gerenciador (`Ctrl+D`) → *Restaurar padrão*;
- **Equipamentos**: simulador (`Ctrl+K`) → aba de gerenciamento →
  *Restaurar padrão*;
- **Preferências**: apague a chave `HKCU\Software\Carina\Carina` no
  Editor do Registro;
- **Tudo**: apague a pasta `%LOCALAPPDATA%\Carina`.

### As imagens que baixei sumiram

Ficam em `%LOCALAPPDATA%\Carina\Carina\Cache\images\`. Se você limpou o
cache do sistema, elas serão baixadas de novo quando necessário — desde
que haja internet.

---

## Perguntas frequentes

**Preciso de internet?**
Não. Tudo funciona offline. Internet só é usada para baixar imagens de
objetos que não vieram no pacote.

**Funciona no Linux ou no macOS?**
Deve funcionar, rodando a partir do código, mas não passou por testes
sistemáticos. Relatos são bem-vindos.

**Posso usar as imagens geradas?**
Sim, mantendo os créditos das fontes — veja
[CATALOGOS.md](CATALOGOS.md).

**Ele controla meu telescópio?**
Não, e não está previsto para as próximas versões.

**Mostra cometas ou satélites?**
Ainda não.

**Por que meu objeto favorito não está no catálogo?**
São 18.632 objetos, mas nem tudo cabe. Você pode **criar o objeto**
manualmente no gerenciador (`Ctrl+D`).

---

## Como relatar um problema

Informe:

1. a **versão** (*Ajuda → Sobre o Carina*);
2. a **cidade** configurada;
3. a **data e hora** simuladas, como aparecem na barra de estado;
4. o que você **esperava** e o que **aconteceu**;
5. se possível, uma **captura da tela** (`Ctrl+S`).

Problemas de céu — posição errada, horário estranho, objeto ausente —
têm prioridade máxima: precisão astronômica é o compromisso central do
projeto.
