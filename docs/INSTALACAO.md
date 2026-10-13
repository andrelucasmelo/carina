# Instalação

> Carina 0.23.0 — produto em desenvolvimento.

## Windows

O Carina vem pronto para usar: uma pasta com tudo dentro — o programa, os
catálogos de estrelas e objetos, as imagens e as efemérides. Não instala
nada no sistema, não exige Python e **funciona sem internet**.

1. Baixe o arquivo **`Carina-…-windows-x64.zip`** da página
   [Releases](https://github.com/andrelucasmelo/carina/releases) do projeto.
2. Extraia a pasta `Carina` para onde quiser — por exemplo
   `C:\Programas\Carina`.
3. Abra **`Carina.exe`**.

Na primeira vez, um assistente pede a sua cidade e a qualidade do seu céu.
Daí em diante, o céu na tela é o do seu quintal. O passeio completo está em
[Primeiros passos](PRIMEIROS_PASSOS.md).

### Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| **Sistema** | Windows 10 | Windows 11 |
| **Gráficos** | OpenGL 3.3 (qualquer placa dos últimos quinze anos) | placa dedicada |
| **Memória** | 4 GB | 8 GB |
| **Disco** | 400 MB | 500 MB |

### Aviso do Windows ao abrir

Como o executável não é assinado digitalmente, o SmartScreen pode exibir
"O Windows protegeu o computador". Clique em **Mais informações ▸
Executar assim mesmo**. Isso acontece com qualquer programa sem
certificado de assinatura, que custa caro para um projeto pessoal.

### Atualizar

Baixe a versão nova e substitua a pasta antiga. As suas listas, o diário, o
horizonte do quintal, os equipamentos e as preferências ficam no seu perfil
do Windows e são mantidos.

### O que fica onde

O programa nunca escreve dentro da própria pasta. Os seus dados vão para o
seu perfil:

| O quê | Onde |
|---|---|
| Preferências (camadas, local, configurações) | Registro do Windows, em `HKCU\Software\Carina\Carina` |
| Listas, diário, horizontes e progresso | `%LOCALAPPDATA%\Carina\Carina\carina.sqlite` |
| O seu catálogo de objetos, com as edições | `%LOCALAPPDATA%\Carina\Carina\dso.sqlite` |
| Os seus equipamentos | `%LOCALAPPDATA%\Carina\Carina\equipamentos.json` |
| Imagens baixadas em uso | `%LOCALAPPDATA%\Carina\Carina\Cache\images\` |

### Desinstalar

Apague a pasta do programa. Para apagar também os seus dados, remova a pasta
`%LOCALAPPDATA%\Carina`.

---

## Linux e macOS

Ainda não há pacote pronto: nesses sistemas o Carina roda a partir do código,
com o Python. O passo a passo está em
[Ambiente de desenvolvimento](desenvolvimento/AMBIENTE.md). Ele deve
funcionar, mas ainda não passou por testes sistemáticos fora do Windows —
relatos de uso são muito bem-vindos.

---

Problemas? Veja [Solução de problemas](SOLUCAO_DE_PROBLEMAS.md).
