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
    parser.add_argument(
        "--dialog", choices=["dso", "search", "eclipses", "track", "fov"],
        default=None, help="abre um diálogo/janela ao iniciar (para testes)",
    )
    parser.add_argument("--demo-fov", metavar="TEL,CAM", default=None,
                        help="aplica um campo de visão ao céu (testes)")
    parser.add_argument("--dialog-text", default=None,
                        help="texto pré-digitado no diálogo (para testes)")
    parser.add_argument("--enable-layer", action="append", default=[],
                        metavar="CAMADA",
                        help="liga uma camada ao iniciar (para testes)")
    parser.add_argument("--chart", action="store_true",
                        help="inicia em modo mapa para impressão")
    parser.add_argument("--demo-measure", metavar="A,B", default=None,
                        help="mede entre dois objetos por nome (testes)")
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

    if args.chart:
        win.control_panel.btn_chart.setChecked(True)

    def _apply_demo_measure() -> None:
        """Injeta uma medição entre dois objetos (só para testes visuais).

        Precisa rodar depois de show() e de --look: as posições de tela
        dependem da câmera final e do viewport real.
        """
        import math as _math

        import numpy as _np

        names = [s.strip().lower() for s in args.demo_measure.split(",")]
        t0 = win.engine.time.current()
        m0 = win.engine.horizontal_matrix(t0)
        points = []
        for want in names:
            for i, nm in win.star_catalog.proper.items():
                if nm.lower() == want:
                    vec = win.star_catalog.xyz[i] @ m0.T
                    x, y, _ = win.sky._to_screen(vec[_np.newaxis, :], margin=1e9)
                    points.append(
                        {"x": float(x[0]), "y": float(y[0]),
                         "vec": win.sky.camera.unproject(float(x[0]), float(y[0]))}
                    )
                    break
        if len(points) == 2:
            win.sky.set_mouse_mode("measure")
            win.sky._measure = {"a": points[0], "b": points[1]}
            sep = _math.degrees(
                _math.acos(
                    max(-1.0, min(1.0, float(
                        _np.dot(points[0]["vec"], points[1]["vec"])
                    )))
                )
            )
            print(f"medicao: {args.demo_measure} = {sep:.3f} graus")
            win.sky.update()

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
    elif args.dialog == "track":
        win._open_track()
        dialog = win._track_windows[-1] if win._track_windows else None
    elif args.dialog == "fov":
        from .catalogs.equipment import EquipmentStore
        from .config import user_data_path
        from .ui.fov_dialog import FovDialog

        win._equipment = EquipmentStore(user_data_path() / "equipamentos.json")
        dialog = FovDialog(win._equipment, win)
        dialog.fovChanged.connect(win.sky.set_fov_shapes)
        dialog.show()

    if args.demo_measure:
        _apply_demo_measure()

    if args.demo_fov:
        from .catalogs.equipment import EquipmentStore, compute_camera_fov
        from .config import user_data_path

        store = EquipmentStore(user_data_path() / "equipamentos.json")
        tel_name, cam_name = (s.strip() for s in args.demo_fov.split(","))
        scope = next(
            (t for t in store.items("telescopes") if tel_name.lower() in t.name.lower()),
            None,
        )
        cam = next(
            (c for c in store.items("cameras") if cam_name.lower() in c.name.lower()),
            None,
        )
        if scope and cam:
            shape = compute_camera_fov(scope, cam)
            import math as _math

            print(
                f"FOV: {shape.label} = "
                f"{_math.degrees(shape.width):.3f} x "
                f"{_math.degrees(shape.height):.3f} graus"
            )
            for k, v in shape.details:
                print(f"  {k}: {v}")
            win.sky.set_fov_shapes([shape], 0.0, True)

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
