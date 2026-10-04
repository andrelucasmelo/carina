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
from .infopanel import build_info_html
from .object_card import CardContext, ObjectCard
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
    ("moon_labels", "Nomes das formações da Lua", None, True),
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
        # banco do usuário (listas, diário, horizonte do quintal — v0.15)
        from ..core import userdata

        self.userdata = userdata.get()
        self.horizon_profile = self.userdata.active_horizon()
        self.sky.set_horizon_profile(self.horizon_profile)
        self.sky.statusUpdated.connect(self._on_status)
        self.sky.selectionChanged.connect(self._on_selection)
        self.sky.contextInfoRequested.connect(self._popup_info)
        self.sky.contextDetailsRequested.connect(self._open_object_window)
        self.sky.contextTrackRequested.connect(lambda _s: self._open_track())
        self.sky.contextFovRequested.connect(self._open_fov_for)
        self.sky.contextAction.connect(self._on_card_action)
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

        self.info_dock = QDockWidget(self.tr("Ficha do objeto"), self)
        self.info_dock.setObjectName("info_dock")
        # ficha unificada (v0.15 T5): a mesma do popup e da janela de detalhes
        self.card = ObjectCard(self._card_context(), parent=self.info_dock)
        self.card.actionRequested.connect(self._on_card_action)
        self.info_dock.setWidget(self.card)
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
        if self.settings.value("ui/night_mode", False, bool):
            self.act_night.setChecked(True)     # no campo, abre já no vermelho
        self._setup_field_tools()

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
        self._add(m_file, self.tr("Gerar carta celeste…"),
                  self._open_chart_dialog, "Ctrl+Shift+P")
        self._add(m_file, self.tr("Anotar a vista atual…"), self._open_print_map)
        self._add(m_file, self.tr("Minha foto no mapa…"), self._open_photo_overlay)
        m_file.addSeparator()
        self._add(m_file, self.tr("Preferências…"), self._open_preferences, "Ctrl+,")
        m_file.addSeparator()
        self._add(m_file, self.tr("Sair"), self.close, QKeySequence.Quit)

        # --- Exibir ----------------------------------------------------
        m_view = bar.addMenu(self.tr("&Exibir"))
        m_obj = m_view.addMenu(self.tr("Objetos"))
        for key in ("stars", "planets", "dso", "dso_images", "milkyway"):
            m_obj.addAction(layer[key])
        # catálogos inteiros de uma vez (pré-0.17): atalho do filtro de exibição
        self._cat_menu = m_obj.addMenu(self.tr("Catálogos do céu profundo"))
        self._cat_menu.aboutToShow.connect(self._fill_catalog_menu)
        m_lines = m_view.addMenu(self.tr("Linhas e grades"))
        for key in ("const_lines", "const_bounds", "grid_altaz", "grid_eq",
                    "meridian", "ecliptic", "equator", "horizon", "cardinals"):
            m_lines.addAction(layer[key])

        m_labels = m_view.addMenu(self.tr("Rótulos"))
        for key in ("star_names", "planet_names", "moon_labels", "dso_names"):
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
        self._names_acts = {}
        for code, label in names.LANGUAGES.items():
            act = QAction(self.tr(label), self)
            act.setCheckable(True)
            act.setActionGroup(lang_group)
            act.setChecked(code == names.language())
            act.triggered.connect(
                lambda _c=False, c=code: self._set_names_language(c))
            m_lang.addAction(act)
            self._names_acts[code] = act

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
        self.act_night = self._add(m_view, self.tr("Modo noturno (vermelho)"),
                                   None, "Ctrl+N", checkable=True)
        self.act_night.toggled.connect(self._toggle_night)
        self.act_fullscreen = self._add(m_view, self.tr("Tela cheia"), None, "F11",
                                        checkable=True)
        self.act_fullscreen.toggled.connect(
            lambda on: self.showFullScreen() if on else self.showNormal())
        self.act_observe = self._add(m_view, self.tr("Modo observação"), None,
                                     "Ctrl+Shift+F", checkable=True)
        self.act_observe.toggled.connect(self._toggle_observing)
        self.act_slider = self._add(m_view, self.tr("Linha do tempo da noite"), None, None,
                                    checkable=True, checked=True)
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
        self._add(m_local, self.tr("Horizonte do quintal…"), self._open_horizon)
        self._saved_menu = m_local.addMenu(self.tr("Locais salvos"))
        self._saved_menu.aboutToShow.connect(self._fill_saved_locations)

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
        self._add(m_objs, self.tr("Minhas listas…"), self._open_lists, "Ctrl+Shift+L")
        self._add(m_objs, self.tr("★ Acrescentar seleção à minha lista"),
                  self._add_selection_to_list, "Ctrl+B")
        self._add(m_objs, self.tr("Diário de observação…"), self._open_journal,
                  "Ctrl+Shift+J")
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
        self._add(m_sol, self.tr("Planetas…"), self._open_planets, "Ctrl+Shift+E")
        self._add(m_sol, self.tr("A Lua em detalhe…"), self._open_moon_window)
        self._add(m_sol, self.tr("Previsão da Lua (28 dias)…"), self._open_moon_forecast)
        self.act_moon_layer = self._add(m_sol, self.tr("Exibir previsão da Lua no céu"),
                                        None, "Shift+M", checkable=True)
        self.act_moon_layer.toggled.connect(self._toggle_moon_forecast)
        m_sol.addAction(layer["moon_zone"])

        # --- Planejar --------------------------------------------------
        m_plan = bar.addMenu(self.tr("&Planejar"))
        self._add(m_plan, self.tr("Hoje à noite…"), self._open_tonight, "T")
        self._add(m_plan, self.tr("Calendário do céu…"), self._open_sky_calendar,
                  "Ctrl+Shift+A")
        self._add(m_plan, self.tr("Calendário de noites escuras…"), self._open_dark_calendar,
                  "Ctrl+Shift+N")
        self._add(m_plan, self.tr("Sessão de astrofoto…"), self._open_session, "Ctrl+Shift+S")
        self._add(m_plan, self.tr("Companheiro no celular…"), self._open_companion)
        self._add(m_plan, self.tr("Satélites e ISS…"), self._open_satellites)
        m_moon = m_plan.addMenu(self.tr("Lua"))
        self._add(m_moon, self.tr("A Lua em detalhe…"), self._open_moon_window, "Ctrl+Shift+M")
        self._add(m_moon, self.tr("Planejador de foto lunar…"), self._open_moon_planner)
        self._add(m_moon, self.tr("Lunar 100…"), self._open_lunar100)
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
        self._add(m_rot, self.tr("Roteiro da minha lista…"), self._plan_current_list)
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
        self._add(m_help, self.tr("Ajuda do Carina"), self._open_help, "F1")
        self._add(m_help, self.tr("O que há de novo"),
                  lambda: self._open_help("NOVIDADES.md"))
        self._add(m_help, self.tr("Abrir a documentação no navegador"), self._open_docs)
        self._add(m_help, self.tr("Assistente de primeiro uso…"), self.run_first_run)
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

    # --- campo (v0.16 T5) ---------------------------------------------------
    def _setup_field_tools(self) -> None:
        """Linha do tempo da noite no rodapé, preferências e relógio de 1 s."""
        from PySide6.QtWidgets import QToolBar

        from .preferences_dialog import apply_font_scale
        from .widgets.night_slider import NightSlider

        self.night_slider = NightSlider()
        self.night_slider.timeChosen.connect(self._slider_time)
        bar = QToolBar(self.tr("Linha do tempo da noite"))
        bar.setObjectName("night_slider_bar")
        bar.setMovable(False)
        bar.addWidget(self.night_slider)
        self.addToolBar(Qt.BottomToolBarArea, bar)
        self._slider_bar = bar
        self.act_slider.toggled.connect(bar.setVisible)
        self.act_slider.setChecked(self.settings.value("ui/night_slider", True, bool))
        self.act_slider.toggled.connect(
            lambda on: self.settings.set_value("ui/night_slider", on)
            if not getattr(self, "skip_state_save", False) else None)
        self._slider_night_key = None
        scale = self.settings.value("ui/font_scale", 100, int)
        if scale != 100:
            apply_font_scale(scale)
        self.sky.label_scale = self.settings.value("sky/label_scale", 100, int) / 100.0
        self._next_card = None
        self._field_timer = QTimer(self)
        self._field_timer.setInterval(1000)
        self._field_timer.timeout.connect(self._tick_field)
        self._field_timer.start()
        QTimer.singleShot(0, self._tick_field)

    def _tick_field(self) -> None:
        from ..core.visibility import _noon_before, night_grid

        now = self.engine.time.current_datetime()
        key = (_noon_before(now), self.settings.location().name)
        try:
            if key != self._slider_night_key:
                self.night_slider.set_night(night_grid(self.engine, now))
                self._slider_night_key = key
            self.night_slider.set_now(now)
        except Exception:  # noqa: BLE001 — o rodapé não pode derrubar a janela
            pass
        card = self._next_card
        if card is not None and card.isVisible():
            card.tick(now)
            card.adjustSize()
            card.move(14, self.sky.height() - card.height() - 14)

    def _slider_time(self, when) -> None:
        self.engine.time.set_datetime(when)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()

    def _latest_plan(self):
        for w in reversed(self._track_windows):
            try:
                plan = getattr(w, "plan", None)
            except RuntimeError:
                continue
            if plan is not None and getattr(plan, "entries", None):
                return plan
        return None

    def _toggle_observing(self, on: bool) -> None:
        """Exibir ▸ Modo observação: sem painéis, rótulos grandes, cartão do
        próximo alvo do roteiro aberto."""
        from .observing_mode import LABEL_SCALE, NextTargetCard

        base = self.settings.value("sky/label_scale", 100, int) / 100.0
        if on:
            self._docks_before = (self.info_dock.isVisible(), self.side_dock.isVisible())
            self.info_dock.hide()
            self.side_dock.hide()
            self.sky.label_scale = base * LABEL_SCALE
            if self._next_card is None:
                self._next_card = NextTargetCard(self.sky)
                self._next_card.gotoRequested.connect(
                    lambda k, i, _w: self._goto_ident(k, i))
                self._next_card.observedRequested.connect(
                    lambda k, i, w: self._observed_ident(k, i, w))
            self._next_card.set_plan(self._latest_plan())
            self._next_card.show()
            self._next_card.raise_()
            self._tick_field()
        else:
            info, side = getattr(self, "_docks_before", (False, True))
            self.info_dock.setVisible(info and self.sky.selection is not None)
            self.side_dock.setVisible(side)
            self.sky.label_scale = base
            if self._next_card is not None:
                self._next_card.hide()
        self.sky.update()

    def _observed_ident(self, kind: str, ident: str, when) -> None:
        ref = ObjectRef.from_ident(kind, ident, self.star_catalog, self.dso_catalog)
        if ref is not None:
            self._mark_observed(ref.selection, when)

    def _open_preferences(self) -> None:
        from .preferences_dialog import PreferencesDialog, apply_font_scale

        dlg = PreferencesDialog(self.settings, self)
        if dlg.exec():
            self.set_language(dlg.language.currentData())
            dlg.save()
            apply_font_scale(dlg.font_scale.value())
            base = dlg.label_scale.value() / 100.0
            self.sky.label_scale = base * (1.45 if self.act_observe.isChecked() else 1.0)
            self.sky.update()
            self._refresh_cards()

    def _toggle_night(self, on: bool) -> None:
        """Exibir ▸ Modo noturno (Ctrl+N): céu e interface em vermelho (v0.16 T2)."""
        from .nightmode import NightMode

        if not hasattr(self, "_night"):
            self._night = NightMode()
        self._night.apply(on)
        if on:
            self.sky.set_theme("red")
        else:
            self.sky.set_theme("light" if self.act_chart.isChecked() else "dark")
        self.act_chart.setEnabled(not on)       # papel branco no vermelho ofuscaria
        self.card.show_image = not on           # fotos coloridas quebram a adaptação
        self._refresh_cards(reselect=True)
        if not getattr(self, "skip_state_save", False):
            self.settings.set_value("ui/night_mode", on)
        self.statusBar().showMessage(
            self.tr("Modo noturno ligado") if on else self.tr("Modo noturno desligado"), 4000)

    def _open_dark_calendar(self) -> None:
        """Tempo ▸ Calendário de noites escuras (v0.15 T12)."""
        from ..core.localtime import to_local
        from .dark_calendar import DarkCalendarDialog

        today = to_local(self.engine.time.current_datetime()).date()
        dlg = DarkCalendarDialog(self.engine, today, self)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.dateChosen.connect(self._goto_night_of)
        self._dark_calendar = dlg
        dlg.show()

    # --- Lua e calendário do céu (v0.17) --------------------------------
    def _open_sky_calendar(self) -> None:
        """Planejar ▸ Calendário do céu."""
        from ..core.localtime import to_local
        from .calendar_window import CalendarWindow

        today = to_local(self.engine.time.current_datetime()).date()
        win = CalendarWindow(self.engine, today, self.settings.location().name, self,
                             settings=self.settings)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.gotoEvent.connect(self._goto_sky_event)
        self._sky_calendar = win
        win.show()

    def _goto_sky_event(self, event) -> None:
        """Leva o céu ao instante de um evento do calendário."""
        self.engine.time.set_datetime(event.start_utc)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        target = event.target
        if target in ("Lua", "Sol", "Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno",
                      "Urano", "Netuno"):
            self.sky.goto_object(("body", target))
        elif target.startswith("HIP "):
            self._goto_ident("star", target)
        self.statusBar().showMessage(
            f"{event.title} — {event.local_start():%d/%m/%Y %H:%M}", 8000)

    def _open_moon_window(self, feature: str | None = None) -> None:
        """Planejar ▸ Lua ▸ A Lua em detalhe."""
        from ..core import moon as moonlib
        from ..render import moontex
        from .moon_window import MoonWindow

        if not moontex.available():
            QMessageBox.information(self, self.tr("A Lua"), self.tr(
                "Os dados lunares não foram encontrados nesta instalação."))
            return
        win = getattr(self, "_moon_window", None)
        try:
            alive = win is not None and win.isVisible()
        except RuntimeError:
            alive = False
        if not alive:
            win = MoonWindow(self.engine, self.engine.time.current_datetime(), self,
                             observed=self.userdata.observed_idents())
            win.setAttribute(Qt.WA_DeleteOnClose, True)
            win.markObserved.connect(self._mark_observed_ident)
            self._moon_window = win
        else:
            win.set_time(self.engine.time.current_datetime())
        win.show()
        win.raise_()
        if feature:
            f = moonlib.find_feature(feature)
            if f is not None and f.lat == f.lat:
                win.select_feature(f)
                win.canvas.center_on(f, 3.0)

    def _open_photo_overlay(self) -> None:
        """Arquivo ▸ Minha foto no mapa (v0.19)."""
        from .photo_overlay import PHOTO_KIND, PhotoOverlayDialog

        dlg = PhotoOverlayDialog(
            self.star_catalog, self._selected_star_index, self, userdata=self.userdata,
            current=self.userdata.profile(PHOTO_KIND, "atual"))
        dlg.overlayChanged.connect(self.sky.set_photo_overlay)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        self._photo_dialog = dlg
        dlg.show()

    def _selected_star_index(self):
        sel = self.sky.selection
        return int(sel[1]) if sel and sel[0] == "star" else None

    def restore_photo_overlay(self) -> None:
        """Volta a foto alinhada da última sessão."""
        from .photo_overlay import PHOTO_KIND, overlay_from_profile

        d = self.userdata.profile(PHOTO_KIND, "atual")
        if d:
            ov = overlay_from_profile(d)
            if ov is not None:
                self.sky.set_photo_overlay(ov)

    def _open_satellites(self) -> None:
        """Planejar ▸ Satélites e ISS (v0.19)."""
        from .satellites_dialog import SatellitesDialog

        dlg = SatellitesDialog(self.engine, self)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.showPass.connect(self._show_sat_pass)
        self._satellites = dlg
        dlg.show()

    def _show_sat_pass(self, tle, p) -> None:
        """Leva o relógio ao nascer da passagem e desenha a trilha."""
        import datetime as dt
        import math

        from ..core import orbital as O

        pts = O.track(self.engine, tle, p.rise, p.set, 10.0)
        self.sky.set_sat_track(tle.name, pts, tle)
        start = p.visible_from or p.rise
        self.engine.time.set_datetime(start - dt.timedelta(seconds=30))
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        # aponta para o ponto mais alto, campo amplo
        top = max(pts, key=lambda tv: tv[1][2])[1]
        self.sky.camera.set_direction(math.atan2(top[1], top[0]),
                                      max(0.35, math.asin(max(-1.0, min(1.0, top[2]))) * 0.7))
        self.sky.camera.fov = math.radians(100.0)
        self.sky.update()

    def _open_companion(self) -> None:
        """Planejar ▸ Companheiro no celular (v0.19)."""
        from .companion_dialog import CompanionDialog

        dlg = getattr(self, "_companion", None)
        try:
            alive = dlg is not None and dlg.isVisible()
        except RuntimeError:
            alive = False
        if not alive:
            dlg = CompanionDialog(self.companion_plan, self)
            dlg.setAttribute(Qt.WA_DeleteOnClose, True)
            # o servidor roda em outra thread: o sinal chega na fila da interface
            dlg.observedReceived.connect(self._companion_observed, Qt.QueuedConnection)
            self._companion = dlg
            dlg.start()
        dlg.show()
        dlg.raise_()

    def companion_plan(self) -> dict:
        """Roteiro para o celular: o plano aberto, a sessão de astrofoto ou,
        sem nenhum dos dois, os melhores alvos de hoje à noite (chamado na
        thread da interface pelo diálogo, que guarda a cópia para o servidor)."""
        from ..core.localtime import to_local

        observed = self.userdata.observed_idents()
        items = []
        title = "Carina"
        subtitle = self.settings.location().name
        plan_win = next((w for w in reversed(self._track_windows)
                         if hasattr(w, "plan") and getattr(w.plan, "entries", None)), None)
        sess = getattr(self, "_session_window", None)
        try:
            if plan_win is not None:
                plan = plan_win.plan
                title = plan.title
                for e in plan.entries:
                    items.append({
                        "time": f"{to_local(e.when_utc):%H:%M}", "name": e.catalog_id,
                        "kind": e.kind, "ident": e.ident or e.name,
                        "detail": f"{e.type_label} · {e.constellation} · alt {e.altitude:.0f}°"
                                  + (f" · {e.how_to_find}" if e.how_to_find else ""),
                    })
            elif sess is not None and sess.plan is not None and sess.plan.blocks:
                title = "Sessão de astrofoto"
                for b in sess.plan.blocks:
                    tg = sess.plan.targets[b.target]
                    items.append({
                        "time": f"{to_local(b.start):%H:%M}", "name": tg.name,
                        "kind": tg.kind, "ident": tg.ident,
                        "detail": f"até {to_local(b.end):%H:%M} · alt {b.alt_min:.0f}–{b.alt_max:.0f}°"
                                  + (" · virar a montagem no fim" if b.flip_after else ""),
                    })
            else:
                from ..core.tonight import tonight_summary

                s = tonight_summary(self.engine, self.dso_catalog,
                                    self.engine.time.current_datetime(), bortle=self.sky.bortle,
                                    horizon=self.horizon_profile, n_best=12)
                title = "Hoje à noite"
                subtitle += f" · {s.verdict}"
                for it in s.planets + s.best:
                    items.append({
                        "time": f"{to_local(it.best_utc):%H:%M}" if it.best_utc else "",
                        "name": it.name, "kind": it.kind, "ident": it.ident,
                        "detail": f"{it.type_label} · nota {it.score} · {it.explain}",
                    })
        except RuntimeError:
            pass
        for it in items:
            it["observed"] = (it["kind"], it["ident"]) in observed
        return {"title": title, "subtitle": subtitle, "items": items}

    def _companion_observed(self, kind: str, ident: str, name: str) -> None:
        """Registro vindo do celular: entra no diário sem diálogo."""
        self.userdata.add_observation(kind, ident, name,
                                      location=self.settings.location().name,
                                      note="registrado pelo celular", bortle=self.sky.bortle)
        self.statusBar().showMessage(self.tr("{o} observado (pelo celular)").format(o=name), 6000)
        self._refresh_cards(reselect=True)
        dlg = getattr(self, "_companion", None)
        try:
            if dlg is not None:
                dlg.refresh_plan()
        except RuntimeError:
            pass

    def _open_session(self, selection=None) -> None:
        """Planejar ▸ Sessão de astrofoto (v0.19). Com ``selection`` (menu do
        botão direito), acrescenta aquele objeto à sessão aberta ou nova."""
        from .session_window import SessionWindow

        if isinstance(selection, bool):          # sinal triggered(bool) do menu
            selection = None

        win = getattr(self, "_session_window", None)
        try:
            alive = win is not None and win.isVisible()
        except RuntimeError:
            alive = False
        if not alive:
            win = SessionWindow(
                self.engine, self.engine.time.current_datetime(), self,
                equipment=self.equipment(), userdata=self.userdata,
                bortle=lambda: self.sky.bortle, horizon=lambda: self.horizon_profile,
                current_target=self._session_target,
                active_setup=self.settings.value("equipment/active_setup", "", str),
                settings=self.settings, candidates=self._session_candidates,
                resolve=self._session_resolve)
            win.setAttribute(Qt.WA_DeleteOnClose, True)
            win.gotoTarget.connect(self._goto_ident)
            win.fovRequested.connect(self._open_fov_from_session)
            self._session_window = win
            if selection is None:
                win.add_current()
        if selection is not None:
            got = self._session_target(selection)
            if got is not None:
                win.add_target(*got)
        win.show()
        win.raise_()

    def _open_fov_from_session(self) -> None:
        """Botão "Campo de visão…" da sessão: cria/edita setups e volta."""
        self._open_fov()
        win = getattr(self, "_session_window", None)
        if win is not None:
            try:
                win.refresh_setups(self.settings.value("equipment/active_setup", "", str))
            except RuntimeError:
                pass

    def _session_resolve(self, kind: str, ident: str):
        """(nome, icrs, ident, kind, tamanho′) a partir do identificador."""
        ref = ObjectRef.from_ident(kind, ident, self.star_catalog, self.dso_catalog)
        return self._session_target(ref.selection) if ref is not None else None

    def _session_candidates(self) -> list[dict]:
        """Candidatos às sugestões da sessão: objetos de céu profundo com
        designação conhecida e foto embarcada (as mesmas da ficha)."""
        import numpy as np

        from ..catalogs import names
        from ..catalogs.dso import type_label
        from ..catalogs.images import image_path_for

        rows = self.dso_catalog.cx.execute(
            "SELECT name, common, klass, type, ra, dec, mag, maj, min FROM objects"
            " WHERE enabled = 1 AND klass != 'OTHER'"
            "   AND (name LIKE 'M %' OR name LIKE 'NGC%' OR name LIKE 'IC %'"
            "        OR name LIKE 'Sh2%' OR common != '')"
            "   AND (mag <= 12.5 OR maj >= 8.0)").fetchall()
        out = []
        for r in rows:
            if image_path_for(r["name"]) is None:
                continue
            ra, dec = float(r["ra"]), float(r["dec"])
            common = names.common_label(r["common"]) if r["common"] else ""
            out.append({
                "kind": "dso", "ident": r["name"], "name": r["name"],
                "label": f"{r['name']} — {common}" if common else r["name"],
                "common": common, "klass": r["klass"], "type_label": type_label(r["type"]),
                "mag": r["mag"], "maj": r["maj"], "min": r["min"],
                "icrs": np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra),
                                  np.sin(dec)]),
            })
        return out

    def _session_target(self, sel=None):
        """(nome, icrs, ident, kind, tamanho′) do objeto (padrão: o selecionado)."""
        sel = self.sky.selection if sel is None else sel
        if sel is None:
            return None
        ref = ObjectRef.resolve(sel, self.star_catalog, self.dso_catalog)
        if ref is None or ref.icrs is None:
            return None
        size = (ref.data or {}).get("maj") if ref.kind == "dso" else 0.0
        return (ref.name, ref.icrs, ref.ident, ref.kind, size or 0.0)

    def _open_planets(self, planet=None) -> None:
        """Sistema Solar ▸ Planetas (v0.18)."""
        from .planet_window import PlanetWindow

        if not isinstance(planet, str):
            sel = self.sky.selection
            planet = sel[1] if sel and sel[0] == "body" and sel[1] not in ("Sol", "Lua") \
                else "Júpiter"
        win = getattr(self, "_planet_window", None)
        try:
            alive = win is not None and win.isVisible()
        except RuntimeError:
            alive = False
        if not alive:
            win = PlanetWindow(self.engine, self.engine.time.current_datetime(), self,
                               settings=self.settings,
                               constellation_fn=self.sky.constellation_name, planet=planet)
            win.setAttribute(Qt.WA_DeleteOnClose, True)
            win.gotoPlanet.connect(self._goto_planet_at)
            win.chartRequested.connect(self._planet_finder_chart)
            self._planet_window = win
        else:
            win.set_time(self.engine.time.current_datetime())
            win.select(planet)
        win.show()
        win.raise_()

    def _planet_finder_chart(self, name: str, when) -> None:
        """Carta de busca: o gerador de carta enquadrando o planeta em 8°."""
        import math

        self.engine.time.set_datetime(when)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        self.sky.goto_object(("body", name), animate=False)   # sem animação: a carta
        self.sky.camera.fov = math.radians(8.0)                # lê a vista na hora
        self.sky.update()
        self._open_chart_dialog()

    def _goto_planet_at(self, name: str, when) -> None:
        self.engine.time.set_datetime(when)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        self.sky.goto_object(("body", name))

    def _open_moon_planner(self) -> None:
        from ..catalogs.equipment import EquipmentStore
        from .moon_planner import MoonPlannerDialog

        if not hasattr(self, "_equipment"):
            self._equipment = EquipmentStore(user_data_path() / "equipamentos.json")
        dlg = MoonPlannerDialog(self.engine, self.engine.time.current_datetime(),
                                self._equipment, self)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.nightChosen.connect(self._goto_moon_time)
        self._moon_planner = dlg
        dlg.show()

    def _goto_moon_time(self, when) -> None:
        self.engine.time.set_datetime(when)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        self.sky.goto_object(("body", "Lua"))

    def _open_lunar100(self) -> None:
        from .moon_planner import Lunar100Dialog

        dlg = Lunar100Dialog(self.userdata.observed_idents(), self)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.showFeature.connect(self._open_moon_window)
        dlg.markObserved.connect(self._mark_observed_ident)
        self._lunar100 = dlg
        dlg.show()

    def _mark_observed_ident(self, kind: str, ident: str, name: str) -> bool:
        """Diário para alvos fora do mapa (formações lunares)."""
        from PySide6.QtWidgets import QDialog

        from .journal_dialog import ObservationDialog

        dlg = ObservationDialog(name, self.engine.time.current_datetime(),
                                self.settings.location().name, self._instruments(),
                                self.sky.bortle, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        values = dlg.values()
        when = values.pop("when_utc")
        self.userdata.add_observation(kind, ident, name, when, **values)
        self.statusBar().showMessage(self.tr("{o} registrado no diário").format(o=name), 5000)
        observed = self.userdata.observed_idents()
        for attr, method in (("_moon_window", "set_observed"), ("_lunar100", "reload")):
            w = getattr(self, attr, None)
            try:
                if w is not None and w.isVisible():
                    getattr(w, method)(observed)
            except RuntimeError:
                pass
        return True

    def show_today_if_needed(self) -> None:
        """Cartão "Hoje no céu" ao abrir, quando há eventos ou lembretes."""
        import datetime as dt

        from ..core import events as skyevents
        from .calendar_window import TodayDialog, today_events

        if not self.settings.value("calendar/show_today", True, bool):
            return
        now = dt.datetime.now(dt.timezone.utc)
        try:
            skyevents.purge_old_reminders(now)
            due = skyevents.due_reminders(now)
            todays = [e for e in today_events(self.engine, now) if e.importance >= 2]
        except Exception:
            return
        if not due and not todays:
            return
        dlg = TodayDialog(todays, due, self, settings=self.settings)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.openCalendar.connect(self._open_sky_calendar)
        self._today_dialog = dlg
        dlg.show()

    def _goto_night_of(self, date) -> None:
        """Leva a simulação ao fim do crepúsculo astronômico da data."""
        import datetime as dt

        from ..core.localtime import from_local_naive
        from ..core.twilight import night_info

        ref = from_local_naive(dt.datetime(date.year, date.month, date.day, 20, 0))
        info = night_info(self.engine, ref.astimezone(dt.timezone.utc))
        target = info.astro_dusk or info.nautical_dusk or info.sunset or ref
        self.engine.time.set_datetime(target)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        self.statusBar().showMessage(self.tr("Noite de {d:%d/%m/%Y}").format(d=date), 5000)

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
        self._goto_best_tonight(self.sky.selection)

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
        self.card.set_selection(selection)

    def _refresh_info(self) -> None:
        if self.info_dock.isVisible() and self.sky.selection is not None:
            if self.card.selection != self.sky.selection:
                self.card.set_selection(self.sky.selection)
            else:
                self.card.refresh()

    # --- ficha do objeto (v0.15 T5) ------------------------------------
    def _card_context(self) -> CardContext:
        return CardContext(
            engine=self.engine, stars=self.star_catalog, dso=self.dso_catalog,
            const_names=self.const_names, userdata=self.userdata,
            bortle=lambda: self.sky.bortle,
            horizon=lambda: self.horizon_profile,
            min_alt=lambda: self._plan_settings().min_altitude,
            instrument=lambda: self.settings.value("card/instrument", "pequeno", str),
            setup_shape=self._active_setup_shape,
        )

    def _refresh_cards(self, reselect: bool = False) -> None:
        """Recalcula as fichas abertas (Bortle, horizonte, nomes mudaram)."""
        cards = [self.card] + [getattr(w, "card", None) for w in self._track_windows]
        for card in cards:
            try:
                if card is None or card.selection is None:
                    continue
                if reselect:
                    card.set_selection(card.selection)
                else:
                    card.invalidate()
            except RuntimeError:
                continue            # janela já fechada (objeto Qt destruído)

    def _on_card_action(self, key: str, selection) -> None:
        """Botões da ficha: ações sobre o objeto."""
        if selection is None:
            return
        if key == "center":
            self.sky.selection = selection
            self.sky.goto_object(selection)
        elif key == "follow":
            self.sky.selection = selection
            self.sky.goto_object(selection)
            self.act_follow.setChecked(True)
        elif key == "track":
            self._track_selection(selection)
        elif key == "details" and selection[0] == "body":
            if selection[1] == "Lua":
                self._open_moon_window()
            elif selection[1] != "Sol":
                self._open_planets(selection[1])
        elif key == "details":
            self._open_object_window(selection)
        elif key == "frame":
            self.sky.selection = selection
            self._open_fov_for(selection)
        elif key == "goto_best":
            self._goto_best_tonight(selection)
        elif key == "list":
            self._add_to_list(selection)
        elif key == "observed":
            self._mark_observed(selection)
        elif key == "session":
            self._open_session(selection)
        elif key == "moon":
            self._open_moon_window()
        elif key == "planet":
            self._open_planets(selection[1])
        elif key == "copy":
            self.statusBar().showMessage(self.tr("Copiado: {t}").format(
                t=self.card.copy_text() if self.card.selection == selection
                else self.sky.describe_selection(selection)), 5000)

    def _open_tonight(self) -> None:
        """Planejar ▸ Hoje à noite (T) — v0.15 T11."""
        from ..core.tonight import tonight_summary
        from .tonight_panel import TonightPanel

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            summary = tonight_summary(
                self.engine, self.dso_catalog, self.engine.time.current_datetime(),
                bortle=self.sky.bortle, horizon=self.horizon_profile,
                min_alt=self._plan_settings().min_altitude,
                instrument=self.settings.value("card/instrument", "pequeno", str))
        finally:
            QApplication.restoreOverrideCursor()
        panel = TonightPanel(summary, self.settings.location().name, self)
        panel.setAttribute(Qt.WA_DeleteOnClose, True)
        panel.gotoRequested.connect(self._goto_ident)
        panel.gotoAtTimeRequested.connect(self._goto_ident_at)
        panel.addToListRequested.connect(self._add_ident_to_list)
        panel.planRequested.connect(lambda: self._open_marathon("BEST"))
        self._tonight_panel = panel
        panel.show()

    def _add_ident_to_list(self, kind: str, ident: str) -> None:
        ref = ObjectRef.from_ident(kind, ident, self.star_catalog, self.dso_catalog)
        if ref is not None:
            self._add_to_list(ref.selection)

    def _search_goto(self, selection) -> None:
        """Resultado da busca: constelação vai ao centro com destaque."""
        if selection[0] == "const":
            self.sky.goto_constellation(selection[1])
        else:
            self.sky.goto_object(selection)

    def _open_lists(self) -> None:
        """Objetos ▸ Minhas listas (v0.15 T7)."""
        from .lists_window import ListsWindow

        win = getattr(self, "_lists_window", None)
        try:
            if win is not None and win.isVisible():
                win.refresh_lists()
                win.raise_()
                win.activateWindow()
                return
        except RuntimeError:
            pass
        win = ListsWindow(self._card_context(), self.settings, self)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.gotoRequested.connect(self._goto_selection)
        win.planRequested.connect(lambda name: self._open_marathon(f"LIST:{name}"))
        self._lists_window = win
        win.show()

    def _goto_selection(self, selection) -> None:
        self.sky.selection = selection
        self.sky.selectionChanged.emit(selection)
        self.sky.goto_object(selection)

    def _add_selection_to_list(self) -> None:
        if self.sky.selection is None:
            self.statusBar().showMessage(self.tr("Nenhum objeto selecionado"), 4000)
            return
        self._add_to_list(self.sky.selection)

    def _plan_current_list(self) -> None:
        from ..core.userdata import DEFAULT_LIST

        name = self.settings.value("lists/current", DEFAULT_LIST, str)
        lid = self.userdata.list_id(name)
        if lid is None or not self.userdata.items(lid):
            QMessageBox.information(self, "Carina", self.tr(
                "A lista \"{n}\" está vazia. Acrescente objetos pelo botão "
                "direito, pela ficha (★) ou com Ctrl+B.").format(n=name))
            return
        self._open_marathon(f"LIST:{name}")

    def _goto_best_tonight(self, selection) -> None:
        """Relógio na melhor hora desta noite (janela útil e horizonte)."""
        from ..core.localtime import to_local
        from ..core.visibility import visibility_of

        ref = ObjectRef.resolve(selection, self.star_catalog, self.dso_catalog)
        if ref is None:
            return
        vis = visibility_of(self.engine, ref, self.engine.time.current_datetime(),
                            min_alt=self._plan_settings().min_altitude,
                            horizon=self.horizon_profile)
        if not vis.observable:
            self.sky.show_notice(self.tr("{n} não tem janela útil nesta noite").format(
                n=ref.name))
            return
        self.engine.time.set_datetime(vis.best_utc)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        self.sky.selection = selection
        self.sky.goto_object(selection, animate=False)
        self.sky.show_notice(self.tr("{n}: melhor hora {h}, altitude {a:.0f}°").format(
            n=ref.name, h=to_local(vis.best_utc).strftime("%H:%M"), a=vis.best_alt))

    def _add_to_list(self, selection, list_name: str | None = None) -> None:
        """Acrescenta à "Minha lista" (ou à lista indicada)."""
        from ..core.userdata import DEFAULT_LIST

        ref = ObjectRef.resolve(selection, self.star_catalog, self.dso_catalog)
        if ref is None:
            return
        name = list_name or self.settings.value("lists/current", DEFAULT_LIST, str)
        lid = self.userdata.ensure_list(name)
        radec = ref.ra_dec or (None, None)
        added = self.userdata.add_item(lid, ref.kind, ref.ident, ref.name, *radec)
        msg = (self.tr("{o} acrescentado a \"{l}\"") if added
               else self.tr("{o} já está em \"{l}\""))
        self.statusBar().showMessage(msg.format(o=ref.name, l=name), 5000)
        self._refresh_cards(reselect=True)

    def _instruments(self) -> list[str]:
        """Sugestões de instrumento para o diário: o último usado primeiro."""
        from ..catalogs.equipment import EquipmentStore

        if not hasattr(self, "_equipment"):
            self._equipment = EquipmentStore(user_data_path() / "equipamentos.json")
        names_ = [self.tr("Olho nu"), self.tr("Binóculo 10×50")]
        names_ += [t.name for t in self._equipment.items("telescopes")]
        last = self.settings.value("journal/instrument", "", str)
        if last:
            names_ = [last] + [n for n in names_ if n != last]
        return names_

    def _mark_observed(self, selection, when_utc=None) -> bool:
        """Registra no diário (v0.15 T8). Devolve True se salvou."""
        from .journal_dialog import ObservationDialog

        ref = ObjectRef.resolve(selection, self.star_catalog, self.dso_catalog)
        if ref is None:
            return False
        dlg = ObservationDialog(
            ref.name, when_utc or self.engine.time.current_datetime(),
            self.settings.location().name, self._instruments(), self.sky.bortle,
            parent=self)
        from PySide6.QtWidgets import QDialog

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        values = dlg.values()
        when = values.pop("when_utc")
        self.userdata.add_observation(ref.kind, ref.ident, ref.name, when, **values)
        if values.get("instrument"):
            self.settings.set_value("journal/instrument", values["instrument"])
        self.statusBar().showMessage(
            self.tr("{o} registrado no diário").format(o=ref.name), 5000)
        self._refresh_cards(reselect=True)
        jw = getattr(self, "_journal_window", None)
        try:
            if jw is not None and jw.isVisible():
                jw.reload()
        except RuntimeError:
            pass
        return True

    def _open_journal(self) -> None:
        """Objetos ▸ Diário de observação (v0.15 T8)."""
        from .journal_dialog import JournalWindow

        win = JournalWindow(self.userdata, self._instruments(), self)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.gotoRequested.connect(self._goto_ident)
        self._journal_window = win
        win.show()

    def _goto_ident(self, kind: str, ident: str) -> None:
        ref = ObjectRef.from_ident(kind, ident, self.star_catalog, self.dso_catalog)
        if ref is None:
            self.statusBar().showMessage(
                self.tr("{o} não está mais no catálogo").format(o=ident), 5000)
            return
        self._goto_selection(ref.selection)

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
            "print": self._open_chart_dialog,
            "info": self._open_night_info,
            "tonight": self._open_tonight,
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

    def _open_horizon(self) -> None:
        """Local ▸ Horizonte do quintal: editor do perfil (v0.15 T4)."""
        from .horizon_dialog import HorizonDialog

        ref = ObjectRef.resolve(self.sky.selection, self.star_catalog,
                                self.dso_catalog)
        dialog = HorizonDialog(self.engine, self.star_catalog, self.userdata,
                               self.settings.location().name, ref, self)
        dialog.profileApplied.connect(self._apply_horizon)
        self._horizon_dialog = dialog
        dialog.show()

    def _apply_horizon(self, profile) -> None:
        self.horizon_profile = profile
        self.sky.set_horizon_profile(profile)
        self._refresh_cards()
        name = profile.name if profile is not None else self.tr("plano")
        self.statusBar().showMessage(
            self.tr("Horizonte do quintal: {n}").format(n=name), 6000)

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

        dlg = SearchDialog(self.star_catalog, self.dso_catalog, self,
                           ctx=self._card_context())
        dlg.goto_requested.connect(self._search_goto)
        dlg.addToListRequested.connect(self._add_to_list)
        dlg.exec()

    def _set_names_language(self, code: str) -> None:
        """Idioma dos nomes comuns: vale para mapa, ficha, busca e roteiros."""
        names.set_language(code)
        self.settings.set_value("names/language", code)
        self.sky.update()
        self._refresh_cards(reselect=True)

    def _set_bortle(self, level: int) -> None:
        self.sky.set_bortle(level)
        self._refresh_cards()
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

    def _fill_catalog_menu(self) -> None:
        """Um item marcável por catálogo, mais "todos" e "nenhum".

        Mesma regra do filtro: um objeto aparece se estiver em ALGUM
        catálogo ligado — ao desligar Collinder, os Collinder que também
        são NGC continuam visíveis enquanto o NGC estiver ligado.
        """
        from ..catalogs.dso import ALL_CATALOGS, CATALOG_LABELS

        menu = self._cat_menu
        menu.clear()
        flt = self.sky.dso_filter
        for cat in ALL_CATALOGS:
            act = menu.addAction(self.tr(CATALOG_LABELS.get(cat, cat)))
            act.setCheckable(True)
            act.setChecked(cat in flt.catalogs)
            act.toggled.connect(lambda on, c=cat: self._set_catalog_visible(c, on))
        menu.addSeparator()
        menu.addAction(self.tr("Mostrar todos")).triggered.connect(
            lambda: self._set_all_catalogs(True))
        menu.addAction(self.tr("Ocultar todos")).triggered.connect(
            lambda: self._set_all_catalogs(False))
        menu.addSeparator()
        hint = menu.addAction(self.tr("Um objeto em vários catálogos aparece se algum "
                                      "deles estiver ligado"))
        hint.setEnabled(False)

    def _set_catalog_visible(self, cat: str, on: bool) -> None:
        flt = self.sky.dso_filter.copy()
        cats = set(flt.catalogs)
        cats.add(cat) if on else cats.discard(cat)
        flt.catalogs = cats
        self._apply_dso_filter(flt)
        self.statusBar().showMessage(
            (self.tr("Catálogo {c} exibido") if on else self.tr("Catálogo {c} oculto"))
            .format(c=cat), 4000)

    def _set_all_catalogs(self, on: bool) -> None:
        from ..catalogs.dso import ALL_CATALOGS

        flt = self.sky.dso_filter.copy()
        flt.catalogs = set(ALL_CATALOGS) if on else set()
        self._apply_dso_filter(flt)

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
            build_bright_stars, build_from_list, build_marathon, build_period_plan,
        )

        now = self.engine.time.current_datetime()
        settings.bortle = self.sky.bortle          # pontuação com o céu atual
        if kind.startswith("LIST:"):
            name = kind[5:]
            lid = self.userdata.list_id(name)
            items = self.userdata.items(lid) if lid is not None else []
            plan = build_from_list(
                self.engine, self.dso_catalog, self.star_catalog, items, now,
                self.const_names, settings=settings, horizon=self.horizon_profile,
                title=self.tr("Roteiro: {n}").format(n=name),
            )
        elif kind == "STARS":
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
                self.const_names, settings=settings, horizon=self.horizon_profile,
            )
        plan.location = self.settings.location().name
        return plan

    def _open_marathon(self, kind: str) -> None:
        """Abre uma janela de planejamento (menu Planejar → Visual)."""
        from ..catalogs import skygeometry
        from ..config import package_data_dir
        from .plan_window import PlanWindow
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

        win = PlanWindow(
            plan, self.star_catalog, self._const_lines_cache, self,
            settings=settings, recompute_cb=recompute,
            observed=self.userdata.observed_idents,
        )
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.gotoRequested.connect(self._goto_ident)
        win.gotoAtTimeRequested.connect(self._goto_ident_at)
        win.trackRequested.connect(self._track_ident)
        win.observedRequested.connect(
            lambda k, i, w, pw=win: self._observed_from_plan(pw, k, i, w))
        self._track_windows.append(win)
        win.show()

    def _goto_ident_at(self, kind: str, ident: str, when) -> None:
        """Roteiro ▸ Ir para na hora: relógio no horário da parada."""
        self.engine.time.set_datetime(when)
        self.engine.time.set_speed(0.0)
        self.sky.sync_clock()
        self._goto_ident(kind, ident)

    def _track_ident(self, kind: str, ident: str) -> None:
        ref = ObjectRef.from_ident(kind, ident, self.star_catalog, self.dso_catalog)
        if ref is not None:
            self._track_selection(ref.selection)

    def _observed_from_plan(self, plan_window, kind: str, ident: str, when) -> None:
        ref = ObjectRef.from_ident(kind, ident, self.star_catalog, self.dso_catalog)
        if ref is not None and self._mark_observed(ref.selection, when):
            try:
                plan_window.mark_observed_refresh()
            except RuntimeError:
                pass

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

    def _open_chart_dialog(self) -> None:
        """Arquivo ▸ Gerar carta celeste (v0.16 T3)."""
        from .chart_dialog import ChartDialog

        dlg = ChartDialog(self)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        self._chart_dialog = dlg
        dlg.show()

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
        from .info_popup import InfoPopup

        if selection is None:
            return
        card = ObjectCard(self._card_context())
        card.set_selection(selection)
        card.actionRequested.connect(self._on_card_action)
        popup = InfoPopup(card, self.sky.describe_selection(selection), self)
        popup.destroyed.connect(
            lambda *_: self._track_windows.remove(popup)
            if popup in self._track_windows else None)
        self._track_windows.append(popup)
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
        # a ficha vai sem imagem: esta janela já mostra a imagem grande
        card = ObjectCard(self._card_context(), show_image=False)
        card.set_selection(selection)
        card.actionRequested.connect(self._on_card_action)
        card.buttons["details"].hide()
        win = ObjectWindow(title, card, image_path, dates, alt_mid, alt_max,
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
        dlg = FovDialog(self._equipment, self, settings=self.settings)
        dlg.fovChanged.connect(self.sky.set_fov_shapes)
        dlg.setupChosen.connect(self._set_active_setup)
        active = self.active_setup()
        i = dlg.cb_saved.findText(active.name) if active is not None else -1
        if i >= 0:
            dlg.cb_saved.setCurrentIndex(i)
            dlg.apply_setup(active)
        else:
            dlg.restore_last()
        dlg.exec()

    # -- setup ativo (v0.19) ------------------------------------------------
    def equipment(self):
        from ..catalogs.equipment import EquipmentStore

        if not hasattr(self, "_equipment"):
            self._equipment = EquipmentStore(user_data_path() / "equipamentos.json")
        return self._equipment

    def active_setup(self):
        from ..catalogs.equipment import load_setup

        name = self.settings.value("equipment/active_setup", "", str)
        return load_setup(name, self.userdata) if name else None

    def _set_active_setup(self, name: str) -> None:
        self.settings.set_value("equipment/active_setup", name)
        self._refresh_cards(reselect=True)
        win = getattr(self, "_session_window", None)
        if win is not None:
            try:
                win.refresh_setups(name or None)
            except RuntimeError:          # janela já fechada
                pass

    def _active_setup_shape(self):
        """(nome, campo da câmera) do setup ativo, para a ficha."""
        s = self.active_setup()
        if s is None:
            return None
        shape = s.camera_shape(self.equipment())
        return (s.name, shape) if shape is not None else None

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
            self._apply_location(dlg.location())
            b = dlg.bortle_choice()
            if b is not None:
                self._apply_bortle(b)

    def _apply_location(self, loc) -> None:
        """Muda o local do observador (diálogo, assistente, locais salvos)."""
        self.settings.set_location(loc)
        self.engine.set_location(loc)
        self.sky.location_name = loc.name
        self._slider_night_key = None
        self.sky.update()
        self._refresh_cards()

    def _apply_bortle(self, level: int) -> None:
        level = max(1, min(9, int(level)))
        self._set_bortle(level)
        if level in self._bortle_acts:
            self._bortle_acts[level].setChecked(True)

    # --- locais salvos (v0.16 T6) --------------------------------------------
    def _fill_saved_locations(self) -> None:
        menu = self._saved_menu
        menu.clear()
        names_ = self.userdata.profiles("location")
        for name in names_:
            act = menu.addAction(name)
            act.triggered.connect(lambda _c=False, n=name: self._use_saved_location(n))
        if names_:
            menu.addSeparator()
        menu.addAction(self.tr("Salvar local atual…")).triggered.connect(
            self._save_location)
        if names_:
            menu.addAction(self.tr("Excluir local salvo…")).triggered.connect(
                self._delete_location)

    def _save_location(self) -> None:
        from dataclasses import asdict

        loc = self.settings.location()
        name, ok = QInputDialog.getText(self, self.tr("Salvar local"), self.tr("Nome:"),
                                        text=loc.name.split(",")[0])
        if not ok or not name.strip():
            return
        data = asdict(loc)
        data["bortle"] = int(self.sky.bortle)
        data["horizon"] = self.horizon_profile.name if self.horizon_profile else ""
        self.userdata.save_profile("location", name.strip(), data)
        self.statusBar().showMessage(self.tr("Local \"{n}\" salvo").format(n=name.strip()), 5000)

    def _use_saved_location(self, name: str) -> None:
        from ..config import ObserverLocation

        data = self.userdata.profile("location", name)
        if not data:
            return
        fields = {k: data[k] for k in ("name", "latitude", "longitude", "elevation", "timezone")
                  if k in data}
        self._apply_location(ObserverLocation(**fields))
        if data.get("bortle"):
            self._apply_bortle(data["bortle"])
        horizon = data.get("horizon") or None
        if horizon is None or self.userdata.horizon(horizon) is not None:
            self.userdata.set_active_horizon(horizon)
            self._apply_horizon(self.userdata.active_horizon())
        self.statusBar().showMessage(self.tr("Local: {n}").format(n=name), 5000)

    def _delete_location(self) -> None:
        names_ = self.userdata.profiles("location")
        name, ok = QInputDialog.getItem(self, self.tr("Excluir local"), self.tr("Local:"),
                                        names_, 0, False)
        if ok and name:
            self.userdata.delete_profile("location", name)

    # --- ajuda, novidades e primeiro uso (v0.16 T6) ---------------------------
    def _open_help(self, page: str = "README.md") -> None:
        from .help_viewer import HelpViewer

        viewer = HelpViewer(page, self)
        viewer.setAttribute(Qt.WA_DeleteOnClose, True)
        self._help_viewer = viewer
        viewer.show()

    def set_language(self, code: str) -> None:
        """Idioma do programa: nomes dos objetos já; o resto ao reiniciar."""
        from ..i18n import DEFAULT_LANGUAGE, LANGUAGES, SETTING_KEY

        code = code if code in LANGUAGES else DEFAULT_LANGUAGE
        previous = self.settings.value(SETTING_KEY, DEFAULT_LANGUAGE, str)
        self.settings.set_value(SETTING_KEY, code)
        if code != previous:
            self._set_names_language(LANGUAGES[code][1])
            if hasattr(self, "_names_acts") and LANGUAGES[code][1] in self._names_acts:
                self._names_acts[LANGUAGES[code][1]].setChecked(True)
            self.statusBar().showMessage(self.tr(
                "Idioma: {l}. Diálogos do sistema mudam ao reiniciar o Carina.").format(
                    l=LANGUAGES[code][0]), 8000)

    def show_whats_new_if_needed(self) -> None:
        """Na primeira abertura de uma versão nova, mostra as novidades."""
        last = self.settings.value("ui/last_version", "", str)
        self.settings.set_value("ui/last_version", __version__)
        if last and last != __version__:
            self._open_help("NOVIDADES.md")

    def run_first_run(self) -> bool:
        """Assistente de 3 passos (cidade, céu, instrumento)."""
        from .first_run import FirstRunWizard

        from ..i18n import DEFAULT_LANGUAGE, SETTING_KEY

        wiz = FirstRunWizard(self.settings.location(), int(self.sky.bortle),
                             self.settings.value("card/instrument", "pequeno", str), self,
                             language=self.settings.value(SETTING_KEY, DEFAULT_LANGUAGE, str))
        self._first_run = wiz
        accepted = bool(wiz.exec())
        self.settings.set_value("ui/first_run_done", True)
        self.settings.set_value("ui/last_version", __version__)
        if not accepted:
            return False
        values = wiz.result_values()
        self.set_language(values["language"])
        self._apply_location(values["location"])
        self._apply_bortle(values["bortle"])
        self.settings.set_value("card/instrument", values["instrument"])
        self._refresh_cards()
        if values["horizon"]:
            self._open_horizon()
        if values["tonight"]:
            self._open_tonight()
        return True


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
                "efemérides JPL DE440s e orientação da Lua (NAIF).<br>"
                "Lua: textura LROC e relevo LOLA (NASA SVS CGI Moon Kit), nomes "
                "da IAU/USGS (Gazetteer of Planetary Nomenclature), Lunar 100 de "
                "Charles A. Wood; chuvas de meteoros: IMO.<br>"
                "Planetas: texturas Solar System Scope (CC BY 4.0, a partir de "
                "mosaicos da NASA); luas de Júpiter e Saturno pelas efemérides "
                "de satélites do JPL; Grande Mancha Vermelha: JUPOS.<br>"
                "Textura da Via Láctea: <b>ESO/S. Brunier</b> (CC BY 4.0)."
            ).format(v=__version__),
        )
