# assets

Arte original do projeto, na resolução mais alta disponível. O que está
aqui é **fonte**: os arquivos usados pelo programa são gerados a partir
destes por `scripts/build_icon.py`.

## Logotipo

Salve o logotipo do **Astronomia no Quintal** como:

```
assets/Astronomianoquintal.jpg
```

Depois gere os ícones:

```bash
.venv/Scripts/python scripts/build_icon.py
```

Isso produz, em `data/processed/`:

| Arquivo | Uso |
|---|---|
| `icon.ico` | Ícone do executável e da janela no Windows (16 a 256 px) |
| `icon.png` | 512 px — README e tela "Sobre" |
| `icon_64.png` | Versão pequena para a interface |

Os gerados são ignorados pelo git (constam no `.gitignore`) — quem clonar
o repositório roda o script uma vez.

> A imagem de origem deve ser **quadrada** ou próxima disso. Se não for,
> o script recorta pelo centro.
