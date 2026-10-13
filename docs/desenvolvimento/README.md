# Documentação de desenvolvimento

> Carina 0.23.0 — produto em desenvolvimento.

Esta seção é para quem quer **rodar o Carina a partir do código, entender
como ele funciona por dentro, gerar os dados, escrever conteúdo, testar ou
empacotar uma versão**. Para usar o programa, veja o
[guia do usuário](../README.md).

## Em uma frase

O Carina é um aplicativo desktop em **Python 3.12+**, com interface em
**PySide6 (Qt 6)**, céu desenhado em **OpenGL 3.3** e astronomia calculada
pelo **Skyfield** com as efemérides **JPL DE440s**. Todos os dados vêm
embarcados e o programa funciona sem internet. Licença **MIT**.

## Páginas

| Página | Conteúdo |
|---|---|
| **[Ambiente de desenvolvimento](AMBIENTE.md)** | Requisitos, clonar, instalar, rodar, a estrutura de pastas, a linha de comando de testes e como isolar os dados do usuário |
| **[Arquitetura](ARQUITETURA.md)** | As camadas do código, o mapa dos módulos, o desenho de um quadro, a projeção, os referenciais e as aproximações |
| **[Componentes e dados](COMPONENTES.md)** | Bibliotecas, dados embarcados, fontes, licenças e atribuições |
| **[Pipeline de dados](DADOS.md)** | Os scripts `scripts/build_*.py`: o que cada um gera, de onde e em que ordem |
| **[Escrevendo tours](TOURS.md)** | O formato dos tours, os alvos, as setas, os tours gerados e a verificação |
| **[Testes e qualidade](TESTES.md)** | A suíte, os testes com OpenGL e as validações astronômicas |
| **[Build e release](BUILD.md)** | Ícones, PyInstaller, o pacote, o checksum, as notas e a publicação |
| **[Decisões de arquitetura](DECISOES.md)** | Resumo das decisões registradas (ADRs) |
| **[Como contribuir](CONTRIBUINDO.md)** | Convenções de código, de texto e de commits; como relatar um problema |

## Princípios do projeto

- **Precisão primeiro.** Todo cálculo novo é conferido contra uma fonte
  independente e ganha teste.
- **Tudo local.** O que o programa precisa é embarcado; nada depende de
  internet depois de instalado. Os dados do usuário ficam só no computador
  dele.
- **Licença limpa.** Só dados e código compatíveis com MIT — nada do
  Stellarium (GPL), nada sob CC BY-NC.
- **Em português.** Interface, documentação e código comentado em português
  do Brasil; a interface passa por `tr()` para traduções futuras.
- **Testável sem interação.** Cada recurso ganha uma opção de linha de
  comando que o aciona e uma captura em PNG — é assim que as validações
  visuais rodam.
