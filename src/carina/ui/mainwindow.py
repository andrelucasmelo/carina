"""Janela principal do Carina."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QMainWindow, QMessageBox,
)

from .. import __version__
from ..catalogs import skygeometry
from ..catalogs.dso import DsoCatalog
from ..catalogs.stars import StarCatalog
from ..config import Settings, ephemeris_dir, package_data_dir, user_data_path
from ..core.engine import SkyEngine
from .controlpanel import ControlPanel
from .dso_manager import DsoManagerDialog
from .infopanel import InfoPanel, build_info_html
from .location_dialog import LocationDialog
from .skywidget import SkyWidget
from .time_dialog import TimeDialog

# (chave da camada, título do menu, atalho, padrão)
_LAYER_ACTIONS = [
    ("stars", "Estrelas", None, True),
    ("planets", "Planetas, Sol e Lua", "P", True),
    ("dso", "Objetos de céu profundo", "D", True),
    ("moon_zone", "Zona de influência da Lua (astrofoto)", "U", False),
    ("const_lines", "Linhas das constelações", "C", True),
    ("const_bounds", "Fronteiras das constelações", "B", False),
    ("grid_altaz", "Grade horizontal (Alt-Az)", "Z", True),
    ("grid_eq", "Grade equatorial", "E", False),
    ("milkyway", "Via Láctea", "M", True),
    ("horizon", "Linha do horizonte", "H", True),
    ("ground", "Solo (oculta o que está abaixo do horizonte)", "G", True),
    ("cardinals", "Pontos cardeais", "Q", True),
    ("star_names", "Nomes das estrelas", "N", True),
    ("planet_names", "Nomes dos planetas", None, True),
    ("dso_names", "Rótulos do céu profundo", None, True),
    ("atmosphere", "Atmosfera", "A", True),
    ("refraction", "Refração atmosférica", "R", True),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Carina {__version__}")
        self.resize(1280, 800)

        self.settings = Settings()
        data_dir = package_data_dir()

        self.engine = SkyEngine(ephemeris_dir())
        loc = self.settings.location()
        self.engine.set_location(loc)

        self.star_catalog = StarCatalog(data_dir)
        self.dso_catalog = DsoCatalog(
            data_dir / "dso.sqlite", user_data_path() / "dso.sqlite"
        )
        self.const_names = {
            c["id"]: c for c in skygeometry.load_constellation_info(data_dir)
        }
        self.sky = SkyWidget(
            self.engine, self.star_catalog, self.dso_catalog, data_dir, self
        )
        self.sky.location_name = loc.name
        self.setCentralWidget(self.sky)
        self.sky.statusUpdated.connect(self._on_status)
        self.sky.selectionChanged.connect(self._on_selection)

        self.info_dock = QDockWidget(self.tr("Informações"), self)
        self.info_dock.setObjectName("info_dock")
        self.info_panel = InfoPanel(self.info_dock)
        self.info_dock.setWidget(self.info_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)
        self.info_dock.hide()

        # painel lateral de controle
        self.control_dock = QDockWidget(self.tr("Controles"), self)
        self.control_dock.setObjectName("control_dock")
        self.control_panel = ControlPanel(self.engine, self.control_dock)
        self.control_dock.setWidget(self.control_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.control_dock)
        self._wire_control_panel()
        self._track_windows: list = []

        self._build_menus()
        self._restore_layers()

    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        bar = self.menuBar()

        m_file = bar.addMenu(self.tr("&Arquivo"))
        act_export = QAction(self.tr("Exportar vista…"), self)
        act_export.setShortcut("Ctrl+S")
        act_export.triggered.connect(self._export_view)
        m_file.addAction(act_export)
        m_file.addSeparator()
        act_quit = QAction(self.tr("Sair"), self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        # --- Tempo -----------------------------------------------------
        m_time = bar.addMenu(self.tr("&Tempo"))
        time_actions = [
            (self.tr("Agora"), "8", self._time_now),
            (self.tr("Pausar / continuar"), "K", self._time_pause),
            (self.tr("Mais devagar"), "J", self._time_slower),
            (self.tr("Mais rápido"), "L", self._time_faster),
            (self.tr("Velocidade normal (1x)"), "7", self._time_normal),
            (self.tr("Ir para data/hora…"), "Ctrl+T", self._time_goto),
        ]
        for title, shortcut, slot in time_actions:
            act = QAction(title, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            m_time.addAction(act)

        m_view = bar.addMenu(self.tr("&Exibir"))
        self._layer_acts: dict[str, QAction] = {}
        for key, title, shortcut, default in _LAYER_ACTIONS:
            act = QAction(self.tr(title), self)
            act.setCheckable(True)
            act.setChecked(default)
            if shortcut:
                act.setShortcut(shortcut)
            act.toggled.connect(
                lambda on, k=key: self._on_layer_toggled(k, on)
            )
            m_view.addAction(act)
            self._layer_acts[key] = act

        m_view.addSeparator()
        name_group = QActionGroup(self)
        self.act_proper = QAction(self.tr("Rotular estrelas por nome próprio"), self)
        self.act_bayer = QAction(self.tr("Rotular estrelas por Bayer (genitivo)"), self)
        for act, mode in ((self.act_proper, "proper"), (self.act_bayer, "bayer")):
            act.setCheckable(True)
            act.setActionGroup(name_group)
            act.triggered.connect(lambda _=False, m=mode: self.sky.set_name_mode(m))
            m_view.addAction(act)
        self.act_proper.setChecked(True)

        m_view.addSeparator()
        dso_group = QActionGroup(self)
        self.act_dso_number = QAction(
            self.tr("Rotular céu profundo por número de catálogo"), self
        )
        self.act_dso_name = QAction(
            self.tr("Rotular céu profundo por nome"), self
        )
        for act, mode in (
            (self.act_dso_number, "number"), (self.act_dso_name, "name")
        ):
            act.setCheckable(True)
            act.setActionGroup(dso_group)
            act.triggered.connect(
                lambda _=False, m=mode: self.sky.set_dso_name_mode(m)
            )
            m_view.addAction(act)
        self.act_dso_number.setChecked(True)

        m_view.addSeparator()
        m_view.addAction(self.info_dock.toggleViewAction())

        m_dso = bar.addMenu(self.tr("&Céu profundo"))
        act_manage = QAction(self.tr("Gerenciar objetos e catálogos…"), self)
        act_manage.setShortcut("Ctrl+D")
        act_manage.triggered.connect(self._manage_dso)
        m_dso.addAction(act_manage)

        m_tools = bar.addMenu(self.tr("&Ferramentas"))
        act_search = QAction(self.tr("Buscar objeto…"), self)
        act_search.setShortcut("Ctrl+F")
        act_search.triggered.connect(self._open_search)
        m_tools.addAction(act_search)
        act_ecl = QAction(self.tr("Eclipses…"), self)
        act_ecl.setShortcut("Ctrl+E")
        act_ecl.triggered.connect(self._open_eclipses)
        m_tools.addAction(act_ecl)
        act_fov = QAction(self.tr("Campo de visão (equipamentos)…"), self)
        act_fov.setShortcut("Ctrl+K")
        act_fov.triggered.connect(self._open_fov)
        m_tools.addAction(act_fov)
        act_track = QAction(self.tr("Rastrear objeto na noite…"), self)
        act_track.setShortcut("Ctrl+R")
        act_track.triggered.connect(self._open_track)
        m_tools.addAction(act_track)

        m_obs = bar.addMenu(self.tr("&Observador"))
        act_loc = QAction(self.tr("Localização…"), self)
        act_loc.setShortcut("Ctrl+L")
        act_loc.triggered.connect(self._edit_location)
        m_obs.addAction(act_loc)

        m_help = bar.addMenu(self.tr("A&juda"))
        act_about = QAction(self.tr("Sobre o Carina"), self)
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

    # ------------------------------------------------------------------
    def _on_layer_toggled(self, key: str, on: bool) -> None:
        self.sky.set_layer(key, on)
        self.settings.set_layer(key, on)

    def _restore_layers(self) -> None:
        for key, _title, _sc, default in _LAYER_ACTIONS:
            value = self.settings.layer(key, default)
            act = self._layer_acts[key]
            if act.isChecked() != value:
                act.setChecked(value)  # dispara o toggled -> aplica na cena
            else:
                self.sky.set_layer(key, value)

    # --- tempo ---------------------------------------------------------
    def _time_now(self) -> None:
        self.engine.time.to_now()
        self.sky.sync_clock()

    def _time_pause(self) -> None:
        self.engine.time.toggle_pause()
        self.sky.sync_clock()

    def _time_faster(self) -> None:
        self.engine.time.faster()
        self.sky.sync_clock()

    def _time_slower(self) -> None:
        self.engine.time.slower()
        self.sky.sync_clock()

    def _time_normal(self) -> None:
        self.engine.time.set_speed(1.0)
        self.sky.sync_clock()

    def _time_goto(self) -> None:
        current_local = self.engine.time.current_datetime().astimezone()
        dlg = TimeDialog(current_local, self)
        if dlg.exec():
            self.engine.time.set_datetime(dlg.datetime_utc())
            self.sky.sync_clock()

    # --- seleção / informações ----------------------------------------
    def _on_selection(self, selection) -> None:
        if selection is None:
            self.info_dock.hide()
            return
        self.info_dock.show()
        self._refresh_info()

    def _refresh_info(self) -> None:
        if self.info_dock.isVisible() and self.sky.selection is not None:
            self.info_panel.show_html(
                build_info_html(
                    self.sky.selection, self.engine, self.star_catalog,
                    self.const_names, self.dso_catalog,
                )
            )

    # --- painel de controle ------------------------------------------
    def _wire_control_panel(self) -> None:
        p = self.control_panel
        p.magCapChanged.connect(self.sky.set_mag_cap)
        p.layerToggled.connect(self._on_panel_layer)
        p.catalogToggled.connect(self._on_catalog_toggled)
        p.timeStep.connect(self._on_time_step)
        p.timeNow.connect(self._time_now)
        p.mouseModeChanged.connect(self.sky.set_mouse_mode)
        p.chartModeChanged.connect(self.sky.set_chart_mode)
        p.trackRequested.connect(self._open_track)
        p.refresh_night()

    def _on_panel_layer(self, key: str, value: bool) -> None:
        act = self._layer_acts.get(key)
        if act is not None and act.isChecked() != value:
            act.setChecked(value)  # dispara o toggled -> aplica e persiste
        else:
            self._on_layer_toggled(key, value)

    def _on_catalog_toggled(self, catalog: str, visible: bool) -> None:
        self.dso_catalog.set_catalog_visible(catalog, visible)
        self.sky.update()

    def _on_time_step(self, seconds: float) -> None:
        self.engine.time.step(seconds)
        self.sky.sync_clock()
        self.control_panel.refresh_night()

    def _open_track(self) -> None:
        """Abre a janela de rastreamento para o objeto selecionado."""
        from ..core.tracking import compute_track
        from .track_window import TrackWindow

        selection = self.sky.selection
        if selection is None:
            QMessageBox.information(
                self, "Carina",
                self.tr("Selecione um objeto no céu (ou pela busca) para "
                        "rastrear sua trajetória na noite."),
            )
            return
        kind, key = selection
        icrs = None
        if kind == "star":
            idx = int(key)
            label = (
                self.star_catalog.proper.get(idx)
                or self.star_catalog.label(idx, "bayer")
                or f"HIP {int(self.star_catalog.hip[idx])}"
            )
            icrs = self.star_catalog.xyz[idx]
        elif kind == "dso":
            data = self.dso_catalog.get(int(key))
            if data is None:
                return
            label = data["name"]
            if data.get("common"):
                label += f" — {data['common'].split(',')[0]}"
            import math as _math

            cd = _math.cos(data["dec"])
            icrs = [
                cd * _math.cos(data["ra"]), cd * _math.sin(data["ra"]),
                _math.sin(data["dec"]),
            ]
        else:
            label = str(key)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = compute_track(
                self.engine, selection, label, icrs,
                self.engine.time.current_datetime(),
            )
        finally:
            QApplication.restoreOverrideCursor()

        win = TrackWindow(result, self.settings.location().name, self)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.destroyed.connect(
            lambda *_: self._track_windows.remove(win)
            if win in self._track_windows else None
        )
        self._track_windows.append(win)
        win.show()

    def _manage_dso(self) -> None:
        dlg = DsoManagerDialog(self.dso_catalog, self)
        dlg.exec()
        self.dso_catalog.reload()
        self.sky.update()
        self._refresh_info()

    def _export_view(self) -> None:
        """Exporta a vista atual do céu (PNG/JPG/PDF) — base do item 11."""
        path, selected = QFileDialog.getSaveFileName(
            self, self.tr("Exportar vista"), "carina_mapa.png",
            "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf)",
        )
        if not path:
            return
        img = self.sky.grabFramebuffer()
        try:
            if path.lower().endswith(".pdf") or "PDF" in selected:
                from PySide6.QtCore import QMarginsF, QRectF
                from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

                if not path.lower().endswith(".pdf"):
                    path += ".pdf"
                writer = QPdfWriter(path)
                writer.setPageSize(QPageSize(QPageSize.A4))
                writer.setPageOrientation(
                    QPageLayout.Landscape if img.width() >= img.height()
                    else QPageLayout.Portrait
                )
                writer.setPageMargins(
                    QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter
                )
                writer.setResolution(300)
                painter = QPainter(writer)
                page = QRectF(0, 0, writer.width(), writer.height())
                scale = min(page.width() / img.width(),
                            page.height() / img.height())
                w, h = img.width() * scale, img.height() * scale
                painter.drawImage(
                    QRectF((page.width() - w) / 2, (page.height() - h) / 2, w, h),
                    img,
                )
                painter.end()
            else:
                img.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, "Carina",
                self.tr("Falha ao exportar: {e}").format(e=exc),
            )
            return
        self.statusBar().showMessage(
            self.tr("Vista exportada: {p}").format(p=path), 6000
        )

    def _open_search(self) -> None:
        from .search_dialog import SearchDialog

        dlg = SearchDialog(self.star_catalog, self.dso_catalog, self)
        dlg.goto_requested.connect(self.sky.goto_object)
        dlg.exec()

    def _open_fov(self) -> None:
        """Simulador de campo de visão dos equipamentos (item 7)."""
        from ..catalogs.equipment import EquipmentStore
        from .fov_dialog import FovDialog

        if not hasattr(self, "_equipment"):
            self._equipment = EquipmentStore(
                user_data_path() / "equipamentos.json"
            )
        dlg = FovDialog(self._equipment, self)
        dlg.fovChanged.connect(self.sky.set_fov_shapes)
        dlg.exec()

    def _open_eclipses(self) -> None:
        from .eclipse_dialog import EclipseDialog

        dlg = EclipseDialog(self.engine, self)
        dlg.goto_requested.connect(self._goto_eclipse)
        dlg.exec()

    def _goto_eclipse(self, when_utc, body: str) -> None:
        self.engine.time.set_datetime(when_utc)
        self.engine.time.set_speed(0.0)  # pausa no instante do máximo
        self.sky.sync_clock()
        self.sky.goto_object(("body", body))

    def _on_status(self, text: str) -> None:
        self.statusBar().showMessage(text)
        self._refresh_info()

    def _edit_location(self) -> None:
        dlg = LocationDialog(self.settings.location(), self)
        if dlg.exec():
            loc = dlg.location()
            self.settings.set_location(loc)
            self.engine.set_location(loc)
            self.sky.location_name = loc.name
            self.sky.update()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            self.tr("Sobre o Carina"),
            self.tr(
                "<b>Carina {v}</b><br>"
                "Planetário desktop em Python — PySide6 + OpenGL + Skyfield."
                "<br><br>Dados: HYG v4.1 (CC BY-SA), d3-celestial (BSD-3), "
                "OpenNGC (CC BY-SA 4.0), catálogos SH2/Barnard/Melotte via "
                "VizieR e SIMBAD (CDS), imagens DSS2 via hips2fits (CDS), "
                "efemérides JPL DE440s.<br>"
                "Textura da Via Láctea: <b>ESO/S. Brunier</b> (CC BY 4.0)."
            ).format(v=__version__),
        )
