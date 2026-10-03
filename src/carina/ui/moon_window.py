"""Janela da Lua (v0.17 T5): o globo lunar em detalhe.

Mostra a Lua como ela está no instante escolhido — fase, libração e
terminador reais — com zoom, arraste, orientação conforme o instrumento e
os nomes das formações. Ao lado: os números do dia (fase, colongitude,
libração), a lista do que está **no terminador** (relevo realçado) e a
ficha da formação clicada, com as **próximas noites boas** para ela.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QPushButton,
                               QSplitter, QTabWidget, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import moon as moonlib
from ..core.formats import num
from ..core.localtime import to_local
from ..render.moon_cpu import MoonView, render

ORIENTATIONS = [
    ("sky", "Como no céu agora (zênite para cima)"),
    ("north", "Norte celeste para cima"),
    ("inverted", "Telescópio sem diagonal (imagem invertida)"),
    ("mirror", "Refrator ou SCT com diagonal (espelhada)"),
]


def _outlined(painter: QPainter, x: float, y: float, text: str, font: QFont,
              ink: QColor, halo: QColor = QColor(0, 0, 0, 210)) -> None:
    path = QPainterPath()
    path.addText(QPointF(x, y), font, text)
    painter.setPen(QPen(halo, 3.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.NoPen)
    painter.setBrush(ink)
    painter.drawPath(path)


def label_for(f) -> str:
    """Nome exibido: mares, lagos e baías em português quando os nomes
    estão em português (como no céu); as demais formações pelo nome IAU."""
    from ..catalogs import names

    if f.pt and f.type in ("mare", "lacus", "sinus", "palus") and names.language() == "pt":
        return f.pt
    return f.name


class MoonCanvas(QWidget):
    """Área de desenho: imagem calculada na CPU + rótulos por cima."""

    featureClicked = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.view = MoonView(600, 600)
        self.geom: moonlib.MoonGeometry | None = None
        self.arrays = None
        self.show_names = True
        self.selected: moonlib.MoonFeature | None = None
        self._image: QImage | None = None
        self._dirty = True
        self._drag = None
        self._labels: list = []          # (feição, x, y, raio_px)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._rerender)

    # -- estado -----------------------------------------------------------
    def set_geometry(self, geom) -> None:
        self.geom = geom
        self.invalidate()

    def invalidate(self) -> None:
        self._dirty = True
        self._timer.start(0)

    def _basis(self):
        return moonlib.view_basis(self.geom)

    def _rerender(self) -> None:
        if self.geom is None:
            return
        if self.arrays is None:
            from ..render import moontex

            self.arrays = moontex.moon_arrays(1)
            if self.arrays is None:
                return
        dpr = self.devicePixelRatioF()
        w, h = max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr))
        self.view.width, self.view.height = w, h
        e_t, n_t, wv, v2b = self._basis()
        rgb = render(self.view, v2b, self.geom.sun_body, self.geom.obs_body,
                     *self.arrays, illumination=self.geom.illumination)
        img = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        img.setDevicePixelRatio(dpr)
        self._image = img
        self._dirty = False
        self._compute_labels()
        self.update()

    def _compute_labels(self) -> None:
        self._labels = []
        feats = moonlib.features()
        if not feats or self.geom is None:
            return
        e_t, n_t, w, _ = self._basis()
        lat = np.radians([f.lat for f in feats])
        lon = np.radians([f.lon for f in feats])
        vb = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
        vi = self.geom.rotation.T @ vb
        a, b, c = e_t @ vi, n_t @ vi, w @ vi
        sun_alt = np.degrees(np.arcsin(np.clip(self.geom.sun_body @ vb, -1, 1)))
        x, y = self.view.to_screen(a, b)
        dpr = self.devicePixelRatioF()
        px_per_km = self.view.scale / moonlib.MOON_RADIUS_KM / dpr
        for i, f in enumerate(feats):
            if c[i] < 0.05:
                continue
            self._labels.append((f, x[i] / dpr, y[i] / dpr, f.diam * px_per_km / 2.0,
                                 float(sun_alt[i])))

    # -- desenho -----------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(8, 10, 16))
        if self._image is not None:
            p.drawImage(0, 0, self._image)
        p.setRenderHint(QPainter.Antialiasing, True)
        font = QFont("Segoe UI", 9)
        fm = QFontMetrics(font)
        taken: list[QRectF] = []
        if self.selected is not None:
            for f, x, y, r, _alt in self._labels:
                if f is self.selected:
                    p.setPen(QPen(QColor(255, 170, 60), 1.6))
                    p.setBrush(Qt.NoBrush)
                    rr = max(r, 7.0)
                    p.drawEllipse(QPointF(x, y), rr, rr)
                    tw = fm.horizontalAdvance(f.name)
                    _outlined(p, x - tw / 2, y - rr - 5, f.name, font, QColor(255, 190, 90))
                    taken.append(QRectF(x - tw / 2, y - rr - 5 - fm.ascent(), tw, fm.height()))
        if self.show_names:
            for f, x, y, r, alt in self._labels:
                if f is self.selected or 2 * r < 16 or alt < -3.0:
                    continue
                if not (0 <= x <= self.width() and 0 <= y <= self.height()):
                    continue
                text = label_for(f)
                tw = fm.horizontalAdvance(text)
                rect = QRectF(x - tw / 2, y - fm.ascent() / 2, tw, fm.height())
                if any(rect.intersects(t) for t in taken):
                    continue
                taken.append(rect.adjusted(-3, -1, 3, 1))
                ink = QColor(255, 226, 150) if not f.l100 else QColor(150, 220, 255)
                _outlined(p, x - tw / 2, y + fm.ascent() / 2 - 2, text, font, ink)
        p.end()

    def resizeEvent(self, _event) -> None:
        self.invalidate()

    # -- interação ----------------------------------------------------------
    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        dpr = self.devicePixelRatioF()
        pos = event.position()
        a0, b0 = self.view.to_local(pos.x() * dpr, pos.y() * dpr)
        self.view.zoom = float(min(16.0, max(0.6, self.view.zoom * factor)))
        a1, b1 = self.view.to_local(pos.x() * dpr, pos.y() * dpr)
        # mantém o ponto sob o cursor parado
        self.view.pan_a += float(a0 - a1)
        self.view.pan_b += float(b0 - b1)
        self.invalidate()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag = (event.position(), self.view.pan_a, self.view.pan_b, False)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None:
            start, pa, pb, _moved = self._drag
            d = event.position() - start
            if abs(d.x()) + abs(d.y()) > 3:
                dpr = self.devicePixelRatioF()
                a0, b0 = self.view.to_local(start.x() * dpr, start.y() * dpr)
                a1, b1 = self.view.to_local(event.position().x() * dpr,
                                            event.position().y() * dpr)
                self.view.pan_a = pa + float(a0 - a1)
                self.view.pan_b = pb + float(b0 - b1)
                self._drag = (start, pa, pb, True)
                self.invalidate()
            return
        hit = self.feature_at(event.position().x(), event.position().y())
        self.setToolTip(f"{hit.name} — {hit.summary()}" if hit else "")

    def mouseReleaseEvent(self, event) -> None:
        if self._drag is not None and not self._drag[3]:
            hit = self.feature_at(event.position().x(), event.position().y())
            if hit is not None:
                self.featureClicked.emit(hit)
        self._drag = None

    def feature_at(self, x: float, y: float):
        """Menor formação que contém o ponto (ou a mais próxima a 12 px)."""
        best, best_r = None, 1e9
        for f, fx, fy, r, _alt in self._labels:
            d = math.hypot(fx - x, fy - y)
            if d <= max(r, 6.0) and r < best_r:
                best, best_r = f, r
        return best

    def center_on(self, f: moonlib.MoonFeature, zoom: float | None = None) -> None:
        if self.geom is None:
            return
        a, b, _c = moonlib.feature_local(self.geom, f.lat, f.lon)
        self.view.pan_a, self.view.pan_b = a, b
        if zoom is not None:
            self.view.zoom = zoom
        self.invalidate()


class MoonWindow(QMainWindow):
    """Planejar ▸ Lua ▸ Janela da Lua."""

    markObserved = Signal(str, str, str)       # kind, ident, nome

    def __init__(self, engine, when_utc: dt.datetime, parent=None,
                 observed: set | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("A Lua"))
        self.engine = engine
        self.when = when_utc
        self.observed = observed or set()
        self.canvas = MoonCanvas()
        self.canvas.featureClicked.connect(self.select_feature)

        bar = QHBoxLayout()
        self.lbl_when = QLabel()
        self.lbl_when.setMinimumWidth(170)
        bar.addWidget(self.lbl_when)
        for text, hours in (("◀ 1 d", -24), ("◀ 1 h", -1), ("1 h ▶", 1), ("1 d ▶", 24)):
            b = QPushButton(text)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, h=hours: self.step(h))
            bar.addWidget(b)
        now = QPushButton(self.tr("Agora"))
        now.clicked.connect(self.to_now)
        bar.addWidget(now)
        bar.addSpacing(12)
        self.cmb_orient = QComboBox()
        for key, label in ORIENTATIONS:
            self.cmb_orient.addItem(self.tr(label), key)
        self.cmb_orient.currentIndexChanged.connect(self._apply_orientation)
        bar.addWidget(self.cmb_orient)
        self.chk_names = QCheckBox(self.tr("Nomes"))
        self.chk_names.setChecked(True)
        self.chk_names.toggled.connect(self._toggle_names)
        bar.addWidget(self.chk_names)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Procurar formação…"))
        names = sorted({f.name for f in moonlib.features()} |
                       {f.pt for f in moonlib.features() if f.pt})
        comp = QCompleter(names, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.search.setCompleter(comp)
        self.search.returnPressed.connect(self._search)
        comp.activated.connect(lambda _t: self._search())
        bar.addWidget(self.search, 1)
        fit = QPushButton(self.tr("Disco inteiro"))
        fit.clicked.connect(self._fit)
        bar.addWidget(fit)

        self.info = QTextBrowser()
        self.term = QTreeWidget()
        self.term.setHeaderLabels([self.tr("Formação"), self.tr("Tipo"),
                                   self.tr("Sol"), ""])
        self.term.setRootIsDecorated(False)
        self.term.itemActivated.connect(self._term_chosen)
        self.term.itemClicked.connect(self._term_chosen)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        self.btn_obs = QPushButton(self.tr("✓ Marcar como observada"))
        self.btn_obs.setEnabled(False)
        self.btn_obs.clicked.connect(self._mark)
        self.btn_dates = QPushButton(self.tr("Próximas noites boas"))
        self.btn_dates.setEnabled(False)
        self.btn_dates.clicked.connect(self._good_dates)
        detail_box = QWidget()
        dl = QVBoxLayout(detail_box)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.detail, 1)
        row = QHBoxLayout()
        row.addWidget(self.btn_dates)
        row.addWidget(self.btn_obs)
        dl.addLayout(row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.info, self.tr("Hoje"))
        self.tabs.addTab(self.term, self.tr("No terminador"))
        self.tabs.addTab(detail_box, self.tr("Formação"))

        split = QSplitter()
        split.addWidget(self.canvas)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(bar)
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self.resize(1250, 760)
        self.selected: moonlib.MoonFeature | None = None
        self.refresh()

    # -- tempo --------------------------------------------------------------
    def step(self, hours: float) -> None:
        self.when = self.when + dt.timedelta(hours=hours)
        self.refresh()

    def to_now(self) -> None:
        self.when = dt.datetime.now(dt.timezone.utc)
        self.refresh()

    def set_time(self, when_utc: dt.datetime) -> None:
        self.when = when_utc
        self.refresh()

    def refresh(self) -> None:
        self.geom = moonlib.geometry(self.engine, self.when)
        self.lbl_when.setText(f"{to_local(self.when):%d/%m/%Y %H:%M}")
        self.canvas.set_geometry(self.geom)
        self._apply_orientation()
        self._fill_info()
        self._fill_terminator()
        if self.selected is not None:
            self._fill_detail(self.selected)

    def _zenith_pa(self) -> float:
        """Ângulo de posição do zênite visto na Lua (graus)."""
        t = self.engine.ts.from_datetime(self.when)
        zen = self.engine.horizontal_matrix(t)[2]
        return moonlib._position_angle(np.asarray(zen, np.float64),
                                       self.geom.moon_icrs)

    def _apply_orientation(self, *_a) -> None:
        key = self.cmb_orient.currentData()
        v = self.canvas.view
        v.mirror = key == "mirror"
        if key == "sky":
            v.rotation = -self._zenith_pa()
        elif key == "inverted":
            v.rotation = 180.0
        else:
            v.rotation = 0.0
        self.canvas.invalidate()

    def _toggle_names(self, on: bool) -> None:
        self.canvas.show_names = on
        self.canvas.update()

    def _fit(self) -> None:
        v = self.canvas.view
        v.zoom, v.pan_a, v.pan_b = 1.0, 0.0, 0.0
        self.canvas.invalidate()

    # -- painéis --------------------------------------------------------------
    def _fill_info(self) -> None:
        g = self.geom
        lib_side = []
        if g.lib_lon > 2:
            lib_side.append("a borda leste (Mare Crisium)")
        elif g.lib_lon < -2:
            lib_side.append("a borda oeste (Grimaldi)")
        if g.lib_lat > 2:
            lib_side.append("o polo norte")
        elif g.lib_lat < -2:
            lib_side.append("o polo sul")
        lib_txt = (" — mostra mais " + " e ".join(lib_side)) if lib_side else ""
        t = self.engine.ts.from_datetime(self.when)
        alt = self.engine.site.at(t).observe(self.engine.eph["moon"]).apparent().altaz()[0].degrees
        rows = [
            ("Fase", f"{g.phase_name} · {g.illumination * 100:.0f}% iluminada"),
            ("Idade", f"{num(g.age_days)} dias desde a Lua nova"),
            ("Colongitude", f"{num(g.colongitude)}° (terminador da manhã em "
                            f"{num(abs(-g.colongitude + 360 if g.colongitude > 180 else g.colongitude))}°"
                            f"{'O' if g.colongitude <= 180 else 'L'})"),
            ("Libração", f"{num(g.lib_lon)}° em longitude, {num(g.lib_lat)}° em latitude{lib_txt}"),
            ("Sol subsolar", f"{num(g.sun_lat)}°, {num(g.sun_lon)}°"),
            ("Distância", f"{g.distance_km:,.0f} km".replace(",", ".")),
            ("Diâmetro aparente", f"{num(g.angular_diameter_arcmin)}′"),
            ("Altura agora", f"{num(alt)}°" + (" (abaixo do horizonte)" if alt < 0 else "")),
        ]
        html = ["<table cellspacing=4>"]
        for k, v in rows:
            html.append(f"<tr><td style='color:#9aa'>{k}</td><td>{v}</td></tr>")
        html.append("</table>")
        html.append(f"<p>{moonlib.photo_advice(g.illumination, g.waxing)}</p>")
        self.info.setHtml("".join(html))

    def _fill_terminator(self) -> None:
        self.term.clear()
        for e in moonlib.terminator_features(self.geom, limit=150):
            f = e.feature
            it = QTreeWidgetItem([f.name, f.type_pt, f"{num(e.sun_alt)}°",
                                  ("★ L100" if f.l100 else "") +
                                  (" · manhã" if e.morning else " · tarde")])
            it.setData(0, Qt.UserRole, f)
            if f.l100:
                it.setForeground(0, QColor(150, 220, 255))
            self.term.addTopLevelItem(it)
        for col in range(4):
            self.term.resizeColumnToContents(col)

    def _term_chosen(self, item, _col=0) -> None:
        f = item.data(0, Qt.UserRole)
        if f is not None:
            self.select_feature(f)
            self.canvas.center_on(f, max(self.canvas.view.zoom, 2.5))

    def _search(self) -> None:
        f = moonlib.find_feature(self.search.text())
        if f is not None and f.lat == f.lat:
            self.select_feature(f)
            self.canvas.center_on(f, max(self.canvas.view.zoom, 3.0))

    def select_feature(self, f) -> None:
        self.selected = f
        self.canvas.selected = f
        self.canvas.update()
        self._fill_detail(f)
        self.tabs.setCurrentIndex(2)

    def _ident(self, f) -> tuple[str, str]:
        from ..core.programs import LUNAR_KIND, lunar_ident

        return (LUNAR_KIND, f"L100 {f.l100}" if f.l100 else lunar_ident(f.name))

    def _fill_detail(self, f, dates_html: str = "") -> None:
        g = self.geom
        alt = g.sun_altitude_at(f.lat, f.lon)
        vis = g.view_cos(f.lat, f.lon)
        if vis < 0:
            state = "no lado oculto agora (a libração não o mostra)"
        elif alt < -0.5:
            state = "no escuro (noite lunar)"
        elif alt < moonlib.GOOD_SUN_MAX:
            state = (f"com o Sol baixo ({num(alt)}°, "
                     f"{'nascendo' if g.is_morning(f.lon) else 'se pondo'}): relevo realçado")
        else:
            state = f"com o Sol alto ({num(alt)}°): pouco relevo, bom para albedo"
        kind, ident = self._ident(f)
        done = (kind, ident) in self.observed
        title = f.name + (f" <span style='color:#9aa'>({f.pt})</span>" if f.pt else "")
        html = [f"<h3>{title}</h3>", f"<p>{f.summary()}</p>",
                f"<p><b>Agora:</b> {state}.</p>"]
        if f.l100:
            html.append(f"<p><b>Lunar 100 nº {f.l100}</b>" +
                        (" — <span style='color:#7d7'>observada ✓</span>" if done else "") +
                        "</p>")
        if f.desc:
            html.append(f"<p>{f.desc}</p>")
        html.append(dates_html)
        self.detail.setHtml("".join(html))
        self.btn_obs.setEnabled(True)
        self.btn_obs.setText(self.tr("✓ Observada") if done else
                             self.tr("✓ Marcar como observada"))
        self.btn_dates.setEnabled(f.lat == f.lat)

    def _good_dates(self) -> None:
        f = self.selected
        if f is None or f.lat != f.lat:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            wins = moonlib.good_dates(self.engine, f.lat, f.lon, self.when, days=60)
        finally:
            QApplication.restoreOverrideCursor()
        if not wins:
            html = ("<p><b>Próximas noites boas:</b> nenhuma nos próximos 60 dias "
                    "com a Lua alta e o céu escuro.</p>")
        else:
            items = []
            for w in wins[:8]:
                a, b = to_local(w.start_utc), to_local(w.end_utc)
                items.append(f"<li>{a:%d/%m} das {a:%H:%M} às {b:%H:%M} — Sol a "
                             f"{num(w.sun_alt_min)}–{num(w.sun_alt_max)}°, "
                             f"{'manhã' if w.morning else 'tarde'} lunar</li>")
            html = ("<p><b>Próximas noites boas</b> (Sol rasante na formação, "
                    "Lua acima de 15° e céu escuro):</p><ul>" + "".join(items) + "</ul>")
        self._fill_detail(f, html)

    def _mark(self) -> None:
        f = self.selected
        if f is None:
            return
        kind, ident = self._ident(f)
        self.markObserved.emit(kind, ident, f.name)

    def set_observed(self, observed: set) -> None:
        self.observed = observed
        if self.selected is not None:
            self._fill_detail(self.selected)
