"""Gerador de carta celeste (v0.16 T3) — Arquivo ▸ Gerar carta…

Enquadramento (vista atual, objeto, constelação inteira, campo do
equipamento, rotação), papel (A4, A3, Carta; retrato ou paisagem;
margens), tema (papel, escuro, vermelho), conteúdo (estrelas e nomes até
uma magnitude, linhas, fronteiras, grades, Via Láctea, céu profundo com
filtro próprio…), moldura (título, bússola, escala, legenda, rodapé),
pré-visualização ao vivo, perfis salvos e **atlas** multipágina. O
resultado abre no editor de anotações, que imprime e exporta PDF, PNG e
SVG.

O render é fora da tela (``SkyWidget.render_frame``): a vista do usuário
não muda enquanto a carta é gerada.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np

from ..core.projection import Camera, vec_to_altaz
from ..render.chart_frame import ChartInfo, ChartSpec, compose_page, layout, map_render_size


# ---------------------------------------------------------------------------
# Montagem (sem interface — testável)
# ---------------------------------------------------------------------------

def _target_vector(sky, target: str, t):
    """Vetor horizontal do alvo ``kind:ident`` (ou da seleção atual)."""
    from ..core.objects import ObjectRef

    m = sky.engine.horizontal_matrix(t)
    if target and ":" in target:
        kind, ident = target.split(":", 1)
        if kind == "const":
            k = next((i for i, c in enumerate(sky.const_info) if c.get("id") == ident), None)
            return None if k is None else m @ sky.const_centers[k].astype(np.float64)
        ref = ObjectRef.from_ident(kind, ident, sky.stars, sky.dso)
    elif sky.selection is not None:
        ref = ObjectRef.resolve(sky.selection, sky.stars, sky.dso)
    else:
        return None
    if ref is None:
        return None
    if ref.icrs is not None:
        return m @ ref.icrs
    state = next((b for b in sky.engine.bodies(t) if b.name == ref.key), None)
    return state.vec if state is not None else None


def constellation_fov(sky, cid: str) -> float:
    """Campo (graus) que contém a constelação inteira pelas fronteiras IAU."""
    k = next((i for i, c in enumerate(sky.const_info) if c.get("id") == cid), None)
    if k is None:
        return 40.0
    center = sky.const_centers[k].astype(np.float64)
    sub = sky._const_subset(sky.const_bounds, cid)
    if not len(sub.verts):
        return 40.0
    dots = np.clip(sub.verts.astype(np.float64) @ center, -1.0, 1.0)
    return float(min(100.0, max(10.0, 2.3 * math.degrees(float(np.arccos(dots.min()))))))


def frame_camera(sky, spec: ChartSpec, when_utc: dt.datetime | None = None):
    """(câmera, campos de equipamento ou None) para o enquadramento pedido."""
    t = sky.engine.ts.from_datetime(when_utc) if when_utc else sky.engine.time.current()
    fov = math.radians(max(0.5, min(100.0, spec.fov_deg)))
    shapes = sky.fov_shapes if spec.show_fov else None
    if spec.framing == "view":
        return Camera(sky.camera.az, sky.camera.alt, fov), shapes
    target = spec.target
    if spec.framing == "constellation" and target and not target.startswith("const:"):
        target = f"const:{target}"
    vec = _target_vector(sky, target, t)
    if vec is None:
        return Camera(sky.camera.az, sky.camera.alt, fov), shapes
    az, alt = vec_to_altaz(vec)
    if spec.framing == "field":
        shapes = sky.fov_shapes or shapes
    return Camera(az, alt, fov), shapes


def chart_info(sky, cam: Camera, spec: ChartSpec, size_px: tuple[int, int],
               when_utc: dt.datetime | None, location: str) -> ChartInfo:
    """Norte e leste celestes no centro do mapa e a escala em px/grau."""
    from ..core.localtime import to_local

    t = sky.engine.ts.from_datetime(when_utc) if when_utc else sky.engine.time.current()
    m = sky.engine.horizontal_matrix(t)
    probe = Camera(cam.az, cam.alt, cam.fov)
    probe.set_viewport(*size_px)
    cx, cy = size_px[0] / 2.0, size_px[1] / 2.0
    c_h = probe.unproject(cx, cy)
    c = m.T @ c_h
    pole = np.array([0.0, 0.0, 1.0])
    north = pole - float(pole @ c) * c
    if np.linalg.norm(north) < 1e-9:
        north = np.array([1.0, 0.0, 0.0])
    north /= np.linalg.norm(north)
    east = np.cross(pole, c)
    east = east / np.linalg.norm(east) if np.linalg.norm(east) > 1e-9 else np.cross(north, c)

    def angle(direction) -> float:
        v = c + 0.01 * direction
        v /= np.linalg.norm(v)
        x, y, _ = probe.project((m @ v)[np.newaxis, :], margin=1e9)
        return math.degrees(math.atan2(float(x[0]) - cx, cy - float(y[0])))

    when = to_local(when_utc or sky.engine.time.current_datetime())
    return ChartInfo(location=location, when_text=f"{when:%d/%m/%Y %H:%M}",
                     fov_deg=math.degrees(cam.fov), north_deg=angle(north),
                     east_deg=angle(east), px_per_deg=probe.pixel_scale * math.pi / 180.0,
                     map_px=size_px)


def render_chart_page(sky, spec: ChartSpec, when_utc: dt.datetime | None = None,
                      location: str = "", dpi: int | None = None,
                      scale: float = 2.0):
    """Página completa (``QImage``) da carta descrita por ``spec``."""
    W, H = spec.page_px(dpi)
    k = (dpi or spec.dpi) / 200.0              # rótulos com o mesmo tamanho no papel
    eff = max(0.5, scale * k)
    lw, lh = map_render_size(spec, W, H, eff)
    cam, shapes = frame_camera(sky, spec, when_utc)
    options = spec.render_options(sky.render_options())
    img = sky.render_frame(lw, lh, options=options, camera=cam, when_utc=when_utc,
                           scale=eff, theme=spec.theme, show_selection=spec.show_marker,
                           fov_shapes=shapes if spec.show_fov else [])
    info = chart_info(sky, cam, spec, (img.width(), img.height()), when_utc, location)
    return compose_page(img, spec, info, (W, H))


def atlas_jobs(main, base: ChartSpec, source: str) -> list[tuple[ChartSpec, object]]:
    """(especificação, instante) de cada página do atlas.

    ``plan``: uma página por parada do último roteiro aberto, no horário dela;
    ``list``: uma por item da lista do ★, na melhor hora desta noite;
    ``constellations``: uma por constelação acima de 25° agora.
    """
    import dataclasses

    from ..catalogs.constnames import CONSTELLATIONS

    jobs: list[tuple[ChartSpec, object]] = []
    if source == "plan":
        plan = next((w.plan for w in reversed(main._track_windows)
                     if hasattr(w, "plan") and getattr(w.plan, "entries", None)), None)
        for e in (plan.entries if plan else []):
            jobs.append((dataclasses.replace(base, framing="object",
                                             target=f"{e.kind}:{e.ident}",
                                             title=e.label, subtitle=""),
                         e.when_utc if plan.timed else None))
    elif source == "list":
        from ..core.objects import ObjectRef
        from ..core.userdata import DEFAULT_LIST
        from ..core.visibility import visibility_of

        name = main.settings.value("lists/current", DEFAULT_LIST, str)
        lid = main.userdata.list_id(name)
        now = main.engine.time.current_datetime()
        for item in (main.userdata.items(lid) if lid is not None else []):
            ref = ObjectRef.from_ident(item["kind"], item["ident"], main.star_catalog,
                                       main.dso_catalog)
            if ref is None:
                continue
            vis = visibility_of(main.engine, ref, now, min_alt=10.0,
                                horizon=main.horizon_profile)
            jobs.append((dataclasses.replace(base, framing="object",
                                             target=f"{item['kind']}:{item['ident']}",
                                             title=ref.name, subtitle=""),
                         vis.best_utc if vis.observable else None))
    else:
        sky = main.sky
        m = sky.engine.horizontal_matrix(sky.engine.time.current())
        for k, info in enumerate(sky.const_info):
            cid = info.get("id", "")
            h = m @ sky.const_centers[k].astype(np.float64)
            if math.degrees(math.asin(max(-1.0, min(1.0, float(h[2]))))) < 25.0:
                continue
            latin, pt = CONSTELLATIONS.get(cid, (cid, cid))
            jobs.append((dataclasses.replace(base, framing="constellation", target=cid,
                                             fov_deg=constellation_fov(sky, cid),
                                             title=f"{pt} ({latin})", subtitle=""), None))
        jobs.sort(key=lambda j: j[0].title)
    return jobs


# ---------------------------------------------------------------------------
# Diálogo
# ---------------------------------------------------------------------------

from PySide6.QtCore import QDateTime, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDoubleSpinBox,
    QFormLayout, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QProgressDialog, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..render.chart_frame import CONTENT_LAYERS, FRAMINGS, PAPERS  # noqa: E402
from ..render.themes import THEMES  # noqa: E402


class ChartDialog(QDialog):
    """Arquivo ▸ Gerar carta…"""

    def __init__(self, main, parent=None) -> None:
        super().__init__(parent or main)
        self.main = main
        self.sky = main.sky
        self.setWindowTitle(self.tr("Gerar carta celeste"))
        self.resize(1180, 720)
        self.spec = ChartSpec(fov_deg=round(math.degrees(self.sky.camera.fov), 1))
        if self.sky.selection is not None:
            from ..core.objects import ObjectRef

            ref = ObjectRef.resolve(self.sky.selection, self.sky.stars, self.sky.dso)
            if ref is not None:
                self.spec.target = f"{ref.kind}:{ref.ident}"
                self.spec.title = ref.name
                self.spec.framing = "object"
        self._building = False

        tabs = QTabWidget()
        tabs.addTab(self._tab_framing(), self.tr("Enquadramento"))
        tabs.addTab(self._tab_paper(), self.tr("Papel"))
        tabs.addTab(self._tab_content(), self.tr("Conteúdo"))
        tabs.addTab(self._tab_frame(), self.tr("Moldura"))
        tabs.addTab(self._tab_atlas(), self.tr("Atlas"))

        self.profiles = QComboBox()
        btn_save = QPushButton(self.tr("Salvar perfil…"))
        btn_del = QPushButton(self.tr("Excluir"))
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel(self.tr("Perfil:")))
        prof_row.addWidget(self.profiles, 1)
        prof_row.addWidget(btn_save)
        prof_row.addWidget(btn_del)

        left = QVBoxLayout()
        left.addLayout(prof_row)
        left.addWidget(tabs, 1)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(560, 400)
        self.preview.setStyleSheet("background:#2a2c33;")
        self.status = QLabel()
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(self.status)

        btn_editor = QPushButton(self.tr("Abrir no editor (imprimir / exportar)"))
        btn_editor.setDefault(True)
        btn_close = QPushButton(self.tr("Fechar"))
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(btn_editor)
        bottom.addWidget(btn_close)

        top = QHBoxLayout()
        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(470)
        top.addWidget(lw)
        top.addLayout(right, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(top, 1)
        lay.addLayout(bottom)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self.update_preview)
        btn_save.clicked.connect(self._save_profile)
        btn_del.clicked.connect(self._delete_profile)
        self.profiles.activated.connect(self._load_profile)
        btn_editor.clicked.connect(self.open_editor)
        btn_close.clicked.connect(self.close)
        self._refresh_profiles()
        self._spec_to_widgets()
        QTimer.singleShot(50, self.update_preview)

    # -- abas --------------------------------------------------------------
    def _watch(self, *widgets) -> None:
        for w in widgets:
            for sig in ("currentIndexChanged", "valueChanged", "toggled", "textChanged",
                        "dateTimeChanged"):
                if hasattr(w, sig):
                    getattr(w, sig).connect(self._changed)
                    break

    def _tab_framing(self) -> QWidget:
        from ..catalogs.constnames import CONSTELLATIONS

        w = QWidget()
        f = QFormLayout(w)
        self.w_framing = QComboBox()
        for key, label in FRAMINGS.items():
            self.w_framing.addItem(self.tr(label), key)
        self.w_const = QComboBox()
        for abbr, (latin, pt) in sorted(CONSTELLATIONS.items(), key=lambda x: x[1][1]):
            self.w_const.addItem(f"{pt} ({latin})", abbr)
        self.w_target = QLabel()
        self.w_fov = QDoubleSpinBox()
        self.w_fov.setRange(0.5, 100.0)
        self.w_fov.setDecimals(1)
        self.w_fov.setSuffix("°")
        self.w_rot = QSpinBox()
        self.w_rot.setRange(-180, 180)
        self.w_rot.setSuffix("°")
        self.w_when = QDateTimeEdit()
        self.w_when.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.w_when.setCalendarPopup(True)
        btn_now = QPushButton(self.tr("Instante da simulação"))
        btn_now.clicked.connect(self._set_now)
        self._set_now()
        f.addRow(self.tr("Enquadrar"), self.w_framing)
        f.addRow(self.tr("Constelação"), self.w_const)
        f.addRow(self.tr("Objeto"), self.w_target)
        f.addRow(self.tr("Campo (vertical)"), self.w_fov)
        f.addRow(self.tr("Rotação"), self.w_rot)
        f.addRow(self.tr("Data e hora"), self.w_when)
        f.addRow("", btn_now)
        hint = QLabel(self.tr("A carta mostra o céu como você o vê nessa hora: o "
                              "zênite para cima. A bússola indica o norte e o leste "
                              "celestes."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a93a5;")
        f.addRow(hint)
        self.w_const.currentIndexChanged.connect(self._const_chosen)
        self._watch(self.w_framing, self.w_fov, self.w_rot, self.w_when)
        return w

    def _tab_paper(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.w_paper = QComboBox()
        self.w_paper.addItems(list(PAPERS))
        self.w_orient = QComboBox()
        self.w_orient.addItem(self.tr("Paisagem"), True)
        self.w_orient.addItem(self.tr("Retrato"), False)
        self.w_margin = QDoubleSpinBox()
        self.w_margin.setRange(0, 40)
        self.w_margin.setSuffix(" mm")
        self.w_dpi = QSpinBox()
        self.w_dpi.setRange(100, 400)
        self.w_dpi.setSingleStep(50)
        self.w_dpi.setSuffix(" dpi")
        f.addRow(self.tr("Papel"), self.w_paper)
        f.addRow(self.tr("Orientação"), self.w_orient)
        f.addRow(self.tr("Margens"), self.w_margin)
        f.addRow(self.tr("Resolução"), self.w_dpi)
        self._watch(self.w_paper, self.w_orient, self.w_margin)
        return w

    def _tab_content(self) -> QWidget:
        from ..core.dsofilter import PRESETS

        w = QWidget()
        g = QGridLayout(w)
        self.w_theme = QComboBox()
        for key, label in THEMES.items():
            self.w_theme.addItem(self.tr(label), key)
        self.w_star = QDoubleSpinBox()
        self.w_star.setRange(2.0, 12.0)
        self.w_star.setSingleStep(0.5)
        self.w_names = QDoubleSpinBox()
        self.w_names.setRange(-1.5, 7.0)
        self.w_names.setSingleStep(0.5)
        self.w_preset = QComboBox()
        self.w_preset.addItems(list(PRESETS))
        self.w_dsonames = QComboBox()
        self.w_dsonames.addItem(self.tr("Designação (M 42)"), "number")
        self.w_dsonames.addItem(self.tr("Nome (Nebulosa de Órion)"), "name")
        self.w_constmode = QComboBox()
        for key, label in (("pt", "Português"), ("latin", "Latim"), ("abbr", "Sigla")):
            self.w_constmode.addItem(self.tr(label), key)
        form = QFormLayout()
        form.addRow(self.tr("Tema"), self.w_theme)
        form.addRow(self.tr("Estrelas até a magnitude"), self.w_star)
        form.addRow(self.tr("Nomes de estrelas até"), self.w_names)
        form.addRow(self.tr("Céu profundo (filtro)"), self.w_preset)
        form.addRow(self.tr("Rótulos de céu profundo"), self.w_dsonames)
        form.addRow(self.tr("Nomes das constelações"), self.w_constmode)
        g.addLayout(form, 0, 0, 1, 2)
        self.w_layers = {}
        for i, (key, label, _default) in enumerate(CONTENT_LAYERS):
            cb = QCheckBox(self.tr(label))
            self.w_layers[key] = cb
            g.addWidget(cb, 1 + i // 2, i % 2)
            self._watch(cb)
        row = 2 + len(CONTENT_LAYERS) // 2
        self.w_showfov = QCheckBox(self.tr("Campo do equipamento"))
        self.w_marker = QCheckBox(self.tr("Marcador da seleção"))
        g.addWidget(self.w_showfov, row, 0)
        g.addWidget(self.w_marker, row, 1)
        g.setRowStretch(row + 1, 1)
        self._watch(self.w_theme, self.w_star, self.w_names, self.w_preset, self.w_dsonames,
                    self.w_constmode, self.w_showfov, self.w_marker)
        return w

    def _tab_frame(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.w_title = QLineEdit()
        self.w_subtitle = QLineEdit()
        self.w_subtitle.setPlaceholderText(self.tr("vazio = local · data · campo"))
        f.addRow(self.tr("Título"), self.w_title)
        f.addRow(self.tr("Subtítulo"), self.w_subtitle)
        self.w_frame = {}
        for key, label in (("show_title", "Título e subtítulo"), ("show_compass", "Bússola"),
                           ("show_scale", "Escala angular"), ("show_legend", "Legenda"),
                           ("show_footer", "Rodapé")):
            cb = QCheckBox(self.tr(label))
            self.w_frame[key] = cb
            f.addRow("", cb)
            self._watch(cb)
        self._watch(self.w_title, self.w_subtitle)
        return w

    def _tab_atlas(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.w_source = QComboBox()
        self.w_source.addItem(self.tr("Paradas do último roteiro aberto"), "plan")
        self.w_source.addItem(self.tr("Itens da minha lista (★)"), "list")
        self.w_source.addItem(self.tr("Constelações acima de 25° agora"), "constellations")
        self.w_atlas_fov = QDoubleSpinBox()
        self.w_atlas_fov.setRange(2.0, 60.0)
        self.w_atlas_fov.setValue(20.0)
        self.w_atlas_fov.setSuffix("°")
        btn = QPushButton(self.tr("Gerar atlas…"))
        btn.clicked.connect(self.make_atlas)
        f.addRow(self.tr("Páginas"), self.w_source)
        f.addRow(self.tr("Campo por objeto"), self.w_atlas_fov)
        f.addRow("", btn)
        hint = QLabel(self.tr("Cada página usa o papel, o tema, o conteúdo e a moldura "
                              "das outras abas. Objetos do roteiro saem no horário da "
                              "parada; os da lista, na melhor hora desta noite."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a93a5;")
        f.addRow(hint)
        return w

    # -- estado ---------------------------------------------------------------
    def _set_now(self) -> None:
        from ..core.localtime import to_local

        loc = to_local(self.sky.engine.time.current_datetime())
        self.w_when.setDateTime(QDateTime(loc.year, loc.month, loc.day, loc.hour, loc.minute, 0))

    def when_utc(self) -> dt.datetime:
        from ..core.localtime import from_local_naive

        q = self.w_when.dateTime()
        naive = dt.datetime(q.date().year(), q.date().month(), q.date().day(),
                            q.time().hour(), q.time().minute())
        return from_local_naive(naive).astimezone(dt.timezone.utc)

    def _const_chosen(self) -> None:
        if self._building:
            return
        from ..catalogs.constnames import CONSTELLATIONS

        cid = self.w_const.currentData()
        self._building = True
        self.w_framing.setCurrentIndex(self.w_framing.findData("constellation"))
        self.w_fov.setValue(constellation_fov(self.sky, cid))
        latin, pt = CONSTELLATIONS.get(cid, (cid, cid))
        self.w_title.setText(f"{pt} ({latin})")
        self._building = False
        self._changed()

    def _changed(self, *_args) -> None:
        if not self._building:
            self._timer.start()

    def _spec_to_widgets(self) -> None:
        s = self.spec
        self._building = True
        self.w_framing.setCurrentIndex(max(0, self.w_framing.findData(s.framing)))
        if s.framing == "constellation" and s.target:
            self.w_const.setCurrentIndex(max(0, self.w_const.findData(s.target.split(":")[-1])))
        obj = s.target.split(":", 1)[-1] if s.target and not s.target.startswith("const:") else ""
        self.w_target.setText(obj or self.tr("(nenhum — selecione no céu)"))
        self.w_fov.setValue(s.fov_deg)
        self.w_rot.setValue(int(s.rotation_deg))
        self.w_paper.setCurrentText(s.paper)
        self.w_orient.setCurrentIndex(0 if s.landscape else 1)
        self.w_margin.setValue(s.margin_mm)
        self.w_dpi.setValue(s.dpi)
        self.w_theme.setCurrentIndex(max(0, self.w_theme.findData(s.theme)))
        self.w_star.setValue(s.star_mag)
        self.w_names.setValue(s.name_mag)
        self.w_preset.setCurrentText(s.dso_preset)
        self.w_dsonames.setCurrentIndex(max(0, self.w_dsonames.findData(s.dso_name_mode)))
        self.w_constmode.setCurrentIndex(max(0, self.w_constmode.findData(s.const_label_mode)))
        for key, cb in self.w_layers.items():
            cb.setChecked(bool(s.layers.get(key, False)))
        self.w_showfov.setChecked(s.show_fov)
        self.w_marker.setChecked(s.show_marker)
        self.w_title.setText(s.title)
        self.w_subtitle.setText(s.subtitle)
        for key, cb in self.w_frame.items():
            cb.setChecked(bool(getattr(s, key)))
        self._building = False

    def widgets_to_spec(self) -> ChartSpec:
        s = self.spec
        s.framing = self.w_framing.currentData()
        if s.framing == "constellation":
            s.target = f"const:{self.w_const.currentData()}"
        elif s.target.startswith("const:"):
            s.target = ""
        s.fov_deg = float(self.w_fov.value())
        s.rotation_deg = float(self.w_rot.value())
        s.paper = self.w_paper.currentText()
        s.landscape = bool(self.w_orient.currentData())
        s.margin_mm = float(self.w_margin.value())
        s.dpi = int(self.w_dpi.value())
        s.theme = self.w_theme.currentData()
        s.star_mag = float(self.w_star.value())
        s.name_mag = float(self.w_names.value())
        s.dso_preset = self.w_preset.currentText()
        s.dso_name_mode = self.w_dsonames.currentData()
        s.const_label_mode = self.w_constmode.currentData()
        s.layers = {k: cb.isChecked() for k, cb in self.w_layers.items()}
        s.show_fov = self.w_showfov.isChecked()
        s.show_marker = self.w_marker.isChecked()
        s.title = self.w_title.text()
        s.subtitle = self.w_subtitle.text()
        for key, cb in self.w_frame.items():
            setattr(s, key, cb.isChecked())
        return s

    # -- saída ----------------------------------------------------------------
    def _location(self) -> str:
        return self.main.settings.location().name

    def update_preview(self) -> None:
        spec = self.widgets_to_spec()
        try:
            page = render_chart_page(self.sky, spec, self.when_utc(), self._location(),
                                     dpi=60, scale=1.0)
        except Exception as exc:  # noqa: BLE001 — a prévia não derruba o diálogo
            self.status.setText(self.tr("Falha na pré-visualização: {e}").format(e=exc))
            return
        pix = QPixmap.fromImage(page)
        self.preview.setPixmap(pix.scaled(self.preview.size(), Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        w, h = spec.page_mm()
        orient = self.tr("paisagem") if spec.landscape else self.tr("retrato")
        self.status.setText(self.tr("{p} {o} · {w:.0f} × {h:.0f} mm · {d} dpi na saída")
                            .format(p=spec.paper, o=orient, w=w, h=h, d=spec.dpi))

    def build_page(self, spec: ChartSpec | None = None, when=None):
        spec = spec or self.widgets_to_spec()
        return render_chart_page(self.sky, spec, when or self.when_utc(), self._location())

    def open_editor(self) -> None:
        from .print_window import PrintMapWindow

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            spec = self.widgets_to_spec()
            page = self.build_page(spec)
        finally:
            QApplication.restoreOverrideCursor()
        win = PrintMapWindow(page, spec.title, self.main, page_mm=spec.page_mm())
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        self.main._track_windows.append(win)
        self.editor = win
        win.show()

    def make_atlas(self) -> None:
        import dataclasses

        from .print_window import PrintMapWindow

        base = dataclasses.replace(self.widgets_to_spec(),
                                   fov_deg=float(self.w_atlas_fov.value()))
        jobs = atlas_jobs(self.main, base, self.w_source.currentData())
        if not jobs:
            QMessageBox.information(self, "Carina", self.tr(
                "Nada para o atlas: abra um roteiro, acrescente itens à lista ou "
                "escolha outra fonte."))
            return
        progress = QProgressDialog(self.tr("Gerando o atlas…"), self.tr("Cancelar"), 0,
                                   len(jobs), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(300)
        pages = []
        for i, (spec, when) in enumerate(jobs):
            progress.setValue(i)
            QApplication.processEvents()
            if progress.wasCanceled():
                break
            pages.append(self.build_page(spec, when))
        progress.close()
        if not pages:
            return
        win = PrintMapWindow(pages, self.tr("Atlas"), self.main, page_mm=base.page_mm())
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        self.main._track_windows.append(win)
        self.editor = win
        win.show()

    # -- perfis (carina.sqlite, kind = "chart") -------------------------------
    def _refresh_profiles(self) -> None:
        self.profiles.clear()
        self.profiles.addItem(self.tr("(atual)"), None)
        for name in self.main.userdata.profiles("chart"):
            self.profiles.addItem(name, name)

    def _save_profile(self) -> None:
        import json

        name, ok = QInputDialog.getText(self, self.tr("Perfil de carta"), self.tr("Nome:"))
        if ok and name.strip():
            data = json.loads(self.widgets_to_spec().to_json())
            data.pop("target", None)            # o perfil é o estilo, não o alvo
            self.main.userdata.save_profile("chart", name.strip(), data)
            self._refresh_profiles()
            self.profiles.setCurrentIndex(self.profiles.findData(name.strip()))

    def _load_profile(self) -> None:
        name = self.profiles.currentData()
        if not name:
            return
        data = self.main.userdata.profile("chart", name)
        if data:
            target = self.spec.target
            self.spec = ChartSpec.from_json(data)
            self.spec.target = target
            self._spec_to_widgets()
            self.update_preview()

    def _delete_profile(self) -> None:
        name = self.profiles.currentData()
        if name:
            self.main.userdata.delete_profile("chart", name)
            self._refresh_profiles()
