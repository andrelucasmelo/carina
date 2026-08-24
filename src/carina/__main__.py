"""Ponto de entrada: ``python -m carina``.

Opções úteis para testes automatizados:
  --screenshot CAMINHO   renderiza um quadro, salva PNG e sai
  --at ISO               congela o relógio da simulação (ex.: 2026-08-24T22:00)
  --size LARGxALT        tamanho da janela (padrão 1280x800)
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from .config import APP_NAME, ORG_NAME


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="carina")
    parser.add_argument("--screenshot", metavar="CAMINHO", default=None)
    parser.add_argument("--at", metavar="ISO", default=None)
    parser.add_argument("--size", metavar="LARGxALT", default=None)
    parser.add_argument("--look", metavar="AZ,ALT", default=None,
                        help="direção inicial da câmera em graus")
    parser.add_argument("--fov", metavar="GRAUS", type=float, default=None)
    parser.add_argument("--select", metavar="NOME", default=None,
                        help="seleciona um objeto ao abrir (nome próprio ou corpo)")
    parser.add_argument("--dialog", choices=["dso", "search", "eclipses"],
                        default=None,
                        help="abre um diálogo ao iniciar (para testes)")
    parser.add_argument("--dialog-text", default=None,
                        help="texto pré-digitado no diálogo (para testes)")
    parser.add_argument("--enable-layer", action="append", default=[],
                        metavar="CAMADA",
                        help="liga uma camada ao iniciar (para testes)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setSamples(4)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    from .ui.mainwindow import MainWindow

    win = MainWindow()

    if args.at:
        when = dt.datetime.fromisoformat(args.at)
        if when.tzinfo is None:
            when = when.astimezone()  # interpreta como hora local
        win.engine.time.set_fixed(when.astimezone(dt.timezone.utc))

    if args.size:
        try:
            w, h = (int(v) for v in args.size.lower().split("x"))
            win.resize(w, h)
        except ValueError:
            pass

    for layer_name in args.enable_layer:
        win.sky.set_layer(layer_name, True)

    if args.look:
        import math

        az, alt = (float(v) for v in args.look.split(","))
        win.sky.camera.set_direction(math.radians(az), math.radians(alt))
    if args.fov:
        import math

        win.sky.camera.fov = math.radians(args.fov)

    if args.select:
        target = args.select.strip().lower()
        selection = None
        for i, nm in win.star_catalog.proper.items():
            if nm.lower() == target:
                selection = ("star", int(i))
                break
        if selection is None:
            from .core.engine import _BODIES

            for name, _key, _color in _BODIES:
                if name.lower() == target:
                    selection = ("body", name)
                    break
        if selection is None:
            import re

            variants = {target, re.sub(r"^([a-z]+)\s*", r"\1 ", target).strip()}
            for v in variants:
                row = win.dso_catalog.cx.execute(
                    "SELECT id FROM objects WHERE name = ? COLLATE NOCASE",
                    (v,),
                ).fetchone()
                if row:
                    selection = ("dso", int(row["id"]))
                    break
        if selection is not None:
            if args.look:
                win.sky.selection = selection
                win.sky.selectionChanged.emit(selection)
            else:
                # sem --look explícito, centraliza a câmera na seleção
                win.sky.goto_object(selection, animate=False)

    if args.screenshot:
        # janelas de teste não devem roubar o foco do usuário (teclas
        # digitadas em outra janela acionariam os atalhos de camada)
        from PySide6.QtCore import Qt

        win.setAttribute(Qt.WA_ShowWithoutActivating, True)
        win.setWindowFlag(Qt.WindowStaysOnBottomHint, True)

    win.show()

    dialog = None
    if args.dialog == "dso":
        from .ui.dso_manager import DsoManagerDialog

        dialog = DsoManagerDialog(win.dso_catalog, win)
        dialog.show()
    elif args.dialog == "search":
        from .ui.search_dialog import SearchDialog

        dialog = SearchDialog(win.star_catalog, win.dso_catalog, win)
        dialog.goto_requested.connect(win.sky.goto_object)
        if args.dialog_text:
            dialog.edit.setText(args.dialog_text)
        dialog.show()
    elif args.dialog == "eclipses":
        from .ui.eclipse_dialog import EclipseDialog

        dialog = EclipseDialog(win.engine, win)
        dialog.show()

    if args.screenshot:
        def grab() -> None:
            # QWidget.grab() perde a camada QPainter desenhada dentro do
            # paintGL (o render() pinta o texto num alvo raster e depois
            # sobrepõe a textura GL). Compomos manualmente: janela inteira
            # (menus/docks) + framebuffer real do céu por cima.
            from PySide6.QtCore import QPoint, QRect
            from PySide6.QtGui import QPainter

            if dialog is not None:
                img = dialog.grab().toImage()
                img.save(args.screenshot)
                print(f"screenshot: {args.screenshot} ({img.width()}x{img.height()})")
                app.quit()
                return
            pix = win.grab()
            gl_img = win.sky.grabFramebuffer()
            painter = QPainter(pix)
            top_left = win.sky.mapTo(win, QPoint(0, 0))
            painter.drawImage(
                QRect(top_left, win.sky.size()), gl_img
            )
            painter.end()
            img = pix.toImage()
            img.save(args.screenshot)
            print(f"screenshot: {args.screenshot} ({img.width()}x{img.height()})")
            app.quit()

        QTimer.singleShot(1200, grab)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
