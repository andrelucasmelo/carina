"""Janela dos planetas (v0.18 T4): cada planeta, agora e no ano.

À esquerda, os sete planetas com o estado de cada um. No centro, o disco
desenhado como no telescópio — fase de Mercúrio e Vênus, Marte com o
meridiano central, Júpiter com as faixas e a Grande Mancha Vermelha na
longitude atual, Saturno com os anéis na inclinação do dia — e, embaixo,
uma tira própria de cada caso: as luas de Júpiter e Saturno vistas da
Terra, as fases de Mercúrio e Vênus ao longo da aparição, o disco de Marte
crescendo até a oposição. À direita: o estado agora, a melhor época (com a
temporada de visibilidade) e os eventos das luas na noite.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QPushButton, QSplitter, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..core import planets as P
from ..core import satellites as S
from ..core.formats import num
from ..core.localtime import to_local
from ..render.moon_cpu import MoonView
from ..render.planet_cpu import render_planet, ring_profile
from .moon_window import ORIENTATIONS, _outlined

UTC = dt.timezone.utc


# --------------------------------------------------------------------------
# recursos (texturas e perfil dos anéis), lidos uma vez
_TEXTURES: dict = {}


def texture(name: str):
    if name not in _TEXTURES:
        from ..render.moontex import qimage_rgb

        path = S.data_dir() / P.TEXTURE[name]
        _TEXTURES[name] = qimage_rgb(path) if path.exists() else None
    return _TEXTURES[name]


def rings_for(name: str):
    if name != "Saturno":
        return None
    if "rings" not in _TEXTURES:
        path = S.data_dir() / "saturn_ring.png"
        _TEXTURES["rings"] = ring_profile(path) if path.exists() else None
    prof = _TEXTURES["rings"]
    if prof is None:
        return None
    req = P.radii_km("Saturno")[0]
    ri, ro = S.ring_radii_km()
    return {"inner": ri / req, "outer": ro / req, "profile": prof}


def grs_override(settings):
    """(longitude, data) informada pelo usuário, ou None (usa a tabela)."""
    if settings is None:
        return None
    raw = settings.value("planets/grs_override", "", str)
    try:
        lon, date = raw.split(";")
        return float(lon), dt.date.fromisoformat(date)
    except (ValueError, AttributeError):
        return None


def render_state(state, view: MoonView, settings=None, background=(6, 8, 14)) -> np.ndarray:
    """Disco do planeta na vista, com a textura posicionada."""
    name = state.name
    req, rpol = P.radii_km(name)
    frame, off = state.frame, 0.0
    if name == "Júpiter":
        frame = P.body_frame("Júpiter", state.jd_tdb, "II")
        lam = S.grs_longitude(state.when_utc, grs_override(settings))
        off = S.grs_texture_u() - 0.5 + lam / 360.0
    return render_planet(view, frame, state.u_icrs, state.sun_dir, texture(name),
                         rpol / req, off, rings_for(name), background=background,
                         light_exponent=0.5 if name in P.INNER else 1.0)


def to_qimage(rgb: np.ndarray, dpr: float = 1.0) -> QImage:
    h, w, _ = rgb.shape
    img = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
    img.setDevicePixelRatio(dpr)
    return img


_BEST_CACHE: dict = {}        # (aba, planeta, data local) -> resultados


# --------------------------------------------------------------------------
class PlanetCanvas(QWidget):
    """O disco grande, com as luas e sombras que caem no campo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 300)
        self.state = None
        self.moons: list = []
        self.settings = None
        self.rotation = 0.0
        self.mirror = False
        self.zoom = 1.0
        self._image = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._rerender)

    def set_state(self, state, moons) -> None:
        self.state, self.moons = state, moons
        self.invalidate()

    def invalidate(self) -> None:
        self._timer.start(0)

    def _view(self) -> MoonView:
        dpr = self.devicePixelRatioF()
        base = 1.0 / 2.45 if self.state is not None and self.state.name == "Saturno" else 0.92
        return MoonView(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)),
                        zoom=base * self.zoom, rotation=self.rotation, mirror=self.mirror)

    def _rerender(self) -> None:
        if self.state is None:
            return
        view = self._view()
        self._image = to_qimage(render_state(self.state, view, self.settings),
                                self.devicePixelRatioF())
        self.update()

    def resizeEvent(self, _e) -> None:
        self.invalidate()

    def wheelEvent(self, e) -> None:
        self.zoom = float(min(4.0, max(0.3, self.zoom * (1.2 if e.angleDelta().y() > 0 else 1 / 1.2))))
        self.invalidate()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(6, 8, 14))
        if self._image is not None:
            p.drawImage(0, 0, self._image)
        if self.state is None:
            p.end()
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        view = self._view()
        dpr = self.devicePixelRatioF()
        font = QFont("Segoe UI", 9)
        fm = QFontMetrics(font)
        px_r = view.scale / dpr
        for m in self.moons:
            # sombra sobre o disco: ponto preto do tamanho aproximado da lua
            if m.shadow is not None:
                sx, sy = view.to_screen(m.shadow[0], m.shadow[1])
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 230))
                rr = max(2.0, px_r * 0.035)
                p.drawEllipse(QPointF(sx / dpr, sy / dpr), rr, rr)
            if m.status in ("ocultada", "eclipsada"):
                continue
            x, y = view.to_screen(m.x, m.y)
            x, y = x / dpr, y / dpr
            if not (-20 <= x <= self.width() + 20 and -20 <= y <= self.height() + 20):
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(235, 230, 215) if m.status == "visivel" else QColor(255, 250, 235))
            rr = max(2.2, px_r * 0.036)
            p.drawEllipse(QPointF(x, y), rr, rr)
            _outlined(p, x + rr + 3, y + fm.ascent() / 2 - 1, m.name, font, QColor(200, 220, 255))
        # norte e leste da vista
        self._compass(p, view)
        p.end()

    def _compass(self, p: QPainter, view: MoonView) -> None:
        dpr = self.devicePixelRatioF()
        cx, cy = self.width() - 40, self.height() - 40
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        for label, (a, b) in (("N", (0.0, 1.0)), ("L", (1.0, 0.0))):
            x0, y0 = view.to_screen(0.0, 0.0)
            x1, y1 = view.to_screen(a * 0.1, b * 0.1)
            dx, dy = (x1 - x0) / dpr, (y1 - y0) / dpr
            n = math.hypot(dx, dy) or 1.0
            ex, ey = cx + dx / n * 22, cy + dy / n * 22
            p.setPen(QPen(QColor(150, 160, 180), 1.2))
            p.drawLine(QPointF(cx, cy), QPointF(ex, ey))
            p.drawText(QPointF(ex + dx / n * 6 - 4, ey + dy / n * 6 + 4), label)


class SystemStrip(QWidget):
    """Tira inferior: luas (Júpiter, Saturno), fases (Mercúrio, Vênus) ou
    o tamanho do disco ao longo dos meses (Marte, Urano, Netuno)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.mode = "none"
        self.state = None
        self.moons: list = []
        self.series: list = []           # [(data, QImage, diâmetro, iluminação)]
        self.rotation = 0.0
        self.mirror = False
        self.settings = None
        self._planet_img = None

    def set_moons(self, state, moons) -> None:
        self.mode, self.state, self.moons = "moons", state, moons
        # escala: cabe a lua mais afastada (Calisto ~26 RJ; Jápeto ~60 RS)
        self._planet_img = None
        self.update()

    def set_series(self, series, title: str) -> None:
        self.mode, self.series, self.title = "series", series, title
        self.update()

    def clear(self) -> None:
        self.mode = "none"
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 12, 20))
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.mode == "moons" and self.state is not None:
            self._paint_moons(p)
        elif self.mode == "series":
            self._paint_series(p)
        p.end()

    def _paint_moons(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        dpr = self.devicePixelRatioF()
        view = MoonView(int(w * dpr), int(h * dpr), rotation=self.rotation, mirror=self.mirror)
        # escala que cabe todas as luas nas DUAS direções: o plano das órbitas
        # aparece inclinado conforme a posição do planeta no céu
        view.zoom = 1.0 / (min(view.width, view.height) * 0.46)       # 1 px por raio
        cx, cy = view.width / 2.0, view.height / 2.0
        pts = [view.to_screen(m.x, m.y) for m in self.moons if m.status != "ocultada"]
        ext_x = max([abs(x - cx) for x, _ in pts] + [3.0])
        ext_y = max([abs(y - cy) for _, y in pts] + [1.5])
        scale = min((view.width / 2.0 - 30 * dpr) / ext_x,
                    (view.height / 2.0 - 28 * dpr) / ext_y)
        view.zoom = max(scale, 1.0) / (min(view.width, view.height) * 0.46)
        if self._planet_img is None or self._planet_img.width() != view.width:
            self._planet_img = to_qimage(render_state(self.state, view, self.settings), dpr)
        p.drawImage(0, 0, self._planet_img)
        font = QFont("Segoe UI", 8)
        fm = QFontMetrics(font)
        p.setFont(font)
        taken = []
        for m in sorted(self.moons, key=lambda m: m.magnitude):
            x, y = view.to_screen(m.x, m.y)
            x, y = x / dpr, y / dpr
            hidden = m.status in ("ocultada", "eclipsada")
            col = QColor(110, 110, 120) if hidden else QColor(240, 236, 220)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            rr = max(1.6, 4.2 - 0.35 * (m.magnitude - 5))
            if not hidden:
                p.drawEllipse(QPointF(x, y), rr, rr)
            label = m.name + ("" if m.status == "visivel" else f" ({m.status_pt})")
            tw = fm.horizontalAdvance(label)
            ly = y + 16
            while any(abs(ly - t[1]) < fm.height() and abs(x - t[0]) < (tw + t[2]) / 2 for t in taken):
                ly += fm.height()
            taken.append((x, ly, tw))
            _outlined(p, x - tw / 2, ly, label, font, QColor(170, 200, 255) if not hidden
                      else QColor(130, 130, 140))
        p.setPen(QColor(120, 130, 150))
        p.drawText(QRectF(6, 4, w - 12, 16), Qt.AlignLeft,
                   "Luas como vistas da Terra (mesma orientação do disco acima)")

    def _paint_series(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        n = len(self.series)
        if not n:
            return
        p.setPen(QColor(120, 130, 150))
        p.drawText(QRectF(6, 4, w - 12, 16), Qt.AlignLeft, self.title)
        cell = w / n
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        dmax = max(d for _, _, d, _ in self.series) or 1.0
        box = max(10.0, min(cell - 4, h - 64))
        p.setCompositionMode(QPainter.CompositionMode_Plus)   # fundo preto some
        for i, (date, img, diam, illum) in enumerate(self.series):
            cx = cell * (i + 0.5)
            size = box * diam / dmax
            p.drawImage(QRectF(cx - size / 2, 24 + (box - size) / 2, size, size), img)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        for i, (date, img, diam, illum) in enumerate(self.series):
            cx = cell * (i + 0.5)
            p.setPen(QColor(200, 205, 215))
            p.drawText(QRectF(cx - cell / 2, h - 34, cell, 14), Qt.AlignCenter, f"{date:%d/%m}")
            p.setPen(QColor(140, 150, 165))
            p.drawText(QRectF(cx - cell / 2, h - 20, cell, 14), Qt.AlignCenter,
                       f"{illum * 100:.0f}%" if cell < 70 else f"{num(diam, 0)}″ · {illum * 100:.0f}%")


class SeasonChart(QWidget):
    """Altura máxima no céu escuro ao longo do ano, com os eventos."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.dates, self.alts, self.marks = [], None, []

    def set_data(self, dates, alts, marks) -> None:
        self.dates, self.alts, self.marks = dates, alts, marks
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(14, 18, 28))
        if self.alts is None or not len(self.dates):
            p.end()
            return
        left, right, top, bottom = 34, 8, 10, 22
        w = self.width() - left - right
        h = self.height() - top - bottom
        n = len(self.dates)

        def xy(i, a):
            return QPointF(left + w * i / max(n - 1, 1),
                           top + h * (1 - max(0.0, min(90.0, a)) / 90.0))

        p.setFont(QFont("Segoe UI", 8))
        for a in (0, 30, 60):
            y = xy(0, a).y()
            p.setPen(QPen(QColor(70, 80, 100), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.setPen(QColor(140, 150, 165))
            p.drawText(QRectF(0, y - 8, left - 4, 16), Qt.AlignRight | Qt.AlignVCenter, f"{a}°")
        # faixa boa (> 30°)
        for i in range(n - 1):
            a = float(self.alts[i])
            if a <= 0:
                continue
            col = QColor(90, 170, 110, 170) if a >= 30 else QColor(200, 170, 80, 140)
            r0, r1 = xy(i, a), xy(i + 1, 0)
            p.fillRect(QRectF(r0.x(), r0.y(), r1.x() - r0.x() + 0.6, r1.y() - r0.y()), col)
        p.setPen(QColor(150, 160, 180))
        last_month = None
        for i, d in enumerate(self.dates):
            if d.month != last_month and d.day <= 3:
                x = xy(i, 0).x()
                p.drawText(QRectF(x - 12, top + h + 3, 24, 14), Qt.AlignCenter,
                           ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
                            "out", "nov", "dez"][d.month - 1])
                last_month = d.month
        d0 = self.dates[0]
        span = (self.dates[-1] - d0).days or 1
        for when, label in self.marks:
            x = left + w * (when - d0).days / span
            if left <= x <= left + w:
                p.setPen(QPen(QColor(255, 140, 90), 1.4))
                p.drawLine(QPointF(x, top), QPointF(x, top + h))
                _outlined(p, x + 3, top + 12, label, QFont("Segoe UI", 8), QColor(255, 170, 120))
        p.end()


# --------------------------------------------------------------------------
class PlanetWindow(QMainWindow):
    """Sistema Solar ▸ Planetas."""

    gotoPlanet = Signal(str, object)          # nome, datetime UTC
    chartRequested = Signal(str, object)      # carta de busca (Urano, Netuno…)

    def __init__(self, engine, when_utc: dt.datetime, parent=None, settings=None,
                 constellation_fn=None, planet: str = "Júpiter") -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Planetas"))
        self.engine = engine
        self.when = when_utc
        self.settings = settings
        self.constellation_fn = constellation_fn
        self.name = planet
        self._cache: dict = {}

        self.list = QListWidget()
        self.list.setMaximumWidth(320)
        self.list.setMinimumWidth(240)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._planet_changed)

        bar = QHBoxLayout()
        self.lbl_when = QLabel()
        self.lbl_when.setMinimumWidth(130)
        bar.addWidget(self.lbl_when)
        for text, hours in (("◀ 1 d", -24), ("◀ 1 h", -1), ("1 h ▶", 1), ("1 d ▶", 24)):
            b = QPushButton(text)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, hh=hours: self.step(hh))
            bar.addWidget(b)
        now = QPushButton(self.tr("Agora"))
        now.clicked.connect(self.to_now)
        bar.addWidget(now)
        bar.addSpacing(10)
        self.cmb_orient = QComboBox()
        for key, label in ORIENTATIONS:
            self.cmb_orient.addItem(self.tr(label), key)
        # norte para cima: "como no céu" gira o disco conforme a altura, o que
        # confunde quando o planeta está baixo ou abaixo do horizonte
        self.cmb_orient.setCurrentIndex(1)
        self.cmb_orient.currentIndexChanged.connect(self._apply_orientation)
        bar.addWidget(self.cmb_orient)
        bar.addStretch(1)
        go = QPushButton(self.tr("Mostrar no céu"))
        go.clicked.connect(lambda: self.gotoPlanet.emit(self.name, self.when))
        bar.addWidget(go)
        chart = QPushButton(self.tr("Carta de busca…"))
        chart.setToolTip(self.tr("Carta de 8° em torno do planeta, para achá-lo entre as "
                                 "estrelas (útil para Urano e Netuno)"))
        chart.clicked.connect(lambda: self.chartRequested.emit(self.name, self.when))
        bar.addWidget(chart)

        self.canvas = PlanetCanvas()
        self.canvas.settings = settings
        self.strip = SystemStrip()
        self.strip.settings = settings
        center = QSplitter(Qt.Vertical)
        center.addWidget(self.canvas)
        center.addWidget(self.strip)
        center.setStretchFactor(0, 3)
        center.setStretchFactor(1, 1)

        self.info = QTextBrowser()
        self.best = QTextBrowser()
        self.season = SeasonChart()
        best_box = QWidget()
        bl = QVBoxLayout(best_box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(QLabel(self.tr("Altura máxima no céu escuro, nos próximos 13 meses")))
        bl.addWidget(self.season)
        bl.addWidget(self.best, 1)
        self.events = QTextBrowser()
        self.grs_box = QWidget()
        gl = QHBoxLayout(self.grs_box)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(QLabel(self.tr("Longitude da Mancha Vermelha (Sistema II):")))
        self.spin_grs = QDoubleSpinBox()
        self.spin_grs.setRange(0.0, 359.9)
        self.spin_grs.setDecimals(1)
        self.spin_grs.setSuffix("°")
        gl.addWidget(self.spin_grs)
        btn_grs = QPushButton(self.tr("Usar este valor"))
        btn_grs.clicked.connect(self._save_grs)
        gl.addWidget(btn_grs)
        btn_grs_reset = QPushButton(self.tr("Tabela JUPOS"))
        btn_grs_reset.clicked.connect(self._reset_grs)
        gl.addWidget(btn_grs_reset)
        ev_box = QWidget()
        el = QVBoxLayout(ev_box)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(self.events, 1)
        el.addWidget(self.grs_box)
        self.about = QTextBrowser()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.info, self.tr("Agora"))
        self.tabs.addTab(best_box, self.tr("Melhor época"))
        self.tabs.addTab(ev_box, self.tr("Luas e eventos"))
        self.tabs.addTab(self.about, self.tr("Sobre"))
        self._dirty_tabs = set()
        self.tabs.currentChanged.connect(lambda _i: self._fill_current_tab())

        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(center)
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        split.setSizes([250, 700, 450])
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(bar)
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self.resize(1400, 820)
        self._fill_list()
        self.list.setCurrentRow(P.PLANETS.index(planet) if planet in P.PLANETS else 3)

    # -- tempo e seleção ------------------------------------------------------
    def step(self, hours: float) -> None:
        self.when = self.when + dt.timedelta(hours=hours)
        self.refresh()

    def to_now(self) -> None:
        self.when = dt.datetime.now(UTC)
        self.refresh()

    def set_time(self, when_utc: dt.datetime) -> None:
        self.when = when_utc
        self.refresh()

    def select(self, name: str) -> None:
        if name in P.PLANETS:
            self.list.setCurrentRow(P.PLANETS.index(name))

    def _planet_changed(self, row: int) -> None:
        if 0 <= row < len(P.PLANETS):
            self.name = P.PLANETS[row]
            self.refresh(full=True)

    def _fill_list(self) -> None:
        self.list.clear()
        for name in P.PLANETS:
            st = P.planet_state(self.engine, name, self.when)
            it = QListWidgetItem(f"{name}\nmag {num(st.magnitude)} · {st.visibility}")
            if st.elongation < 12:
                it.setForeground(QColor(130, 130, 140))
            self.list.addItem(it)

    def refresh(self, full: bool = False) -> None:
        self.lbl_when.setText(f"{to_local(self.when):%d/%m/%Y %H:%M}")
        self.state = P.planet_state(self.engine, self.name, self.when, self.constellation_fn)
        self.moons = S.system_view(self.engine, self.state) if S.available(self.name) else []
        self._apply_orientation(update=False)
        self.canvas.set_state(self.state, self.moons)
        self._fill_strip()
        self._fill_info()
        # abas pesadas só quando visíveis (melhor época, eventos da noite)
        self._dirty_tabs = {1, 2}
        self._fill_current_tab()
        self.about.setHtml(f"<h3>{self.name}</h3><p>{P.DESCRIPTION[self.name]}</p>"
                           "<p style='color:#9aa'>Texturas: Solar System Scope (CC BY 4.0), "
                           "a partir de mosaicos da NASA. Luas: efemérides de satélites do "
                           "JPL (jup365, sat441).</p>")
        row = P.PLANETS.index(self.name)
        st = self.state
        item = self.list.item(row)
        if item is not None:
            item.setText(f"{self.name}\nmag {num(st.magnitude)} · {st.visibility}")

    def _fill_current_tab(self) -> None:
        idx = self.tabs.currentIndex()
        if idx not in self._dirty_tabs or not hasattr(self, "state"):
            return
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if idx == 1:
                self._fill_best()
            elif idx == 2:
                self._fill_events()
        finally:
            QApplication.restoreOverrideCursor()
        self._dirty_tabs.discard(idx)

    def _apply_orientation(self, *_a, update: bool = True) -> None:
        key = self.cmb_orient.currentData()
        mirror = key == "mirror"
        if key == "sky" and getattr(self, "state", None) is not None:
            t = self.engine.ts.from_datetime(self.when)
            zen = np.asarray(self.engine.horizontal_matrix(t)[2], np.float64)
            rot = -P._pa(zen, self.state.u_icrs)
        elif key == "inverted":
            rot = 180.0
        else:
            rot = 0.0
        for w in (self.canvas, self.strip):
            w.rotation, w.mirror = rot, mirror
        self.strip._planet_img = None
        if update:
            self.canvas.invalidate()
            self.strip.update()

    # -- painéis ----------------------------------------------------------------
    def _fill_strip(self) -> None:
        name = self.name
        if name in ("Júpiter", "Saturno") and self.moons:
            self.strip.set_moons(self.state, self.moons)
            return
        key = (name, self.when.date())
        if self._cache.get("strip_for") != key:
            if name in P.INNER:
                dates = [self.when + dt.timedelta(days=12 * k) for k in range(10)]
                title = "Fases nos próximos meses (tamanho em escala)"
            else:
                dates = [self.when + dt.timedelta(days=30 * k) for k in range(10)]
                title = "O disco nos próximos meses (tamanho em escala)"
            states = [P.planet_state(self.engine, name, d) for d in dates]
            series = []
            for d, s in zip(dates, states):
                # cada disco desenhado em 96 px e reduzido na tira, em escala
                img = render_state(s, MoonView(96, 96, zoom=1.0 / 0.92 * 0.98), self.settings,
                                   background=(0, 0, 0))
                series.append((to_local(d).date(), to_qimage(img), s.diameter, s.illumination))
            self._cache["strip_for"] = key
            self._cache["strip"] = (series, title)
        self.strip.set_series(*self._cache["strip"])

    def _fill_info(self) -> None:
        from ..core.formats import dec_dms, ra_hms
        from ..core.visibility import Target, compute_visibility

        st = self.state
        rows = []
        vis = compute_visibility(self.engine, Target(body=self.name), self.when, min_alt=15.0)

        def hm(t):
            return f"{to_local(t):%H:%M}" if t else "—"

        rows += [
            ("Constelação", st.constellation or "—"),
            ("AR · Dec (J2000)", f"{ra_hms(math.radians(st.ra))} · {dec_dms(math.radians(st.dec))}"),
            ("Altura · azimute", f"{num(st.alt)}° · {num(st.az, 0)}°" +
             (" (abaixo do horizonte)" if st.alt < 0 else "")),
            ("Nasce · culmina · se põe",
             f"{hm(vis.rise_utc)} · {hm(vis.transit_utc)} ({num(vis.transit_alt, 0)}°) · {hm(vis.set_utc)}"),
            ("Quando ver", st.visibility),
            ("Magnitude", num(st.magnitude)),
            ("Diâmetro aparente", f"{num(st.diameter)}″"),
            ("Distância", f"{num(st.distance_au, 3)} UA · luz leva {num(st.light_minutes, 1)} min"),
            ("Elongação", f"{num(st.elongation)}° {'a leste' if st.evening else 'a oeste'} do Sol"),
            ("Movimento", "retrógrado (andando para oeste entre as estrelas)" if st.retrograde
             else "direto"),
        ]
        if self.name in ("Mercúrio", "Vênus", "Marte"):
            rows.append(("Fase", f"{st.illumination * 100:.0f}% iluminado — {st.phase_name}"))
        if self.name == "Marte":
            rows.append(("Meridiano central", f"{num(st.cm)}° (latitude do centro {num(st.sub_obs_lat)}°)"))
        if self.name == "Júpiter":
            lam = S.grs_longitude(self.when, grs_override(self.settings))
            rows.append(("Meridiano central", f"Sistema I/III {num(st.cm)}° · Sistema II {num(st.cm2)}°"))
            dlam = (lam - st.cm2 + 540) % 360 - 180
            where = ("no centro do disco" if abs(dlam) < 12 else
                     f"a {num(abs(dlam), 0)}° do centro" + (" — visível" if abs(dlam) < 80 else
                                                           " — no lado oculto"))
            rows.append(("Mancha Vermelha", f"longitude {num(lam)}° (Sistema II), {where}"))
        if self.name == "Saturno" and st.ring_tilt is not None:
            face = "norte" if st.ring_tilt > 0 else "sul"
            rows.append(("Anéis", f"inclinação {num(st.ring_tilt)}° (face {face} à mostra); "
                                  f"Sol a {num(st.ring_tilt_sun)}°"))
            cross = self._cache.get("ring_cross")
            if cross is None:
                cross = S.next_ring_crossing(self.engine, self.when, years=20) or False
                self._cache["ring_cross"] = cross
            if cross:
                rows.append(("Anéis de perfil", f"próxima travessia do plano em {to_local(cross):%m/%Y}"))
        html = ["<table cellspacing=4>"]
        for k, v in rows:
            html.append(f"<tr><td style='color:#9aa'>{k}</td><td>{v}</td></tr>")
        html.append("</table>")
        self.info.setHtml("".join(html))

    def _fill_best(self) -> None:
        name = self.name
        start = self.when
        key = ("best", name, to_local(start).date())
        if key not in _BEST_CACHE:
            dates, alts = P.visibility_season(self.engine, name, start, days=400, step_days=3)
            years = {"Mercúrio": 1.2, "Vênus": 2.0, "Urano": 1.5, "Netuno": 1.5}.get(name, 3.0)
            aps = P.apparitions(self.engine, name, start, years)
            text = P.best_epoch_text(self.engine, name, start, aps)
            _BEST_CACHE[key] = (dates, alts, aps, text)
        dates, alts, aps, text = _BEST_CACHE[key]
        marks = []
        for a in aps:
            if a.kind in ("oposicao", "elong_leste", "elong_oeste"):
                lbl = {"oposicao": "oposição", "elong_leste": "elong. L",
                       "elong_oeste": "elong. O"}[a.kind]
                marks.append((to_local(a.when_utc).date(), lbl))
        self.season.set_data(dates, alts, marks)
        period = P.best_period(dates, alts, 30.0)
        html = [f"<p>{text}</p>"]
        if period:
            html.append(f"<p><b>Acima de 30° no céu escuro:</b> de {period[0]:%d/%m/%Y} a "
                        f"{period[1]:%d/%m/%Y}.</p>")
        else:
            html.append("<p>Não passa de 30° no céu escuro nos próximos 13 meses neste local.</p>")
        html.append("<table cellspacing=4><tr style='color:#9aa'><td>Data</td><td>Evento</td>"
                    "<td>Diâm.</td><td>Mag.</td><td></td></tr>")
        for a in aps:
            html.append(f"<tr><td>{to_local(a.when_utc):%d/%m/%Y}</td><td>{a.title}</td>"
                        f"<td>{num(a.diameter)}″</td><td>{num(a.magnitude)}</td>"
                        f"<td style='color:#9aa'>{a.note}</td></tr>")
        html.append("</table>")
        self.best.setHtml("".join(html))
        self._cache["best_for"] = (name, self.when.date())

    def _fill_events(self) -> None:
        self.grs_box.setVisible(self.name == "Júpiter")
        if self.name == "Júpiter":
            ov = grs_override(self.settings)
            self.spin_grs.blockSignals(True)
            self.spin_grs.setValue(S.grs_longitude(self.when, ov))
            self.spin_grs.blockSignals(False)
        if self.name not in ("Júpiter", "Saturno"):
            self.events.setHtml("<p style='color:#9aa'>Sem luas brilhantes para acompanhar.</p>"
                                + ("<p>Marte tem duas luas minúsculas (Fobos e Deimos), "
                                   "fora do alcance de telescópios amadores comuns.</p>"
                                   if self.name == "Marte" else ""))
            return
        if not self.moons:
            self.events.setHtml("<p>As posições das luas cobrem de 2000 a 2060.</p>")
            return
        html = ["<h4>Agora</h4><table cellspacing=3>"]
        for m in sorted(self.moons, key=lambda m: m.x):
            side = "leste" if m.x > 0 else "oeste"
            html.append(f"<tr><td><b>{m.name}</b></td><td>{num(abs(m.x), 1)} raios a {side}</td>"
                        f"<td>mag {num(m.magnitude)}</td><td style='color:#9aa'>{m.status_pt}</td></tr>")
        html.append("</table>")
        key = (self.name, to_local(self.when).date(), grs_override(self.settings))
        if self._cache.get("ev_for") != key:
            from ..core.twilight import night_info

            info = night_info(self.engine, self.when)
            a = info.sunset or self.when
            b = info.sunrise or (a + dt.timedelta(hours=12))
            evs = S.moon_events(self.engine, self.name, a, b, step_minutes=1)
            grs = []
            if self.name == "Júpiter":
                lam = S.grs_longitude(self.when, grs_override(self.settings))
                grs = S.grs_transits(self.engine, a, b, lam)
            self._cache["ev_for"] = key
            self._cache["ev"] = (evs, grs)
        evs, grs = self._cache["ev"]
        html.append("<h4>Nesta noite (do pôr ao nascer do Sol)</h4>")
        if not evs and not grs:
            html.append("<p>Nenhum trânsito, sombra, ocultação ou eclipse.</p>")
        else:
            items = [(e.when_utc, e.text) for e in evs]
            items += [(t, "Mancha Vermelha no meridiano central") for t in grs]
            html.append("<ul>")
            for t, text in sorted(items):
                st = P.planet_state(self.engine, self.name, t)
                up = "" if st.alt > 5 else " <span style='color:#d97'>(planeta abaixo do horizonte)</span>"
                html.append(f"<li><b>{to_local(t):%H:%M}</b> — {text}{up}</li>")
            html.append("</ul>")
        self.events.setHtml("".join(html))

    def _save_grs(self) -> None:
        if self.settings is not None:
            self.settings.set_value("planets/grs_override",
                                    f"{self.spin_grs.value():.1f};{to_local(self.when).date().isoformat()}")
        self._cache.pop("ev_for", None)
        self.refresh()

    def _reset_grs(self) -> None:
        if self.settings is not None:
            self.settings.set_value("planets/grs_override", "")
        self._cache.pop("ev_for", None)
        self.refresh()
