"""Janela principal do Carina."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QInputDialog, QMainWindow,
    QMessageBox, QWidget,
)

from .. import __version__
from ..catalogs import skygeometry
from ..catalogs.dso import DsoCatalog
from ..catalogs.stars import StarCatalog
from ..config import Settings, ephemeris_dir, package_data_dir, user_data_path
from ..core.engine import SkyEngine
from .dso_manager import DsoManagerDialog
from .infopanel import InfoPanel, build_info_html
from .location_dialog import LocationDialog
from .skywidget import SkyWidget
from .time_dialog import TimeDialog
from .toolbar import SideToolBar

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
    ("meridian", "Meridiano local", None, False),
    ("ecliptic", "Eclíptica", None, False),
    ("equator", "Equador celeste", None, False),
    ("milkyway", "Via Láctea", "M", True),
    ("horizon", "Linha do horizonte", "H", True),
    ("ground", "Solo (oculta o que está abaixo do horizonte)", "G", True),
    ("cardinals", "Pontos cardeais", "Q", True),
    ("star_names", "Nomes das estrelas", "N", True),
    ("planet_names", "Nomes dos planetas", None, True),
    ("dso_names", "Rótulos do céu profundo", None, True),
    ("dso_images", "Imagens dos objetos (DSS) no céu", "I", False),
    ("below_horizon", "Ver o céu abaixo do horizonte", "V", False),
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
        self.sky.contextInfoRequested.connect(self._popup_info)
        self.sky.contextDetailsRequested.connect(self._open_object_window)
        self.sky.contextTrackRequested.connect(lambda _s: self._open_track())

        self.info_dock = QDockWidget(self.tr("Informações"), self)
        self.info_dock.setObjectName("info_dock")
        self.info_panel = InfoPanel(self.info_dock)
        self.info_dock.setWidget(self.info_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)
        self.info_dock.hide()

        # barra lateral compacta (botões quadrados)
        self.side_bar = SideToolBar(self)
        self.side_dock = QDockWidget(self.tr("Ferramentas"), self)
        self.side_dock.setObjectName("side_dock")
        self.side_dock.setWidget(self.side_bar)
        self.side_dock.setTitleBarWidget(QWidget())  # sem barra de título
        self.side_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.side_dock)
        self._wire_side_bar()
        self._track_windows: list = []
        self._time_step_seconds = 3600.0

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

        m_time.addSeparator()
        m_step = m_time.addMenu(self.tr("Passo dos botões ◀◀ / ▶▶"))
        step_group = QActionGroup(self)
        for label, secs in [
            ("1 minuto", 60), ("5 minutos", 300), ("15 minutos", 900),
            ("30 minutos", 1800), ("1 hora", 3600), ("3 horas", 10800),
            ("6 horas", 21600), ("12 horas", 43200), ("1 dia", 86400),
            ("1 semana", 604800), ("1 mês (30 d)", 2592000),
            ("1 ano (365 d)", 31536000),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(step_group)
            act.triggered.connect(
                lambda _c=False, s=float(secs): setattr(
                    self, "_time_step_seconds", s
                )
            )
            if secs == 3600:
                act.setChecked(True)
            m_step.addAction(act)
        m_time.addSeparator()
        for title, shortcut, secs in (
            (self.tr("Retroceder um passo"), "Ctrl+Left", -1.0),
            (self.tr("Avançar um passo"), "Ctrl+Right", 1.0),
        ):
            act = QAction(title, self)
            act.setShortcut(shortcut)
            act.triggered.connect(
                lambda _c=False, s=secs: self._on_time_step(
                    s * self._time_step_seconds
                )
            )
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
        m_mag = m_view.addMenu(self.tr("Magnitude máxima das estrelas"))
        mag_group = QActionGroup(self)
        for label, value in [
            (self.tr("Automática (pelo zoom)"), None), ("3,0", 3.0),
            ("4,0", 4.0), ("4,5", 4.5), ("5,0", 5.0), ("5,5", 5.5),
            ("6,0", 6.0), ("6,5", 6.5), ("7,0", 7.0), ("8,0", 8.0),
            ("9,0", 9.0), ("10,0", 10.0), ("11,0", 11.0), ("12,0", 12.0),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(mag_group)
            act.triggered.connect(
                lambda _c=False, v=value: self.sky.set_mag_cap(v)
            )
            if value is None:
                act.setChecked(True)
            m_mag.addAction(act)

        m_view.addSeparator()
        m_const = m_view.addMenu(self.tr("Nomes das constelações"))
        const_group = QActionGroup(self)
        for label, mode in (
            (self.tr("Não exibir"), "none"),
            (self.tr("Português"), "pt"),
            (self.tr("Latim (oficial)"), "latin"),
            (self.tr("Abreviado (IAU)"), "abbr"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(const_group)
            act.triggered.connect(
                lambda _c=False, mm=mode: self.sky.set_const_label_mode(mm)
            )
            if mode == "none":
                act.setChecked(True)
            m_const.addAction(act)

        m_bortle = m_view.addMenu(self.tr("Poluição luminosa (Bortle)"))
        bortle_group = QActionGroup(self)
        bortle_desc = {
            1: "1 — céu perfeito", 2: "2 — céu muito escuro",
            3: "3 — céu rural", 4: "4 — transição rural/suburbano",
            5: "5 — céu suburbano", 6: "6 — subúrbio claro",
            7: "7 — transição subúrbio/cidade", 8: "8 — céu urbano",
            9: "9 — centro de cidade",
        }
        for level, label in bortle_desc.items():
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(bortle_group)
            act.triggered.connect(
                lambda _c=False, lv=level: self._set_bortle(lv)
            )
            if level == 1:
                act.setChecked(True)
            m_bortle.addAction(act)

        m_view.addSeparator()
        self.act_chart = QAction(self.tr("Modo mapa para impressão"), self)
        self.act_chart.setCheckable(True)
        self.act_chart.setShortcut("Ctrl+M")
        self.act_chart.toggled.connect(self._on_chart_from_menu)
        m_view.addAction(self.act_chart)
        m_view.addAction(self.info_dock.toggleViewAction())
        m_view.addAction(self.side_dock.toggleViewAction())

        m_dso = bar.addMenu(self.tr("&Céu profundo"))
        act_manage = QAction(self.tr("Gerenciar objetos e catálogos…"), self)
        act_manage.setShortcut("Ctrl+D")
        act_manage.triggered.connect(self._manage_dso)
        m_dso.addAction(act_manage)

        m_dso.addSeparator()
        act_cats = QAction(self.tr("Configurar catálogos exibidos…"), self)
        act_cats.setShortcut("Ctrl+Shift+C")
        act_cats.triggered.connect(self._open_catalogs)
        m_dso.addAction(act_cats)
        act_details = QAction(self.tr("Detalhes do objeto selecionado…"), self)
        act_details.setShortcut("Ctrl+Shift+D")
        act_details.triggered.connect(self._open_object_window)
        m_dso.addAction(act_details)

        m_dso.addSeparator()
        self.act_caldwell = QAction(
            self.tr("Rotular Caldwell pela designação C"), self
        )
        self.act_caldwell.setCheckable(True)
        self.act_caldwell.setChecked(True)
        self.act_caldwell.setToolTip(
            self.tr("Desmarque para exibir a designação NGC/IC correspondente")
        )
        self.act_caldwell.toggled.connect(self.sky.set_prefer_caldwell)
        m_dso.addAction(self.act_caldwell)

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
        m_tools.addSeparator()
        act_paths = QAction(self.tr("Caminho dos planetas (365 dias)…"), self)
        act_paths.triggered.connect(self._open_planet_paths)
        m_tools.addAction(act_paths)
        self.act_paths_layer = QAction(
            self.tr("Exibir caminhos dos planetas"), self
        )
        self.act_paths_layer.setCheckable(True)
        self.act_paths_layer.setChecked(True)
        self.act_paths_layer.setShortcut("Shift+P")
        self.act_paths_layer.toggled.connect(self._toggle_planet_paths)
        m_tools.addAction(self.act_paths_layer)
        act_clear_paths = QAction(self.tr("Limpar caminhos dos planetas"), self)
        act_clear_paths.triggered.connect(
            lambda: self.sky.set_planet_paths([])
        )
        m_tools.addAction(act_clear_paths)
        act_moon = QAction(self.tr("Previsão da Lua (28 dias)…"), self)
        act_moon.triggered.connect(self._open_moon_forecast)
        m_tools.addAction(act_moon)
        self.act_moon_layer = QAction(
            self.tr("Exibir previsão da Lua no céu"), self
        )
        self.act_moon_layer.setCheckable(True)
        self.act_moon_layer.setShortcut("Shift+M")
        self.act_moon_layer.toggled.connect(self._toggle_moon_forecast)
        m_tools.addAction(self.act_moon_layer)

        m_tools.addSeparator()
        act_print = QAction(self.tr("Gerar mapa para impressão…"), self)
        act_print.setShortcut("Ctrl+Shift+P")
        act_print.triggered.connect(self._open_print_map)
        m_tools.addAction(act_print)

        # --- menu Planejar: maratonas de observação visual --------------
        m_planejar = bar.addMenu(self.tr("&Planejar"))
        m_visual = m_planejar.addMenu(self.tr("Visual"))
        for kind, label in (
            ("M", self.tr("Maratona Messier…")),
            ("C", self.tr("Maratona Caldwell…")),
            ("OC", self.tr("Maratona de Aglomerados Abertos…")),
            ("GC", self.tr("Maratona de Aglomerados Globulares…")),
            ("NEB", self.tr("Maratona de Nebulosas…")),
            ("DARK", self.tr("Maratona de Nebulosas Escuras…")),
        ):
            act_k = QAction(label, self)
            act_k.triggered.connect(
                lambda _=False, k=kind: self._open_marathon(k)
            )
            m_visual.addAction(act_k)
        m_visual.addSeparator()
        act_best = QAction(self.tr("Melhores Objetos da Noite…"), self)
        act_best.triggered.connect(lambda: self._open_marathon("BEST"))
        m_visual.addAction(act_best)

        m_planejar.addSeparator()
        m_minutes = m_planejar.addMenu(self.tr("Tempo por objeto"))
        saved_min = int(self.settings.value("marathon/minutes", 4, int))
        group_min = QActionGroup(self)
        for minutes in range(3, 11):
            act_min = QAction(self.tr("{n} minutos").format(n=minutes), self)
            act_min.setCheckable(True)
            act_min.setChecked(minutes == saved_min)
            act_min.triggered.connect(
                lambda _=False, v=minutes: self.settings.set_value(
                    "marathon/minutes", v
                )
            )
            group_min.addAction(act_min)
            m_minutes.addAction(act_min)

        m_info = bar.addMenu(self.tr("&Informações"))
        act_night = QAction(self.tr("Crepúsculos e noite…"), self)
        act_night.setShortcut("Ctrl+I")
        act_night.triggered.connect(self._open_night_info)
        m_info.addAction(act_night)
        act_sel = QAction(self.tr("Objeto selecionado"), self)
        act_sel.setShortcut("Ctrl+J")
        act_sel.triggered.connect(self._show_selection_info)
        m_info.addAction(act_sel)

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
        if hasattr(self, "side_bar"):
            self.side_bar.set_layer_state(key, on)

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
        from ..core.localtime import to_local

        current_local = to_local(self.engine.time.current_datetime())
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

    # --- barra lateral -------------------------------------------------
    def _wire_side_bar(self) -> None:
        b = self.side_bar
        b.layerToggled.connect(self._on_panel_layer)
        b.mouseModeChanged.connect(self.sky.set_mouse_mode)
        b.chartModeChanged.connect(self._on_chart_mode)
        b.timeStep.connect(
            lambda sign: self._on_time_step(sign * self._time_step_seconds)
        )
        b.timeNow.connect(self._time_now)
        b.action.connect(self._on_side_action)

    def _on_side_action(self, kind: str) -> None:
        {
            "search": self._open_search,
            "track": self._open_track,
            "fov": self._open_fov,
            "marathon": self._ask_marathon,
            "print": self._open_print_map,
            "info": self._open_night_info,
        }[kind]()

    def _ask_marathon(self) -> None:
        """Escolha rápida da maratona pelo botão lateral."""
        from ..core.observing import MARATHON_TITLES

        kinds = ["M", "C", "OC", "GC", "NEB", "DARK", "BEST"]
        labels = [MARATHON_TITLES[k] for k in kinds]
        choice, ok = QInputDialog.getItem(
            self, self.tr("Planejar observação"), self.tr("Maratona:"),
            labels, 0, False,
        )
        if ok:
            self._open_marathon(kinds[labels.index(choice)])

    def _on_chart_mode(self, on: bool) -> None:
        self.sky.set_chart_mode(on)
        if self.act_chart.isChecked() != on:
            self.act_chart.setChecked(on)

    def _open_night_info(self) -> None:
        from .night_dialog import NightInfoDialog

        dlg = NightInfoDialog(
            self.engine, self.settings.location().name, self
        )
        dlg.exec()

    def _show_selection_info(self) -> None:
        if self.sky.selection is None:
            QMessageBox.information(
                self, "Carina",
                self.tr("Nenhum objeto selecionado. Clique num objeto do céu "
                        "ou use a busca (Ctrl+F)."),
            )
            return
        self.info_dock.show()
        self._refresh_info()

    def _on_chart_from_menu(self, on: bool) -> None:
        self.sky.set_chart_mode(on)
        if self.side_bar.btn_chart.isChecked() != on:
            self.side_bar.btn_chart.setChecked(on)

    def _on_panel_layer(self, key: str, value: bool) -> None:
        if key == "moon_forecast":
            self.act_moon_layer.setChecked(value)
            return
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

    def _set_bortle(self, level: int) -> None:
        self.sky.set_bortle(level)
        self.statusBar().showMessage(
            self.tr("Poluição luminosa: Bortle {n} — mag. limite a olho nu "
                    "{m:.1f}").format(n=level, m=self.sky.BORTLE_NELM[level]),
            6000,
        )

    def _open_catalogs(self) -> None:
        from .catalog_dialog import CatalogDialog

        dlg = CatalogDialog(self.dso_catalog, self)
        dlg.changed.connect(self.sky.update)
        dlg.exec()
        self.sky.update()

    def _open_planet_paths(self) -> None:
        """Traça o caminho dos planetas nos próximos 365 dias (item 8)."""
        from ..core.engine import _BODIES
        from ..core.planetpath import compute_path

        names = [n for n, _k, _c in _BODIES if n not in ("Sol", "Lua")]
        chosen, ok = QInputDialog.getItem(
            self, self.tr("Caminho dos planetas"),
            self.tr("Planeta (365 dias a partir da data da simulação):"),
            [self.tr("Todos os planetas")] + names, 0, False,
        )
        if not ok:
            return
        targets = names if chosen == self.tr("Todos os planetas") else [chosen]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            start = self.engine.time.current_datetime()
            paths = [
                compute_path(self.engine, name, start, days=365)
                for name in targets
            ]
        finally:
            QApplication.restoreOverrideCursor()
        self.sky.set_planet_paths(paths)
        total_events = sum(len(p.events) for p in paths)
        self.statusBar().showMessage(
            self.tr("{n} trajetória(s) traçada(s) · {e} evento(s) "
                    "(oposições, conjunções, elongações)")
            .format(n=len(paths), e=total_events), 8000,
        )

    def _open_moon_forecast(self) -> None:
        """Calcula e exibe a previsão da Lua para os próximos 28 dias."""
        from ..core.planetpath import compute_moon_forecast

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            marks = compute_moon_forecast(
                self.engine, self.engine.time.current_datetime(), days=28
            )
        finally:
            QApplication.restoreOverrideCursor()
        self.sky.set_moon_forecast(marks)
        self.act_moon_layer.setChecked(True)
        self.side_bar.set_layer_state("moon_forecast", True)
        phases = [m for m in marks if m.phase_name]
        from ..core.planetpath import EVENT_LABEL

        from ..core.localtime import to_local

        resumo = " · ".join(
            f"{EVENT_LABEL.get(m.phase_name, m.phase_name)} "
            f"{to_local(m.when_utc):%d/%m}" for m in phases
        )
        self.statusBar().showMessage(
            self.tr("Previsão da Lua: 28 dias · {r}").format(r=resumo), 15000
        )

    def _toggle_moon_forecast(self, on: bool) -> None:
        if on and not self.sky.moon_forecast:
            self._open_moon_forecast()
            return
        self.sky.layers["moon_forecast"] = on
        self.side_bar.set_layer_state("moon_forecast", on)
        self.sky.update()

    def _toggle_planet_paths(self, on: bool) -> None:
        """Liga/desliga a EXIBIÇÃO dos caminhos sem descartar o cálculo."""
        self.sky.layers["planet_paths"] = on
        self.sky.update()

    def _open_marathon(self, kind: str) -> None:
        """Planejamento das maratonas de observação (menu Planejar)."""
        from ..catalogs import skygeometry
        from ..config import package_data_dir
        from ..core.observing import build_marathon
        from .marathon_window import MarathonWindow

        minutes = int(self.settings.value("marathon/minutes", 4, int))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            plan = build_marathon(
                self.engine, self.dso_catalog, self.star_catalog, kind,
                self.engine.time.current_datetime(), self.const_names,
                minutes_per_object=minutes,
            )
            plan.location = self.settings.location().name
        finally:
            QApplication.restoreOverrideCursor()

        if not plan.entries:
            QMessageBox.information(
                self, "Carina",
                self.tr("Nenhum objeto deste tipo fica bem posicionado "
                        "nesta noite. Tente outra data."),
            )
            return
        # linhas de constelação para as cartas de localização do PDF
        if not hasattr(self, "_const_lines_cache"):
            self._const_lines_cache = skygeometry.load_constellation_lines(
                package_data_dir()
            )
        win = MarathonWindow(
            plan, self.star_catalog, self._const_lines_cache, self
        )
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.gotoRequested.connect(self._goto_by_name)
        self._track_windows.append(win)
        win.show()

    def _goto_by_name(self, name: str) -> None:
        """Centraliza o objeto do roteiro no mapa (duplo clique na lista)."""
        row = self.dso_catalog.cx.execute(
            "SELECT id FROM objects WHERE name = ? LIMIT 1", (name,)
        ).fetchone()
        if row:
            self.sky.goto_object(("dso", int(row["id"])))
            return
        # maratona "Melhores Objetos": planetas e a Lua não são DSOs
        self.sky.goto_object(("body", name))

    def _open_print_map(self) -> None:
        """Abre o editor de mapa para impressão com a vista atual."""
        was_chart = self.sky.chart_mode
        if not was_chart:
            self.sky.set_chart_mode(True)
            self.sky.repaint()
        image = self.sky.grabFramebuffer()
        if not was_chart:
            self.sky.set_chart_mode(False)

        from .print_window import PrintMapWindow

        from ..core.localtime import to_local

        loc = self.settings.location().name
        when = to_local(self.engine.time.current_datetime())
        win = PrintMapWindow(
            image, f"{loc} — {when:%d/%m/%Y %H:%M}", self
        )
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        self._track_windows.append(win)
        win.show()

    def _popup_info(self, selection) -> None:
        """Ficha do objeto em popup (item 7, botão direito)."""
        from ..catalogs import images as image_store
        from .info_popup import InfoPopup

        if selection is None:
            return

        def render(sel):
            return build_info_html(
                sel, self.engine, self.star_catalog, self.const_names,
                self.dso_catalog,
            )

        image_path = None
        if selection[0] == "dso":
            data = self.dso_catalog.get(int(selection[1]))
            if data is not None:
                image_path = image_store.image_path_for(data["name"])
        popup = InfoPopup(
            selection, self.sky.describe_selection(selection),
            render(selection), image_path, refresh_cb=render, parent=self,
        )
        popup.detailsRequested.connect(self._open_object_window)
        popup.trackRequested.connect(self._track_selection)
        popup.show()

    def _track_selection(self, selection) -> None:
        self.sky.selection = selection
        self.sky.selectionChanged.emit(selection)
        self._open_track()

    def _open_object_window(self, selection=None) -> None:
        """Janela de detalhes do objeto (item 3)."""
        import math as _math

        from ..catalogs import images as image_store
        from .object_window import ObjectWindow, yearly_altitude

        if not isinstance(selection, tuple):
            selection = self.sky.selection
        if selection is None:
            QMessageBox.information(
                self, "Carina",
                self.tr("Selecione um objeto (clique no céu ou use Ctrl+F)."),
            )
            return
        kind, key = selection
        html = build_info_html(
            selection, self.engine, self.star_catalog, self.const_names,
            self.dso_catalog,
        )
        icrs = None
        title = str(key)
        image_path = None
        if kind == "dso":
            data = self.dso_catalog.get(int(key))
            if data is None:
                return
            title = data["name"]
            cd = _math.cos(data["dec"])
            icrs = [cd * _math.cos(data["ra"]), cd * _math.sin(data["ra"]),
                    _math.sin(data["dec"])]
            image_path = image_store.image_path_for(data["name"])
        elif kind == "star":
            idx = int(key)
            title = (self.star_catalog.proper.get(idx)
                     or self.star_catalog.label(idx, "bayer") or f"HIP {idx}")
            icrs = self.star_catalog.xyz[idx]
        else:
            QMessageBox.information(
                self, "Carina",
                self.tr("O gráfico anual vale para objetos fixos; corpos do "
                        "Sistema Solar mudam de posição. Use Ferramentas → "
                        "Caminho dos planetas."),
            )
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dates, alt_mid, alt_max = yearly_altitude(
                self.engine, icrs, self.engine.time.current_datetime()
            )
        finally:
            QApplication.restoreOverrideCursor()
        win = ObjectWindow(title, html, image_path, dates, alt_mid, alt_max,
                           self)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        self._track_windows.append(win)
        win.show()

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
