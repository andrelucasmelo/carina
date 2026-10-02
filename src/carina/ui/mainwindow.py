"""Janela principal do Carina."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QInputDialog, QMainWindow,
    QLabel, QMessageBox, QWidget,
)

from .. import __version__
from ..catalogs import names, skygeometry
from ..catalogs.dso import DsoCatalog
from ..catalogs.stars import StarCatalog
from ..config import Settings, ephemeris_dir, package_data_dir, user_data_path
from ..core.dsofilter import DsoFilter
from ..core.engine import SkyEngine
from ..core.objects import ObjectRef
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
    # Controle ÚNICO do solo: marcado = solo opaco; desmarcado = enxerga
    # o céu abaixo do horizonte. A camada 'below_horizon' é o oposto
    # exato (mantida por SkyWidget.set_layer) e não tem entrada própria.
    ("ground", "Solo opaco (desmarque para ver abaixo do horizonte)",
     "G", True),
    ("cardinals", "Pontos cardeais", "Q", True),
    ("star_names", "Nomes das estrelas", "N", True),
    ("planet_names", "Nomes dos planetas", None, True),
    ("dso_names", "Rótulos do céu profundo", None, True),
    ("dso_images", "Imagens dos objetos (DSS) no céu", "I", False),
    ("atmosphere", "Atmosfera", "A", True),
    ("refraction", "Refração atmosférica", "R", True),
]


class _ClickLabel(QLabel):
    """Campo da barra de estado que reage ao clique (hora → data/hora;
    local → localização; campo → volta a 90°)."""

    clicked = Signal()

    def __init__(self, tip: str, parent=None) -> None:
        super().__init__(parent)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("padding: 0 8px;")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Janela principal: monta o aplicativo e liga as pontas.

    Cria o motor, os catálogos e o :class:`SkyWidget`; constrói menus,
    barra lateral e docks; e implementa os handlers que traduzem ações de
    interface em chamadas ao núcleo (abrir diálogos, calcular trajetórias,
    montar maratonas, alternar camadas). Nenhuma astronomia acontece aqui —
    apenas orquestração.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Carina {__version__}")
        self.resize(1280, 800)

        self.settings = Settings()
        # idioma dos nomes comuns (português / inglês / latim)
        names.set_language(
            self.settings.value("names/language", names.DEFAULT_LANGUAGE, str)
        )
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
        # filtro de exibição do céu profundo salvo nas preferências (§9)
        self.sky.set_dso_filter(
            DsoFilter.from_json(self.settings.value("dso/filter", "", str))
        )
        self.sky.statusUpdated.connect(self._on_status)
        self.sky.selectionChanged.connect(self._on_selection)
        self.sky.contextInfoRequested.connect(self._popup_info)
        self.sky.contextDetailsRequested.connect(self._open_object_window)
        self.sky.contextTrackRequested.connect(lambda _s: self._open_track())
        self.sky.contextFovRequested.connect(self._open_fov_for)
        self.sky.layerToggleRequested.connect(self._on_layer_toggled)
        self.sky.followChanged.connect(self._on_follow_changed)
        self.sky.statusParts.connect(self._on_status_parts)
        self.sky.noticeShown.connect(
            lambda text: self.statusBar().showMessage(text, 8000))

        # barra de estado com campos clicáveis (revisão 2026-10)
        status = self.statusBar()
        self.lbl_location = _ClickLabel(self.tr("Clique para mudar a localização"))
        self.lbl_time = _ClickLabel(self.tr("Clique para ir a uma data/hora"))
        self.lbl_fov = _ClickLabel(self.tr("Clique para voltar ao campo de 90°"))
        self.lbl_cursor = QLabel()
        for widget in (self.lbl_location, self.lbl_time, self.lbl_fov, self.lbl_cursor):
            status.addPermanentWidget(widget)
        self.lbl_location.clicked.connect(self._edit_location)
        self.lbl_time.clicked.connect(self._time_goto)
        self.lbl_fov.clicked.connect(self._reset_fov)

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
        self._restore_view_state()
        self.act_sidebar_labels.setChecked(
            self.settings.value("ui/sidebar_labels", False, bool))

        report = self.dso_catalog.migration_report
        if report:
            # a cópia do usuário recebeu catálogos novos (B-023): avisar uma
            # única vez, depois que a janela estiver na tela
            QTimer.singleShot(600, lambda: self._notify_migration(report))

    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        """Barra de menus (revisão 2026-10, §4): oito menus agrupados por
        tarefa — Arquivo · Exibir (submenus Objetos / Linhas e grades /
        Rótulos / Céu) · Tempo · Local · Objetos · Sistema Solar · Planejar
        · Ajuda. As ações de camada ficam em ``self._layer_acts`` para
        sincronizarem com a barra lateral e com o QSettings; os dicionários
        ``_mag_acts``, ``_const_acts``, ``_bortle_acts`` e ``_step_acts``
        servem à restauração do estado salvo.
        """
        bar = self.menuBar()
        layer = self._make_layer_actions()

        # --- Arquivo ---------------------------------------------------
        m_file = bar.addMenu(self.tr("&Arquivo"))
        self._add(m_file, self.tr("Exportar vista…"), self._export_view, "Ctrl+S")
        self._add(m_file, self.tr("Gerar mapa para impressão…"),
                  self._open_print_map, "Ctrl+Shift+P")
        m_file.addSeparator()
        self._add(m_file, self.tr("Sair"), self.close, QKeySequence.Quit)

        # --- Exibir ----------------------------------------------------
        m_view = bar.addMenu(self.tr("&Exibir"))
        m_obj = m_view.addMenu(self.tr("Objetos"))
        for key in ("stars", "planets", "dso", "dso_images", "milkyway"):
            m_obj.addAction(layer[key])
        m_lines = m_view.addMenu(self.tr("Linhas e grades"))
        for key in ("const_lines", "const_bounds", "grid_altaz", "grid_eq",
                    "meridian", "ecliptic", "equator", "horizon", "cardinals"):
            m_lines.addAction(layer[key])

        m_labels = m_view.addMenu(self.tr("Rótulos"))
        for key in ("star_names", "planet_names", "dso_names"):
            m_labels.addAction(layer[key])
        m_labels.addSeparator()
        name_group = QActionGroup(self)
        self.act_proper = QAction(self.tr("Estrelas pelo nome próprio"), self)
        self.act_bayer = QAction(self.tr("Estrelas por Bayer (genitivo)"), self)
        for act, mode in ((self.act_proper, "proper"), (self.act_bayer, "bayer")):
            act.setCheckable(True)
            act.setActionGroup(name_group)
            act.triggered.connect(lambda _=False, m=mode: self.sky.set_name_mode(m))
            m_labels.addAction(act)
        self.act_proper.setChecked(True)
        m_labels.addSeparator()
        dso_group = QActionGroup(self)
        self.act_dso_number = QAction(self.tr("Céu profundo pelo número de catálogo"), self)
        self.act_dso_name = QAction(self.tr("Céu profundo pelo nome"), self)
        for act, mode in ((self.act_dso_number, "number"), (self.act_dso_name, "name")):
            act.setCheckable(True)
            act.setActionGroup(dso_group)
            act.triggered.connect(
                lambda _=False, m=mode: self.sky.set_dso_name_mode(m))
            m_labels.addAction(act)
        self.act_dso_number.setChecked(True)
        self.act_caldwell = QAction(self.tr("Rotular Caldwell pela designação C"), self)
        self.act_caldwell.setCheckable(True)
        self.act_caldwell.setChecked(True)
        self.act_caldwell.setToolTip(
            self.tr("Desmarque para exibir a designação NGC/IC correspondente"))
        self.act_caldwell.toggled.connect(self.sky.set_prefer_caldwell)
        m_labels.addAction(self.act_caldwell)
        m_labels.addSeparator()
        m_const = m_labels.addMenu(self.tr("Nomes das constelações"))
        const_group = QActionGroup(self)
        self._const_acts: dict[str, QAction] = {}
        for label, mode in ((self.tr("Não exibir"), "none"), (self.tr("Português"), "pt"),
                            (self.tr("Latim (oficial)"), "latin"),
                            (self.tr("Abreviado (IAU)"), "abbr")):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(const_group)
            act.triggered.connect(
                lambda _c=False, mm=mode: self.sky.set_const_label_mode(mm))
            act.setChecked(mode == "none")
            m_const.addAction(act)
            self._const_acts[mode] = act
        m_lang = m_labels.addMenu(self.tr("Idioma dos nomes dos objetos"))
        lang_group = QActionGroup(self)
        for code, label in names.LANGUAGES.items():
            act = QAction(self.tr(label), self)
            act.setCheckable(True)
            act.setActionGroup(lang_group)
            act.setChecked(code == names.language())
            act.triggered.connect(
                lambda _c=False, c=code: self._set_names_language(c))
            m_lang.addAction(act)

        m_sky = m_view.addMenu(self.tr("Céu"))
        for key in ("atmosphere", "refraction", "ground"):
            m_sky.addAction(layer[key])
        m_sky.addSeparator()
        m_bortle = m_sky.addMenu(self.tr("Poluição luminosa (Bortle)"))
        bortle_group = QActionGroup(self)
        self._bortle_acts: dict[int, QAction] = {}
        for level, label in {
            1: "1 — céu perfeito", 2: "2 — céu muito escuro", 3: "3 — céu rural",
            4: "4 — transição rural/suburbano", 5: "5 — céu suburbano",
            6: "6 — subúrbio claro", 7: "7 — transição subúrbio/cidade",
            8: "8 — céu urbano", 9: "9 — centro de cidade",
        }.items():
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(bortle_group)
            act.triggered.connect(lambda _c=False, lv=level: self._set_bortle(lv))
            act.setChecked(level == 1)
            m_bortle.addAction(act)
            self._bortle_acts[level] = act
        m_mag = m_sky.addMenu(self.tr("Magnitude máxima das estrelas"))
        mag_group = QActionGroup(self)
        self._mag_acts: dict = {}
        for label, value in [(self.tr("Automática (pelo zoom)"), None), ("3,0", 3.0),
                             ("4,0", 4.0), ("4,5", 4.5), ("5,0", 5.0), ("5,5", 5.5),
                             ("6,0", 6.0), ("6,5", 6.5), ("7,0", 7.0), ("8,0", 8.0),
                             ("9,0", 9.0), ("10,0", 10.0), ("11,0", 11.0), ("12,0", 12.0)]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(mag_group)
            act.triggered.connect(lambda _c=False, v=value: self.sky.set_mag_cap(v))
            act.setChecked(value is None)
            m_mag.addAction(act)
            self._mag_acts[value] = act

        m_view.addSeparator()
        self._add(m_view, self.tr("Filtros do céu profundo…"),
                  self._open_dso_filter, "Ctrl+Shift+C")
        m_view.addSeparator()
        self.act_chart = self._add(m_view, self.tr("Modo mapa para impressão"),
                                   None, "Ctrl+M", checkable=True)
        self.act_chart.toggled.connect(self._on_chart_from_menu)
        self.act_follow = self._add(m_view, self.tr("Seguir objeto selecionado"),
                                    None, "F", checkable=True)
        self.act_follow.toggled.connect(self._toggle_follow)
        self._add(m_view, self.tr("Voltar à vista anterior"), self._go_back, "Backspace")
        m_view.addSeparator()
        self.act_sidebar_labels = self._add(
            m_view, self.tr("Rótulos na barra lateral"), None, None, checkable=True)
        self.act_sidebar_labels.toggled.connect(self._toggle_sidebar_labels)
        m_view.addAction(self.info_dock.toggleViewAction())
        m_view.addAction(self.side_dock.toggleViewAction())

        # --- Tempo -----------------------------------------------------
        m_time = bar.addMenu(self.tr("&Tempo"))
        for title, shortcut, slot in (
            (self.tr("Agora"), "8", self._time_now),
            (self.tr("Pausar / continuar"), "K", self._time_pause),
            (self.tr("Mais devagar"), "J", self._time_slower),
            (self.tr("Mais rápido"), "L", self._time_faster),
            (self.tr("Velocidade normal (1x)"), "7", self._time_normal),
            (self.tr("Ir para data/hora…"), "Ctrl+T", self._time_goto),
        ):
            self._add(m_time, title, slot, shortcut)
        m_time.addSeparator()
        m_jump = m_time.addMenu(self.tr("Ir para"))
        for title, kind in (
            (self.tr("Pôr do sol"), "sunset"),
            (self.tr("Início da noite astronômica"), "dusk"),
            (self.tr("Meia-noite local"), "midnight"),
            (self.tr("Fim da noite astronômica"), "dawn"),
            (self.tr("Nascer do sol"), "sunrise"),
        ):
            self._add(m_jump, title, lambda _c=False, k=kind: self._goto_time(k))
        m_time.addSeparator()
        m_step = m_time.addMenu(self.tr("Passo dos botões ◀◀ / ▶▶"))
        step_group = QActionGroup(self)
        self._step_acts: dict[float, QAction] = {}
        for label, secs in [("1 minuto", 60), ("5 minutos", 300), ("15 minutos", 900),
                            ("30 minutos", 1800), ("1 hora", 3600), ("3 horas", 10800),
                            ("6 horas", 21600), ("12 horas", 43200), ("1 dia", 86400),
                            ("1 semana", 604800), ("1 mês (30 d)", 2592000),
                            ("1 ano (365 d)", 31536000)]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(step_group)
            act.triggered.connect(
                lambda _c=False, s=float(secs): setattr(self, "_time_step_seconds", s))
            act.setChecked(secs == 3600)
            m_step.addAction(act)
            self._step_acts[float(secs)] = act
        self._add(m_time, self.tr("Retroceder um passo"),
                  lambda: self._on_time_step(-self._time_step_seconds), "Ctrl+Left")
        self._add(m_time, self.tr("Avançar um passo"),
                  lambda: self._on_time_step(self._time_step_seconds), "Ctrl+Right")

        # --- Local -----------------------------------------------------
        m_local = bar.addMenu(self.tr("&Local"))
        self._add(m_local, self.tr("Localização…"), self._edit_location, "Ctrl+L")
        self._add(m_local, self.tr("Crepúsculos e noite…"), self._open_night_info, "Ctrl+I")

        # --- Objetos ---------------------------------------------------
        m_objs = bar.addMenu(self.tr("&Objetos"))
        self._add(m_objs, self.tr("Buscar…"), self._open_search, "Ctrl+F")
        self._add(m_objs, self.tr("Informações do objeto selecionado"),
                  self._show_selection_info, "Ctrl+J")
        self._add(m_objs, self.tr("Detalhes e gráfico anual…"),
                  self._open_object_window, "Ctrl+Shift+D")
        self._add(m_objs, self.tr("Rastrear na noite…"), self._open_track, "Ctrl+R")
        m_objs.addSeparator()
        self._add(m_objs, self.tr("Ir para a melhor hora desta noite"), self._goto_best_time)
        self._add(m_objs, self.tr("Ir para quando nasce"), self._goto_rise)
        m_objs.addSeparator()
        self._add(m_objs, self.tr("Gerenciar catálogo de céu profundo…"),
                  self._manage_dso, "Ctrl+D")

        # --- Sistema Solar ---------------------------------------------
        m_sol = bar.addMenu(self.tr("&Sistema Solar"))
        self._add(m_sol, self.tr("Eclipses…"), self._open_eclipses, "Ctrl+E")
        m_sol.addSeparator()
        self._add(m_sol, self.tr("Caminho dos planetas (365 dias)…"), self._open_planet_paths)
        self.act_paths_layer = self._add(m_sol, self.tr("Exibir caminhos dos planetas"),
                                         None, "Shift+P", checkable=True, checked=True)
        self.act_paths_layer.toggled.connect(self._toggle_planet_paths)
        self._add(m_sol, self.tr("Limpar caminhos dos planetas"),
                  lambda: self.sky.set_planet_paths([]))
        m_sol.addSeparator()
        self._add(m_sol, self.tr("Previsão da Lua (28 dias)…"), self._open_moon_forecast)
        self.act_moon_layer = self._add(m_sol, self.tr("Exibir previsão da Lua no céu"),
                                        None, "Shift+M", checkable=True)
        self.act_moon_layer.toggled.connect(self._toggle_moon_forecast)
        m_sol.addAction(layer["moon_zone"])

        # --- Planejar --------------------------------------------------
        m_plan = bar.addMenu(self.tr("&Planejar"))
        m_rot = m_plan.addMenu(self.tr("Roteiros"))
        for kind, label in (("M", self.tr("Maratona Messier…")),
                            ("C", self.tr("Maratona Caldwell…")),
                            ("OC", self.tr("Maratona de Aglomerados Abertos…")),
                            ("GC", self.tr("Maratona de Aglomerados Globulares…")),
                            ("NEB", self.tr("Maratona de Nebulosas…")),
                            ("DARK", self.tr("Maratona de Nebulosas Escuras…"))):
            self._add(m_rot, label, lambda _c=False, k=kind: self._open_marathon(k))
        m_rot.addSeparator()
        self._add(m_rot, self.tr("Melhores Objetos da Noite…"),
                  lambda: self._open_marathon("BEST"))
        m_rot.addSeparator()
        for kind, label in (("MONTH", self.tr("Destaques do mês…")),
                            ("SEASON", self.tr("Destaques da estação…")),
                            ("STARS", self.tr("Estrelas brilhantes…"))):
            self._add(m_rot, label, lambda _c=False, k=kind: self._open_marathon(k))
        self._add(m_plan, self.tr("Campo de visão (equipamentos)…"), self._open_fov, "Ctrl+K")
        m_plan.addSeparator()
        self._add(m_plan, self.tr("Configurar planejamento…"),
                  self._open_plan_settings, "Ctrl+Shift+O")

        # --- Ajuda -----------------------------------------------------
        m_help = bar.addMenu(self.tr("A&juda"))
        self._add(m_help, self.tr("Documentação"), self._open_docs, "F1")
        self._add(m_help, self.tr("Atalhos do teclado e do mouse…"),
                  self._open_shortcuts, "Ctrl+Shift+K")
        m_help.addSeparator()
        self._add(m_help, self.tr("Sobre o Carina"), self._about)

    # ------------------------------------------------------------------
    # Apoio à construção dos menus
    # ------------------------------------------------------------------
    def _add(self, menu, text: str, slot=None, shortcut=None,
             checkable: bool = False, checked: bool = False) -> QAction:
        """Cria, configura e insere uma ação num menu."""
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(shortcut)
        if checkable:
            act.setCheckable(True)
            act.setChecked(checked)
        if slot is not None:
            act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _make_layer_actions(self) -> dict[str, QAction]:
        """Uma ação marcável por camada (``_LAYER_ACTIONS``), ainda fora de
        qualquer menu — os submenus de Exibir e o menu Sistema Solar as
        distribuem. ``self._layer_acts`` sincroniza barra lateral e settings."""
        self._layer_acts: dict[str, QAction] = {}
        for key, title, shortcut, default in _LAYER_ACTIONS:
            act = QAction(self.tr(title), self)
            act.setCheckable(True)
            act.setChecked(default)
            if shortcut:
                if key == "ground":
                    # "V" era o atalho do antigo "ver abaixo do horizonte"
                    act.setShortcuts([shortcut, "V"])
                else:
                    act.setShortcut(shortcut)
            act.toggled.connect(lambda on, k=key: self._on_layer_toggled(k, on))
            self._layer_acts[key] = act
        return self._layer_acts

    # ------------------------------------------------------------------
    # Ações novas da revisão 2026-10
    # ------------------------------------------------------------------
    def _goto_time(self, kind: str) -> None:
        """Tempo ▸ Ir para: pôr do sol, noite astronômica, meia-noite,
        amanhecer ou nascer do sol da noite atual (pausa a simulação)."""
        import datetime as dt

        from ..core.localtime import to_local
        from ..core.twilight import night_info

        now = self.engine.time.current_datetime()
        if kind == "midnight":
            local = to_local(now)
            base = local.replace(hour=0, minute=0, second=0, microsecond=0)
            if local.hour >= 12:
                base += dt.timedelta(days=1)
            target = base.astimezone(dt.timezone.utc)
        else:
            info = night_info(self.engine, now)
            target = {"sunset": info.sunset, "dusk": info.astro_dusk,
                      "dawn": info.astro_dawn, "sunrise": info.sunrise}.get(kind)
        if target is None:
            self.statusBar().showMessage(self.tr(
                "Esse instante não ocorre nesta data para o local atual."), 6000)
            return
        self.engine.time.set_datetime(target)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()

    def _toggle_follow(self, on: bool) -> None:
        if on and self.sky.selection is None:
            self.act_follow.setChecked(False)
            self.statusBar().showMessage(
                self.tr("Selecione um objeto para seguir."), 5000)
            return
        self.sky.set_follow_selection(on)

    def _on_follow_changed(self, on: bool) -> None:
        if self.act_follow.isChecked() != on:
            self.act_follow.setChecked(on)

    def _go_back(self) -> None:
        if not self.sky.go_back():
            self.statusBar().showMessage(self.tr("Não há vista anterior."), 4000)

    def _goto_best_time(self) -> None:
        if self.sky.selection is None:
            self.statusBar().showMessage(self.tr("Selecione um objeto primeiro."), 5000)
            return
        self.sky.goto_best_time(self.sky.selection)

    def _goto_rise(self) -> None:
        if self.sky.selection is None:
            self.statusBar().showMessage(self.tr("Selecione um objeto primeiro."), 5000)
            return
        self.sky.goto_when_rises(self.sky.selection)

    def _open_fov_for(self, _selection) -> None:
        """'Enquadrar com equipamento' do menu de contexto."""
        self._open_fov()

    def _toggle_sidebar_labels(self, on: bool) -> None:
        self.side_bar.set_labels_visible(on)
        self.settings.set_value("ui/sidebar_labels", bool(on))

    def _reset_fov(self) -> None:
        """Clique no campo de visão da barra de estado: volta a 90°."""
        import math

        self.sky._push_view()
        self.sky.camera.fov = math.radians(90.0)
        self.sky.update()

    def _open_docs(self) -> None:
        """Ajuda ▸ Documentação: a pasta docs/ local ou, num build sem
        ela, a documentação publicada no repositório."""
        from pathlib import Path

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        local = Path(__file__).resolve().parents[3] / "docs" / "README.md"
        url = (QUrl.fromLocalFile(str(local)) if local.exists()
               else QUrl("https://github.com/andrelucasmelo/carina/tree/main/docs"))
        QDesktopServices.openUrl(url)

    def _open_shortcuts(self) -> None:
        from .shortcuts_dialog import ShortcutsDialog

        ShortcutsDialog(self.menuBar(), self).exec()

    def _on_status_parts(self, parts: dict) -> None:
        """Campos clicáveis da barra de estado."""
        self.lbl_location.setText(parts.get("location", ""))
        self.lbl_time.setText(
            " ".join(p for p in (parts.get("time", ""), parts.get("speed", "")) if p))
        self.lbl_fov.setText(parts.get("fov", ""))
        self.lbl_cursor.setText(parts.get("cursor", ""))

    def _on_layer_toggled(self, key: str, on: bool) -> None:
        """Ação de camada mudou: aplica na cena e sincroniza toda a UI.

        ``set_layer`` pode alterar MAIS de uma camada (ver as regras lá:
        solo ⇄ abaixo do horizonte, céu profundo → imagens), por isso a
        sincronização parte sempre do estado real de ``sky.layers``, e
        não do par (chave, valor) recebido.
        """
        self.sky.set_layer(key, on)
        self._sync_layer_ui()

    def _sync_layer_ui(self) -> None:
        """Espelha ``sky.layers`` nos menus, nos botões e no QSettings.

        O guard ``_syncing`` evita a recursão óbvia: ajustar uma ação
        dispara seu ``toggled``, que voltaria aqui.
        """
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        try:
            for key, value in self.sky.layers.items():
                act = self._layer_acts.get(key)
                if act is not None and act.isChecked() != value:
                    act.setChecked(value)
                if hasattr(self, "side_bar"):
                    self.side_bar.set_layer_state(key, value)
                self.settings.set_layer(key, value)
            if hasattr(self, "side_bar"):
                # o botão mestre acende enquanto houver marcações OU imagens
                self.side_bar.set_layer_state(
                    self.sky.DSO_MASTER, self.sky.deep_sky_on()
                )
        finally:
            self._syncing = False

    def _restore_layers(self) -> None:
        """Reaplica na inicialização o estado de camadas salvo no QSettings."""
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
        """Conecta os sinais da barra lateral aos handlers da janela."""
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
        """Despacha os botões de ação da barra lateral para os diálogos."""
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

        kinds = ["M", "C", "OC", "GC", "NEB", "DARK", "BEST",
                 "MONTH", "SEASON", "STARS"]
        labels = [MARATHON_TITLES[k] for k in kinds]
        choice, ok = QInputDialog.getItem(
            self, self.tr("Planejar observação"), self.tr("Maratona:"),
            labels, 0, False,
        )
        if ok:
            self._open_marathon(kinds[labels.index(choice)])

    def _on_chart_mode(self, on: bool) -> None:
        """Modo carta alternado pela barra lateral: sincroniza com o menu."""
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
        ref = ObjectRef.resolve(selection, self.star_catalog, self.dso_catalog)
        if ref is None:
            return
        label, icrs = ref.name, ref.icrs

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

    def _set_names_language(self, code: str) -> None:
        """Idioma dos nomes comuns: vale para mapa, ficha, busca e roteiros."""
        names.set_language(code)
        self.settings.set_value("names/language", code)
        self.sky.update()
        self._refresh_info()

    def _set_bortle(self, level: int) -> None:
        self.sky.set_bortle(level)
        self.statusBar().showMessage(
            self.tr("Poluição luminosa: Bortle {n} — mag. limite a olho nu "
                    "{m:.1f}").format(n=level, m=self.sky.BORTLE_NELM[level]),
            6000,
        )

    def _open_dso_filter(self) -> None:
        """Filtros de exibição do céu profundo (não modal: o mapa reage na
        hora a cada mudança)."""
        from .dso_filter_dialog import DsoFilterDialog

        dlg = getattr(self, "_filter_dialog", None)
        if dlg is None:
            dlg = DsoFilterDialog(self.dso_catalog, self.sky.dso_filter, self)
            dlg.changed.connect(self._apply_dso_filter)
            self._filter_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _apply_dso_filter(self, flt) -> None:
        """Aplica o filtro ao céu e o persiste nas preferências."""
        self.sky.set_dso_filter(flt)
        self.settings.set_value("dso/filter", flt.to_json())

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

    def _plan_settings(self):
        """Configuração de planejamento salva nas preferências."""
        from .plan_settings_dialog import load_settings

        return load_settings(self.settings)

    def _open_plan_settings(self) -> None:
        """Diálogo de configuração pelo menu Planejar (item avulso)."""
        from .plan_settings_dialog import PlanSettingsDialog, save_settings

        dlg = PlanSettingsDialog(self._plan_settings(), self)
        if dlg.exec():
            save_settings(self.settings, dlg.settings())

    def _build_plan(self, kind: str, settings):
        """Calcula o plano do tipo pedido com a configuração dada."""
        from ..core.observing import (
            build_bright_stars, build_marathon, build_period_plan,
        )

        now = self.engine.time.current_datetime()
        if kind == "STARS":
            plan = build_bright_stars(
                self.engine, self.star_catalog, now, self.const_names,
                settings=settings,
            )
        elif kind in ("MONTH", "SEASON"):
            plan = build_period_plan(
                self.engine, self.dso_catalog, self.star_catalog, kind, now,
                self.const_names, self.settings.location().latitude,
                settings=settings,
            )
        else:
            plan = build_marathon(
                self.engine, self.dso_catalog, self.star_catalog, kind, now,
                self.const_names, settings=settings,
            )
        plan.location = self.settings.location().name
        return plan

    def _open_marathon(self, kind: str) -> None:
        """Abre uma janela de planejamento (menu Planejar → Visual)."""
        from ..catalogs import skygeometry
        from ..config import package_data_dir
        from .marathon_window import MarathonWindow
        from .plan_settings_dialog import save_settings

        settings = self._plan_settings()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            plan = self._build_plan(kind, settings)
        finally:
            QApplication.restoreOverrideCursor()

        if not plan.entries:
            QMessageBox.information(
                self, "Carina",
                self.tr("Nenhum objeto deste tipo fica bem posicionado "
                        "com a configuração atual. Tente outra data ou "
                        "revise Planejar → Configurar planejamento."),
            )
            return
        # linhas de constelação para as cartas de localização do PDF
        if not hasattr(self, "_const_lines_cache"):
            self._const_lines_cache = skygeometry.load_constellation_lines(
                package_data_dir()
            )

        def recompute(new_settings):
            """Refaz o plano quando o usuário muda a configuração."""
            save_settings(self.settings, new_settings)
            return self._build_plan(kind, new_settings)

        win = MarathonWindow(
            plan, self.star_catalog, self._const_lines_cache, self,
            settings=settings, recompute_cb=recompute,
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
            # o popup tem a imagem própria no topo: a ficha vem sem ela
            return build_info_html(
                sel, self.engine, self.star_catalog, self.const_names,
                self.dso_catalog, include_image=False,
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
        ref = ObjectRef.resolve(selection, self.star_catalog, self.dso_catalog)
        if ref is None:
            return
        # sem a miniatura embutida: esta janela já mostra a imagem grande
        html = build_info_html(
            selection, self.engine, self.star_catalog, self.const_names,
            self.dso_catalog, include_image=False,
        )
        if not ref.is_fixed:
            QMessageBox.information(
                self, "Carina",
                self.tr("O gráfico anual vale para objetos fixos; corpos do "
                        "Sistema Solar mudam de posição. Use Sistema Solar → "
                        "Caminho dos planetas."),
            )
            return
        title = ref.data["name"] if ref.data else ref.name
        icrs = ref.icrs
        image_path = ref.image_path()

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

    # ------------------------------------------------------------------
    # Persistência da vista e das preferências de exibição (revisão
    # 2026-10): antes só local e camadas sobreviviam ao fechar
    # ------------------------------------------------------------------
    def _save_view_state(self) -> None:
        """Grava direção, campo, Bortle, teto de magnitude, modos de
        rótulo, passo de tempo e geometria da janela."""
        import math

        s = self.settings
        cam = self.sky.camera
        s.set_value("view/saved", True)
        s.set_value("view/az", math.degrees(cam.az))
        s.set_value("view/alt", math.degrees(cam.alt))
        s.set_value("view/fov", math.degrees(cam.fov))
        s.set_value("view/bortle", int(self.sky.bortle))
        s.set_value("view/mag_cap",
                    -1.0 if self.sky.mag_cap is None else float(self.sky.mag_cap))
        s.set_value("view/name_mode", self.sky.name_mode)
        s.set_value("view/dso_name_mode", self.sky.dso_name_mode)
        s.set_value("view/const_label_mode", self.sky.const_label_mode)
        s.set_value("view/prefer_caldwell", bool(self.sky.prefer_caldwell))
        s.set_value("view/time_step", float(self._time_step_seconds))
        s.set_value("window/geometry", self.saveGeometry())
        s.set_value("window/state", self.saveState())

    def _restore_view_state(self) -> None:
        """Reaplica o que :meth:`_save_view_state` gravou, sincronizando
        os menus (ações de rádio não disparam ``triggered`` ao marcar por
        código, por isso o valor é aplicado no céu explicitamente)."""
        import math

        from PySide6.QtCore import QByteArray

        from ..core.projection import FOV_MAX, FOV_MIN

        s = self.settings
        if not s.value("view/saved", False, bool):
            return
        cam = self.sky.camera
        cam.set_direction(math.radians(s.value("view/az", 0.0, float)),
                          math.radians(s.value("view/alt", 25.0, float)))
        cam.fov = max(FOV_MIN, min(
            FOV_MAX, math.radians(s.value("view/fov", 90.0, float))))

        bortle = max(1, min(9, s.value("view/bortle", 1, int)))
        self.sky.set_bortle(bortle)
        if bortle in self._bortle_acts:
            self._bortle_acts[bortle].setChecked(True)

        cap = s.value("view/mag_cap", -1.0, float)
        cap = None if cap < 0 else float(cap)
        self.sky.set_mag_cap(cap)
        if cap in self._mag_acts:
            self._mag_acts[cap].setChecked(True)

        name_mode = s.value("view/name_mode", "proper", str)
        self.sky.set_name_mode(name_mode)
        (self.act_bayer if name_mode == "bayer" else self.act_proper).setChecked(True)

        dso_mode = s.value("view/dso_name_mode", "number", str)
        self.sky.set_dso_name_mode(dso_mode)
        (self.act_dso_name if dso_mode == "name" else self.act_dso_number).setChecked(True)

        const_mode = s.value("view/const_label_mode", "none", str)
        self.sky.set_const_label_mode(const_mode)
        if const_mode in self._const_acts:
            self._const_acts[const_mode].setChecked(True)

        self.act_caldwell.setChecked(s.value("view/prefer_caldwell", True, bool))

        step = s.value("view/time_step", 3600.0, float)
        self._time_step_seconds = step
        if step in self._step_acts:
            self._step_acts[step].setChecked(True)

        geometry = s.value("window/geometry", QByteArray(), QByteArray)
        if not geometry.isEmpty():
            self.restoreGeometry(geometry)
        state = s.value("window/state", QByteArray(), QByteArray)
        if not state.isEmpty():
            self.restoreState(state)
        if self.sky.selection is None:
            self.info_dock.hide()
        self.sky.update()

    def closeEvent(self, event) -> None:
        """Salva o estado ao fechar (os testes automatizados não salvam,
        para não trocar a vista do usuário por uma cena de teste)."""
        if not getattr(self, "skip_state_save", False):
            self._save_view_state()
        super().closeEvent(event)

    def _notify_migration(self, report: dict) -> None:
        """Informa a atualização automática do banco de céu profundo."""
        def br(n: int) -> str:
            return f"{n:,}".replace(",", ".")

        text = self.tr(
            "A base de céu profundo foi atualizada para a versão {v}: "
            "{o} objetos e {d} designações novos."
        ).format(v=report["to"], o=br(report["objects"]),
                 d=br(report["designations"]))
        if report.get("magnitudes"):
            text += " " + self.tr("{m} magnitudes corrigidas.").format(
                m=br(report["magnitudes"]))
        text += "\n\n" + self.tr(
            "Cópia de segurança da base anterior:"
        ) + f"\n{report['backup']}"
        QMessageBox.information(self, "Carina", text)
        self.statusBar().showMessage(
            self.tr("Base de céu profundo atualizada (v{v})").format(
                v=report["to"]), 8000,
        )

    def _on_status(self, text: str) -> None:
        """A linha completa fica como tooltip da barra; os campos clicáveis
        vêm por ``_on_status_parts``. ``showMessage`` fica livre para avisos
        temporários (exportações, notificações do céu)."""
        self.statusBar().setToolTip(text)
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
