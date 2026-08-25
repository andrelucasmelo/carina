"""Gera os ícones do aplicativo a partir do logotipo original.

Entrada: ``assets/Astronomianoquintal.jpg`` (o logotipo do Astronomia no
Quintal — círculo com telescópio, símbolo do infinito e o céu noturno).

Saídas, todas em ``data/processed/``:

* ``icon.ico``   — multi-resolução (16…256 px), usado pelo executável do
  Windows e pela janela;
* ``icon.png``   — 512 px, para a tela "Sobre" e para o README;
* ``icon_64.png``— versão pequena para uso na própria interface.

O ``.ico`` do Windows precisa conter VÁRIAS resoluções no mesmo arquivo:
a barra de tarefas usa 32 px, o Explorer em modo "ícones grandes" usa
256 px, e deixar o sistema reamostrar de um tamanho só produz bordas
sujas. O redimensionamento é feito em duas etapas quando a redução é
grande (>4×), o que preserva melhor os traços finos do desenho.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "Astronomianoquintal.jpg"
OUT_DIR = ROOT / "data" / "processed"

# Tamanhos que o Windows realmente consulta em cada contexto.
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _load_source() -> "QImage":
    from PySide6.QtGui import QImage

    if not SOURCE.exists():
        raise SystemExit(
            f"Logotipo não encontrado: {SOURCE}\n"
            f"Salve a imagem do logotipo nesse caminho e rode de novo."
        )
    img = QImage(str(SOURCE))
    if img.isNull():
        raise SystemExit(f"Não foi possível ler a imagem: {SOURCE}")
    return img


def _square(img: "QImage") -> "QImage":
    """Recorta ao centro para deixar a imagem quadrada, se preciso."""
    w, h = img.width(), img.height()
    if w == h:
        return img
    side = min(w, h)
    return img.copy((w - side) // 2, (h - side) // 2, side, side)


def _scaled(img: "QImage", size: int) -> "QImage":
    """Redimensiona com suavização, em duas etapas nas reduções grandes."""
    from PySide6.QtCore import Qt

    current = img
    while current.width() > size * 4:
        current = current.scaled(
            current.width() // 2, current.height() // 2,
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
        )
    return current.scaled(size, size, Qt.IgnoreAspectRatio,
                          Qt.SmoothTransformation)


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    _ = app  # mantém a aplicação viva enquanto as imagens são criadas

    img = _square(_load_source())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"origem: {SOURCE.name} ({img.width()}×{img.height()})")

    png = _scaled(img, 512)
    png.save(str(OUT_DIR / "icon.png"), "PNG")
    _scaled(img, 64).save(str(OUT_DIR / "icon_64.png"), "PNG")

    # O Qt grava .ico com uma resolução só; usamos o Pillow quando
    # disponível (ele empacota todas) e caímos no Qt como reserva.
    ico_path = OUT_DIR / "icon.ico"
    try:
        from PIL import Image

        tmp = OUT_DIR / "_icon_tmp.png"
        _scaled(img, 256).save(str(tmp), "PNG")
        with Image.open(tmp) as base:
            base.save(ico_path, format="ICO",
                      sizes=[(s, s) for s in ICO_SIZES])
        tmp.unlink(missing_ok=True)
        modo = f"Pillow, {len(ICO_SIZES)} resoluções"
    except ImportError:
        _scaled(img, 256).save(str(ico_path), "ICO")
        modo = "Qt, resolução única (instale Pillow para multi-resolução)"

    for name in ("icon.ico", "icon.png", "icon_64.png"):
        path = OUT_DIR / name
        print(f"  {name:12s} {path.stat().st_size / 1024:7.1f} KB")
    print(f"ico gerado via {modo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
