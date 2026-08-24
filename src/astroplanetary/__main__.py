"""Ponto de entrada: ``python -m astroplanetary``.

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
    parser = argparse.ArgumentParser(prog="astroplanetary")
    parser.add_argument("--screenshot", metavar="CAMINHO", default=None)
    parser.add_argument("--at", metavar="ISO", default=None)
    parser.add_argument("--size", metavar="LARGxALT", default=None)
    parser.add_argument("--look", metavar="AZ,ALT", default=None,
                        help="direção inicial da câmera em graus")
    parser.add_argument("--fov", metavar="GRAUS", type=float, default=None)
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

    if args.look:
        import math

        az, alt = (float(v) for v in args.look.split(","))
        win.sky.camera.set_direction(math.radians(az), math.radians(alt))
    if args.fov:
        import math

        win.sky.camera.fov = math.radians(args.fov)

    win.show()

    if args.screenshot:
        def grab() -> None:
            img = win.sky.grabFramebuffer()
            img.save(args.screenshot)
            print(f"screenshot: {args.screenshot} ({img.width()}x{img.height()})")
            app.quit()

        QTimer.singleShot(1200, grab)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
