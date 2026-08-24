"""Janela principal do AstroPlanetary."""

from __future__ import annotations

from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox

from .. import __version__
from ..catalogs.stars import StarCatalog
from ..config import Settings, package_data_dir, user_data_path
from ..core.engine import SkyEngine
from .location_dialog import LocationDialog
from .skywidget import SkyWidget

# (chave da camada, título do menu, atalho, padrão)
_LAYER_ACTIONS = [
    ("stars", "Estrelas", None, True),
    ("planets", "Planetas, Sol e Lua", "P", True),
    ("const_lines", "Linhas das constelações", "C", True),
    ("const_bounds", "Fronteiras das constelações", "B", False),
    ("grid_altaz", "Grade horizontal (Alt-Az)", "Z", True),
    ("grid_eq", "Grade equatorial", "E", False),
    ("milkyway", "Via Láctea", "M", True),
    ("horizon", "Linha do horizonte", "H", True),
    ("cardinals", "Pontos cardeais", "Q", True),
    ("star_names", "Nomes das estrelas", "N", True),
    ("planet_names", "Nomes dos planetas", None, True),
    ("atmosphere", "Atmosfera", "A", True),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Carina {__version__}")
        self.resize(1280, 800)

        self.settings = Settings()
        data_dir = package_data_dir()

        self.engine = SkyEngine(user_data_path())
        loc = self.settings.location()
        self.engine.set_location(loc)

        self.star_catalog = StarCatalog(data_dir)
        self.sky = SkyWidget(self.engine, self.star_catalog, data_dir, self)
        self.sky.location_name = loc.name
        self.setCentralWidget(self.sky)
        self.sky.statusUpdated.connect(self.statusBar().showMessage)

        self._build_menus()
        self._restore_layers()

    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        bar = self.menuBar()

        m_file = bar.addMenu(self.tr("&Arquivo"))
        act_quit = QAction(self.tr("Sair"), self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

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
        self.act_proper = QAction(self.tr("Rotular por nome próprio"), self)
        self.act_bayer = QAction(self.tr("Rotular por designação de Bayer (genitivo)"), self)
        for act, mode in ((self.act_proper, "proper"), (self.act_bayer, "bayer")):
            act.setCheckable(True)
            act.setActionGroup(name_group)
            act.triggered.connect(lambda _=False, m=mode: self.sky.set_name_mode(m))
            m_view.addAction(act)
        self.act_proper.setChecked(True)

        m_obs = bar.addMenu(self.tr("&Observador"))
        act_loc = QAction(self.tr("Localização…"), self)
        act_loc.setShortcut("L")
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
                "Planetário desktop em Python — PySide6 + OpenGL + Skyfield.<br><br>"
                "Dados: HYG v4.1 (CC BY-SA), d3-celestial (BSD-3), "
                "efemérides JPL DE440s."
            ).format(v=__version__),
        )
