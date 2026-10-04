# Diário e listas

> Carina 0.19.1 — produto em desenvolvimento.

O Carina guarda o que você cria: listas de alvos, o diário do que
observou e os perfis de horizonte. Tudo fica num único arquivo no seu
computador e volta igual na próxima abertura.

---

## Minhas listas

*Objetos → Minhas listas…* (`Ctrl+Shift+L`).

Monte listas com nome — "Minha lista", "Galáxias do outono", "Para o
sítio" — e acrescente objetos de qualquer lugar:

| De onde | Como |
|---|---|
| **Ficha do objeto** | Botão **★ Minha lista** |
| **Botão direito** no céu | **★ Acrescentar à minha lista** |
| **Teclado** | `Ctrl+B` acrescenta o objeto selecionado |
| **Busca** (`Ctrl+F`) | `Ctrl+Enter` acrescenta o resultado sem fechar a busca |
| **Hoje à noite** | Botão **★ Minha lista** |

A lista marcada com ★ é o destino desses atalhos; troque com **Usar como
lista do ★**.

Para cada item, a janela mostra como ele está **nesta noite** — nota,
janela útil e melhor hora, já com o seu horizonte e o seu Bortle — e se
você já o observou (✓). Dá para reordenar, remover, anotar, exportar em
CSV e **montar o roteiro desta noite** com os itens da lista. O roteiro
agenda só o que estiver ao alcance e informa, na barra de estado, o que
ficou de fora.

---

## Diário de observação

### Registrar

Clique em **✓ Observado** na ficha, no botão direito ou numa linha do
roteiro. Abre um formulário curto:

| Campo | O que anotar |
|---|---|
| **Quando** | Data e hora (já vem preenchida com o horário da simulação ou da parada do roteiro) |
| **Local** | Já vem com a sua localização |
| **Instrumento** | Olho nu, binóculo ou um telescópio do seu cadastro — o último usado aparece primeiro |
| **Bortle** | Já vem com o Bortle atual |
| **Seeing** | 1 (péssimo) a 5 (excelente) — a estabilidade do ar |
| **Transparência** | 1 (muito nublado) a 5 (excepcional) |
| **Avaliação** | De uma a cinco estrelas |
| **Nota** | O que você viu: detalhes, cores, comparação com a carta |

### Consultar

*Objetos → Diário de observação…* (`Ctrl+Shift+J`) lista todos os
registros, do mais recente ao mais antigo, com quantos objetos e quantas
noites você já somou. Filtre pelo nome, pelo local ou pela nota; edite,
exclua, vá ao objeto no mapa ou **exporte em CSV** para uma planilha.

A **ficha** de cada objeto mostra o histórico: "Observado 3× · último em
02/10/2026: trapézio nítido", além das listas em que ele está.

---

## Onde ficam os dados

Num arquivo chamado `carina.sqlite`, na pasta de dados do usuário:

```
%LOCALAPPDATA%\Carina\Carina\carina.sqlite
```

Ele só é criado quando você salva a primeira coisa — abrir o programa e
só olhar não deixa rastro. Para levar seu diário para outro computador,
copie este arquivo. Para fazer cópia de segurança, inclua-o no seu
backup.

Os objetos são guardados por uma identidade que não muda entre versões
do Carina: o nome do objeto de céu profundo ("M 42"), o número Hipparcos
da estrela ("HIP 27989") ou o nome do corpo ("Júpiter").
