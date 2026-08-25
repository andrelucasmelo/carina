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
    """Linha de comando — quase toda voltada a testes automatizados.

    O padrão do projeto: cada recurso novo ganha uma flag que o aciona ao
    iniciar, e ``--screenshot`` captura o resultado num PNG sem interação.
    É assim que as validações visuais e o ``--bench`` de desempenho rodam
    em CI/desenvolvimento (ver dev-docs/ARQUITETURA.md).
    """
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
        "--dialog",
        choices=["dso", "search", "eclipses", "track", "fov", "object",
                 "catalogs", "print", "night", "location"],
        default=None, help="abre um diálogo/janela ao iniciar (para testes)",
    )
    parser.add_argument("--planet-path", metavar="NOME", default=None,
                        help="traça o caminho anual de um planeta (testes)")
    parser.add_argument("--bortle", type=int, default=None)
    parser.add_argument("--moon-forecast", action="store_true",
                        help="calcula a previsão da Lua ao iniciar (testes)")
    parser.add_argument(
        "--marathon",
        choices=["M", "C", "OC", "GC", "NEB", "DARK", "BEST",
                 "MONTH", "SEASON", "STARS"], default=None,
        help="abre o planejamento da maratona (testes)",
    )
    parser.add_argument("--marathon-pdf", default=None,
                        help="exporta o PDF da maratona para o caminho dado")
    parser.add_argument("--const-names", default=None,
                        choices=["none", "pt", "latin", "abbr"])
    parser.add_argument("--demo-fov", metavar="TEL,CAM", default=None,
                        help="aplica um campo de visão ao céu (testes)")
    parser.add_argument("--dialog-text", default=None,
                        help="texto pré-digitado no diálogo (para testes)")
    parser.add_argument("--enable-layer", action="append", default=[],
                        metavar="CAMADA",
                        help="liga uma camada ao iniciar (para testes)")
    parser.add_argument("--disable-layer", action="append", default=[],
                        metavar="CAMADA",
                        help="desliga uma camada ao iniciar (para testes)")
    parser.add_argument("--side-toggle", action="append", default=[],
                        metavar="CAMADA",
                        help="clica no botão da barra lateral (para testes)")
    parser.add_argument("--chart", action="store_true",
                        help="inicia em modo mapa para impressão")
    parser.add_argument("--demo-measure", metavar="A,B", default=None,
                        help="mede entre dois objetos por nome (testes)")
    parser.add_argument("--bench", action="store_true",
                        help="mede o tempo de quadro em cenários de estresse")
    return parser.parse_args(argv)


def _run_bench(win, app) -> None:
    """Estresse de renderização: mede ms/quadro em cenários pesados.

    Cada cenário configura a cena, faz dois quadros de aquecimento (upload
    de texturas, compilação de shaders) e cronometra 40 repaints síncronos.
    Reporta mediana/p95/máximo — a mediana é a fluidez típica, o máximo
    denuncia travadas (hitches) de carregamento.
    """
    import math

    from PySide6.QtCore import QElapsedTimer

    sky = win.sky
    results = {}

    def measure(name: str, frames: int = 40) -> None:
        # grabFramebuffer() força um render completo (paintGL) mesmo com a
        # janela ao fundo — repaint() seria ignorado sem exposição. O
        # readback de pixels embutido adiciona um custo fixo (~1-3 ms)
        # igual em todos os cenários, então a comparação permanece válida.
        sky.grabFramebuffer()
        sky.grabFramebuffer()
        timer = QElapsedTimer()
        samples = []
        for _ in range(frames):
            timer.restart()
            sky.grabFramebuffer()
            samples.append(timer.nsecsElapsed() / 1e6)
        samples.sort()
        p50 = samples[len(samples) // 2]
        p95 = samples[int(len(samples) * 0.95) - 1]
        results[name] = (p50, p95, samples[-1])
        print(f"  {name:32s} p50 {p50:7.2f} ms   p95 {p95:7.2f}   "
              f"max {samples[-1]:7.2f}")

    def look(az: float, alt: float, fov: float) -> None:
        sky.camera.set_direction(math.radians(az), math.radians(alt))
        sky.camera.fov = math.radians(fov)

    print("cenários (ms por quadro):")
    look(250.0, 45.0, 100.0)
    measure("fov100 padrão")

    sky.set_mag_cap(12.0)
    measure("fov100 mag12 (céu profundo)")

    sky.set_const_label_mode("pt")
    measure("fov100 mag12 + nomes const")

    look(262.0, 57.0, 20.0)
    sky.set_layer("dso_images", True)
    measure("fov20 Sagitário + imagens DSS")

    look(262.0, 57.0, 5.0)
    measure("fov5 Sagitário mag12 + imagens")

    # varredura de zoom: o pior quadro enquanto o campo muda a cada frame
    look(262.0, 57.0, 100.0)
    sky.grabFramebuffer()
    timer = QElapsedTimer()
    worst = 0.0
    steps = 60
    for i in range(steps):
        f = 100.0 * (1.0 - i / steps) + 1.5 * (i / steps)
        sky.camera.fov = math.radians(f)
        timer.restart()
        sky.grabFramebuffer()
        worst = max(worst, timer.nsecsElapsed() / 1e6)
    print(f"  {'zoom sweep 100→1.5°':32s} pior quadro {worst:7.2f} ms")

    sky.set_mag_cap(None)
    sky.set_layer("dso_images", False)

    # memória do processo (working set) via API do Windows
    try:
        import ctypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        # pseudo-handle do processo atual; c_void_p evita o truncamento
        # para 32 bits que o int puro sofreria no ctypes em Win64
        handle = ctypes.c_void_p(-1)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(pmc), pmc.cb
        )
        print(f"memória: {pmc.WorkingSetSize / 1048576:.0f} MB em uso "
              f"(pico {pmc.PeakWorkingSetSize / 1048576:.0f} MB)")
    except Exception:
        pass
    app.quit()


def main(argv=None) -> int:
    """Ponto de entrada: configura o formato OpenGL (3.3 core, MSAA 4×,
    stencil de 8 bits — o stencil é essencial para o preenchimento de
    polígonos côncavos), cria a janela e aplica as flags de teste."""
    import time as _time

    t_start = _time.perf_counter()
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

    # ícone do aplicativo: vale para a janela, a barra de tarefas e os
    # diálogos (todos herdam o ícone da aplicação)
    from .config import app_icon_path

    icon_file = app_icon_path()
    if icon_file is not None:
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon_file)))

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
    for layer_name in args.disable_layer:
        win.sky.set_layer(layer_name, False)
    for layer_name in args.side_toggle:
        # exercita o caminho REAL do usuário: o botão da barra lateral
        btn = win.side_bar.layer_buttons.get(layer_name)
        if btn is not None:
            btn.setChecked(not btn.isChecked())
            print(f"botao {layer_name}: agora {btn.isChecked()}")

    if args.chart:
        win.side_bar.btn_chart.setChecked(True)
    if args.bortle:
        win.sky.set_bortle(args.bortle)
    if args.const_names:
        win.sky.set_const_label_mode(args.const_names)
    if args.planet_path:
        from .core.planetpath import compute_path

        names = ([args.planet_path] if args.planet_path != "todos"
                 else ["Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno"])
        paths = [
            compute_path(win.engine, n, win.engine.time.current_datetime(),
                         days=365)
            for n in names
        ]
        for p in paths:
            print(f"{p.name}: {len(p.points)} pontos, {len(p.marks)} marcas, "
                  f"{len(p.events)} eventos")
            for ev in p.events:
                print(f"   {ev.when_utc:%d/%m/%Y} {ev.kind} {ev.value:.1f}graus")
        win.sky.set_planet_paths(paths)

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

    if args.screenshot or args.bench:
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
    elif args.dialog == "object":
        win._open_object_window()
        dialog = win._track_windows[-1] if win._track_windows else None
    elif args.dialog == "catalogs":
        from .ui.catalog_dialog import CatalogDialog

        dialog = CatalogDialog(win.dso_catalog, win)
        dialog.show()
    elif args.dialog == "night":
        from .ui.night_dialog import NightInfoDialog

        dialog = NightInfoDialog(
            win.engine, win.settings.location().name, win
        )
        dialog.show()
    elif args.dialog == "location":
        from .ui.location_dialog import LocationDialog

        dialog = LocationDialog(win.settings.location(), win)
        if args.dialog_text:
            dialog.search.setText(args.dialog_text)
        dialog.show()
    elif args.dialog == "print":
        win._open_print_map()
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

    if args.moon_forecast:
        win._open_moon_forecast()
        for mk in win.sky.moon_forecast:
            if mk.phase_name:
                print(f"  {mk.when_utc.astimezone():%d/%m %H:%M} "
                      f"{mk.phase_name} ({mk.illumination * 100:.0f}%)")

    if args.marathon:
        win._open_marathon(args.marathon)
        if win._track_windows:
            dialog = win._track_windows[-1]
            plan = dialog.plan
            print(f"{plan.title}: {len(plan.entries)} objetos, "
                  f"{plan.skipped} fora de alcance, "
                  f"{plan.minutes_per_object} min/objeto")
            for e in plan.entries[:6]:
                print(f"  {e.when_utc.astimezone():%H:%M} "
                      f"{e.catalog_id[:22]:22s} alt {e.altitude:.0f} "
                      f"{e.constellation}")
            if args.marathon_pdf:
                ok = dialog._write_pdf(args.marathon_pdf)
                import os as _os

                print(f"pdf: {args.marathon_pdf} "
                      f"({_os.path.getsize(args.marathon_pdf)} bytes, "
                      f"ok={ok})")

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

    if args.bench:
        def _bench_wrapper() -> None:
            print(f"inicialização até a janela: "
                  f"{_time.perf_counter() - t_start:.2f} s "
                  f"(inclui a espera do agendador)")
            _run_bench(win, app)

        QTimer.singleShot(600, _bench_wrapper)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
