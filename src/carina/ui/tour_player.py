"""Player de tours (v0.20 T5).

Painel encostado à direita da janela principal (no lugar da ficha):
título do tour, passo N de M com a hora do céu, o texto em Markdown, uma
imagem ou um cartão opcional e os botões ◀ ▶, automático e Sair. Cada passo
leva o relógio ao instante calculado pelo :class:`core.tours.TourRun`, voa
até o alvo com o campo pedido e acende os destaques.

O estado do céu é fotografado ao entrar (:class:`core.skystate.SkyState`)
e restaurado ao sair — no fim, no meio ou por ``Esc``. Camadas e Bortle
pedidos por um passo valem dali em diante (são cumulativos), e voltar um
passo refaz a conta desde o início, então ◀ mostra exatamente o céu que
aquele passo mostrou da primeira vez.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QDockWidget, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QTextBrowser, QToolButton,
                               QVBoxLayout, QWidget)

from ..core import tours as T
from ..core.localtime import to_local

# fábricas de cartões extras dos passos gerados: tipo → (dados, player) → QWidget
CARD_FACTORIES: dict = {}


def register_card(kind: str):
    def deco(fn):
        CARD_FACTORIES[kind] = fn
        return fn
    return deco


class TourPlayer(QDockWidget):
    """Painel do tour em andamento."""

    finished = Signal(str, bool)          # chave do tour, concluído até o fim
    helpRequested = Signal()

    def __init__(self, main, parent=None) -> None:
        super().__init__(self.tr("Tour"), parent or main)
        self.main = main
        self.sky = main.sky
        self.engine = main.engine
        self.setObjectName("tour_player")
        self.setFeatures(QDockWidget.DockWidgetMovable)
        self.setMinimumWidth(340)
        self.run: T.TourRun | None = None
        self.state = None
        self._card_was_visible = False
        self._base_layers: dict = {}
        self._base_bortle = 5
        self._done = False

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        self.lbl_tour = QLabel()
        self.lbl_tour.setWordWrap(True)
        self.lbl_tour.setStyleSheet("color:#8a93a5; font-size:9pt;")
        self.lbl_step = QLabel()
        self.lbl_step.setStyleSheet("color:#8a93a5; font-size:9pt;")
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size:15pt; font-weight:600;")
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet("background:#3a2c14; color:#f3d79a; padding:6px; "
                                "border-radius:4px;")
        self.warn.hide()
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.hide()
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.setStyleSheet("background:transparent; font-size:10.5pt;")
        self.card_holder = QVBoxLayout()
        self.card_holder.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(self.lbl_tour)
        lay.addWidget(self.lbl_step)
        lay.addWidget(self.title)
        lay.addWidget(self.warn)
        lay.addWidget(self.image)
        lay.addWidget(self.text, 1)
        lay.addLayout(self.card_holder)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip(self.tr("Passo anterior (←)"))
        self.btn_prev.clicked.connect(self.prev)
        self.btn_next = QPushButton(self.tr("Próximo ▶"))
        self.btn_next.setToolTip(self.tr("Próximo passo (→)"))
        self.btn_next.clicked.connect(self.next)
        self.btn_auto = QToolButton()
        self.btn_auto.setText("⏵")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setToolTip(self.tr("Avançar sozinho (Espaço)"))
        self.btn_auto.toggled.connect(self._auto_toggled)
        self.btn_help = QToolButton()
        self.btn_help.setText("?")
        self.btn_help.setToolTip(self.tr("Como funcionam os tours"))
        self.btn_help.clicked.connect(self.helpRequested.emit)
        self.btn_present = QToolButton()
        self.btn_present.setText("⛶")
        self.btn_present.setCheckable(True)
        self.btn_present.setToolTip(self.tr("Modo apresentação: tela cheia, texto grande (F5)"))
        self.btn_present.toggled.connect(self._present_toggled)
        self.btn_voice = QToolButton()
        self.btn_voice.setText("🔊")
        self.btn_voice.setCheckable(True)
        self.btn_voice.setToolTip(self.tr("Narrar os passos com a voz do Windows (experimental)"))
        self.btn_voice.toggled.connect(self._voice_toggled)
        self.btn_exit = QPushButton(self.tr("Sair"))
        self.btn_exit.setToolTip(self.tr("Sair do tour e voltar o céu ao que era (Esc)"))
        self.btn_exit.clicked.connect(lambda: self.stop(False))
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next, 1)
        nav.addWidget(self.btn_auto)
        nav.addWidget(self.btn_present)
        nav.addWidget(self.btn_voice)
        nav.addWidget(self.btn_help)
        nav.addWidget(self.btn_exit)
        lay.addLayout(nav)

        # fim do tour
        self.end_box = QWidget()
        el = QVBoxLayout(self.end_box)
        el.setContentsMargins(0, 0, 0, 0)
        self.btn_list = QPushButton(self.tr("★ Guardar os objetos deste tour numa lista"))
        self.btn_list.clicked.connect(self._save_list)
        self.btn_suggest = QPushButton()
        self.btn_suggest.clicked.connect(self._start_suggested)
        el.addWidget(self.btn_list)
        el.addWidget(self.btn_suggest)
        self.end_box.hide()
        lay.addWidget(self.end_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body)
        self.setWidget(scroll)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._auto_next)
        self._shortcuts: list[QShortcut] = []
        for key, slot in ((Qt.Key_Right, self.next), (Qt.Key_Left, self.prev),
                          (Qt.Key_Space, lambda: self.btn_auto.toggle()),
                          (Qt.Key_Escape, lambda: self.stop(False)),
                          (Qt.Key_F5, lambda: self.btn_present.toggle())):
            sc = QShortcut(QKeySequence(key), main)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(slot)
            sc.setEnabled(False)
            self._shortcuts.append(sc)
        self.suggested_key = ""
        self._last_text = ""
        self._presenting = False
        self._saved_window: dict = {}
        self.overlay = None
        from ..core.speech import Speaker

        self.speaker = Speaker()
        settings = getattr(main, "settings", None)
        if settings is not None and settings.value("tours/voice", False, bool) \
                and self.speaker.available():
            self.btn_voice.blockSignals(True)
            self.btn_voice.setChecked(True)
            self.btn_voice.blockSignals(False)
        self.btn_voice.setEnabled(self.speaker.available())
        self.hide()

    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self.run is not None

    def start(self, tour: T.Tour, now_utc: dt.datetime | None = None) -> T.TourRun:
        """Começa o tour (encerra outro em andamento, restaurando o céu)."""
        from ..core.skystate import SkyState

        if self.active:
            self.stop(False)
        now = now_utc or self.engine.time.current_datetime()
        lat = self.main.settings.location().latitude if hasattr(self.main, "settings") else None
        self.run = T.TourRun(tour, self.engine, self.main.tour_resolver(), now, lat).prepare()
        self.state = SkyState.capture(self.sky, self.engine)
        self._base_layers = dict(self.sky.layers)
        self._base_bortle = int(self.sky.bortle)
        self._done = False
        info = getattr(self.main, "info_dock", None)
        self._card_was_visible = bool(info is not None and info.isVisible())
        if info is not None:
            info.hide()
        self.lbl_tour.setText(f"{tour.title} · {T.CATEGORIES.get(tour.category, '')}")
        self.end_box.hide()
        self.show()
        self.raise_()
        for sc in self._shortcuts:
            sc.setEnabled(True)
        if not self.run.steps:
            self._show_empty()
        else:
            self.apply()
        return self.run

    def stop(self, completed: bool = False) -> None:
        """Sai do tour: o céu volta exatamente ao que era."""
        if not self.active:
            return
        key = self.run.tour.key
        self._timer.stop()
        self.btn_auto.blockSignals(True)
        self.btn_auto.setChecked(False)
        self.btn_auto.blockSignals(False)
        for sc in self._shortcuts:
            sc.setEnabled(False)
        self.speaker.stop()
        if self._presenting:
            self.btn_present.setChecked(False)
        self._clear_card()
        if self.state is not None:
            self.state.restore(self.sky, self.engine)
        self.run = None
        self.state = None
        self.hide()
        info = getattr(self.main, "info_dock", None)
        if info is not None and self._card_was_visible:
            info.show()
        self.finished.emit(key, completed)

    # -- navegação --------------------------------------------------------
    def next(self) -> None:
        if not self.active:
            return
        if self.run.at_end:
            self._finish()
            return
        self.run.next()
        self.apply()

    def prev(self) -> None:
        if not self.active:
            return
        self.end_box.hide()
        self.run.prev()
        self.apply()

    def finish_animation(self) -> None:
        """Salta o voo em curso para o fim (capturas de tela e testes)."""
        anim = getattr(self.sky, "_goto_anim", None)
        if anim is not None:
            anim.setCurrentTime(anim.duration())

    def go(self, index: int) -> None:
        if self.active:
            self.run.go(index)
            self.apply()

    def _auto_toggled(self, on: bool) -> None:
        self.btn_auto.setText("⏸" if on else "⏵")
        if on:
            self._schedule()
        else:
            self._timer.stop()

    def _schedule(self) -> None:
        cur = self.run.current if self.run else None
        if cur is not None and self.btn_auto.isChecked():
            self._timer.start(int(max(4.0, cur.step.duration_s) * 1000))

    def _auto_next(self) -> None:
        if not self.active:
            return
        if self.run.at_end:
            self.btn_auto.setChecked(False)
            self._finish()
            return
        self.next()

    # -- aplicação de um passo ------------------------------------------------
    def apply(self) -> None:
        run = self.run
        cur = run.current
        if cur is None:
            return
        s = cur.step
        sky = self.sky
        # camadas e Bortle cumulativos até este passo
        layers = dict(self._base_layers)
        bortle = self._base_bortle
        for p in run.steps[:run.index + 1]:
            layers.update(p.step.layers)
            if p.step.bortle is not None:
                bortle = int(p.step.bortle)
        for k, v in layers.items():
            if sky.layers.get(k) != v:
                sky.set_layer(k, bool(v))
        if "const_names" in layers and layers["const_names"] and \
                getattr(sky, "const_label_mode", "none") == "none":
            sky.set_const_label_mode("pt")
        if int(sky.bortle) != bortle:
            sky.set_bortle(bortle)
        # relógio parado no instante do passo
        self.engine.time.set_fixed(cur.when)
        # destaques e seleção
        sky.clear_highlights()
        hls = list(cur.highlights)
        if not hls and cur.target is not None and cur.target.kind in ("const", "asterism") \
                and s.kind in ("goto", "highlight"):
            hls = [cur.target]
        for h in hls:
            if h.kind == "const":
                sky.highlight_constellation(h.key, 3600)
            elif h.kind == "asterism":
                sky.highlight_asterism(h.key, 3600)
        if cur.target is not None and cur.target.selection is not None:
            sky.selection = cur.target.selection        # sem abrir a ficha
        elif sky.selection is not None and s.kind != "intro":
            sky.selection = None
        # campos desenhados: binóculo (círculo) ou o setup ativo (v0.21)
        self._apply_fov_shapes(s)
        # câmera
        t = self.engine.ts.from_datetime(cur.when)
        vec = T.horizontal_vec(self.engine, cur.target, t) if cur.target is not None else None
        if vec is not None:
            sky.fly_to(vec, cur.fov)
        elif s.fov:
            sky.camera.fov = max(1e-3, float(s.fov)) * 3.141592653589793 / 180.0
        sky.update()
        self._fill_panel(cur)
        self._schedule()

    def _fill_panel(self, cur: T.PreparedStep) -> None:
        from ..core import lore

        run = self.run
        n, total = run.index + 1, len(run.steps)
        lt = to_local(cur.when)
        self.lbl_step.setText(self.tr("Passo {n} de {m} · céu de {d:%d/%m} às {h:%H:%M}")
                              .format(n=n, m=total, d=lt, h=lt))
        self.title.setText(cur.step.title)
        warns = []
        if run.index == 0:
            warns += run.warnings
            hidden = [sk for sk in run.skipped]
            if hidden:
                warns.append(self.tr("{k} passo(s) pulado(s): {l}.").format(
                    k=len(hidden), l="; ".join(sk.reason for sk in hidden)))
        if cur.below and cur.alt is not None:
            warns.append(self.tr("{o} está abaixo do horizonte agora ({a:.0f}°): o céu mostra "
                                 "onde ele está.").format(o=cur.target.label, a=cur.alt))
        self.warn.setVisible(bool(warns))
        self.warn.setText("\n".join(warns))
        text = T.expand_context(lore.expand(cur.step.text), self._context_values())
        if cur.finder_text:
            text += f"\n\n**Como achar.** {cur.finder_text}"
        self.text.setMarkdown(text)
        self._last_text = text
        self._set_image(cur.step.image)
        self._clear_card()
        card = cur.step.card
        if card and card.get("kind") in CARD_FACTORIES:
            w = CARD_FACTORIES[card["kind"]](card, self)
            if w is not None:
                self.card_holder.addWidget(w)
        self.btn_prev.setEnabled(run.index > 0)
        self.btn_next.setText(self.tr("Concluir ✓") if run.at_end else self.tr("Próximo ▶"))
        self.end_box.hide()
        if self._presenting:
            self._fill_overlay(cur)
        if self.btn_voice.isChecked():
            self.speaker.say(f"{cur.step.title}. {self._last_text}")

    def _context_values(self) -> dict:
        fn = getattr(self.main, "tour_context_values", None)
        try:
            return fn() if fn is not None else {}
        except Exception:                      # noqa: BLE001 — texto continua legível
            return {}

    def _apply_fov_shapes(self, s) -> None:
        import math

        from ..catalogs.equipment import FovShape

        shapes = []
        if s.fov_circle:
            d = math.radians(float(s.fov_circle))
            shapes = [FovShape("circle", d, d, self.tr("Binóculo — {f}°").format(
                f=f"{float(s.fov_circle):g}".replace(".", ",")))]
        elif s.setup_fov:
            setup = self.main.active_setup() if hasattr(self.main, "active_setup") else None
            if setup is not None:
                shapes = setup.shapes(self.main.equipment())
        self.sky.set_fov_shapes(shapes, 0.0, True)

    def _set_image(self, spec: str) -> None:
        path = None
        if spec.startswith("dss:"):
            from ..catalogs.images import image_path_for

            path = image_path_for(spec[4:].strip())
        elif spec:
            from ..config import package_data_dir

            p = package_data_dir() / "tours" / spec
            path = p if p.exists() else None
        if path is None:
            self.image.hide()
            return
        pm = QPixmap(str(path))
        if pm.isNull():
            self.image.hide()
            return
        w = max(220, self.width() - 40)
        self.image.setPixmap(pm.scaled(QSize(w, int(w * 0.75)), Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))
        self.image.show()

    def _clear_card(self) -> None:
        while self.card_holder.count():
            item = self.card_holder.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _show_empty(self) -> None:
        self.lbl_step.setText("")
        self.title.setText(self.tr("Nada para mostrar"))
        reasons = "; ".join(s.reason for s in self.run.skipped) or self.tr("sem passos")
        self.warn.setText(self.tr("Todos os passos foram pulados: {r}.").format(r=reasons))
        self.warn.show()
        self.text.setMarkdown(self.tr("Tente outra data na galeria de tours."))
        self.btn_next.setText(self.tr("Concluir ✓"))

    # -- fim ------------------------------------------------------------------
    def _finish(self) -> None:
        """Último passo: marca como feito e oferece o próximo e a lista."""
        if self._done:
            self.stop(True)
            return
        self._done = True
        from ..core.tours import mark_done

        if getattr(self.main, "userdata", None) is not None:
            mark_done(self.main.userdata, self.run.tour.key)
        self._timer.stop()
        self.btn_auto.setChecked(False)
        objs = self._objects()
        self.btn_list.setVisible(bool(objs))
        self.suggested_key = self.main.suggest_next_tour(self.run.tour.key) \
            if hasattr(self.main, "suggest_next_tour") else ""
        title = self.main.tour_title(self.suggested_key) if self.suggested_key else ""
        self.btn_suggest.setVisible(bool(title))
        self.btn_suggest.setText(self.tr("Próximo sugerido: {t} ▶").format(t=title))
        self.end_box.show()
        self.btn_next.setText(self.tr("Fechar o tour"))

    def _objects(self) -> list:
        out, seen = [], set()
        for p in self.run.steps:
            t = p.target
            if t is not None and t.kind in ("star", "dso") and t.spec not in seen:
                seen.add(t.spec)
                out.append(t)
        return out

    def _save_list(self) -> None:
        ud = getattr(self.main, "userdata", None)
        if ud is None:
            return
        from ..core.objects import ObjectRef

        name = self.tr("Tour: {t}").format(t=self.run.tour.title)
        lid = ud.list_id(name) or ud.create_list(name)
        for t in self._objects():
            ref = ObjectRef.resolve(t.selection, self.main.star_catalog, self.main.dso_catalog)
            if ref is not None:
                ra_dec = ref.ra_dec
                ud.add_item(lid, ref.kind, ref.ident, ref.name,
                            *(ra_dec if ra_dec else (None, None)))
        self.btn_list.setText(self.tr("✓ Guardado na lista “{n}”").format(n=name))
        self.btn_list.setEnabled(False)

    def _start_suggested(self) -> None:
        key = self.suggested_key
        self.stop(True)
        if key and hasattr(self.main, "start_tour"):
            self.main.start_tour(key)

    # -- voz (experimental) ------------------------------------------------
    def _voice_toggled(self, on: bool) -> None:
        settings = getattr(self.main, "settings", None)
        if settings is not None:
            settings.set_value("tours/voice", bool(on))
        if not on:
            self.speaker.stop()
        elif self.active and self.run.current is not None:
            self.speaker.say(f"{self.run.current.step.title}. {self._last_text}")

    # -- modo apresentação --------------------------------------------------
    @property
    def presenting(self) -> bool:
        return self._presenting

    def _present_toggled(self, on: bool) -> None:
        if on and not self._presenting:
            self.enter_presentation()
        elif not on and self._presenting:
            self.exit_presentation()

    def enter_presentation(self) -> None:
        """Tela cheia, sem menus nem painéis; o texto num painel inferior
        semitransparente sobre o céu, com letra grande, e avanço automático."""
        from PySide6.QtWidgets import QDockWidget

        main = self.main
        docks = [d for d in main.findChildren(QDockWidget) if d.isVisible()]
        self._saved_window = {
            "full": main.isFullScreen(), "max": main.isMaximized(),
            "geom": main.saveGeometry(), "docks": docks,
            "menu": main.menuBar().isVisible(),
            "status": main.statusBar().isVisible(),
            "auto": self.btn_auto.isChecked(),
        }
        self._presenting = True
        for d in docks:
            d.hide()
        main.menuBar().hide()
        main.statusBar().hide()
        main.showFullScreen()
        if self.overlay is None:
            self.overlay = PresentationOverlay(self, self.sky)
        self.overlay.show()
        self.overlay.raise_()
        if not self.btn_auto.isChecked():
            self.btn_auto.setChecked(True)
        if self.active and self.run.current is not None:
            self._fill_overlay(self.run.current)

    def exit_presentation(self) -> None:
        main = self.main
        st = self._saved_window
        self._presenting = False
        if self.overlay is not None:
            self.overlay.hide()
        if st.get("menu", True):
            main.menuBar().show()
        if st.get("status", True):
            main.statusBar().show()
        if not st.get("full", False):
            main.showNormal()
            if st.get("max"):
                main.showMaximized()
            elif st.get("geom") is not None:
                main.restoreGeometry(st["geom"])
        for d in st.get("docks", []):
            if d is not self or self.active:
                d.show()
        if not st.get("auto", False) and self.btn_auto.isChecked():
            self.btn_auto.setChecked(False)
        self.btn_present.blockSignals(True)
        self.btn_present.setChecked(False)
        self.btn_present.blockSignals(False)

    def _fill_overlay(self, cur) -> None:
        if self.overlay is None:
            return
        run = self.run
        self.overlay.set_content(cur.step.title, self._last_text,
                                 f"{run.index + 1} / {len(run.steps)}")


class PresentationOverlay(QFrame):
    """Painel inferior do modo apresentação, por cima do céu."""

    def __init__(self, player: TourPlayer, sky) -> None:
        super().__init__(sky)
        from PySide6.QtCore import QEvent

        self.player = player
        self.sky = sky
        self.setObjectName("tour_overlay")
        self.setStyleSheet(
            "#tour_overlay { background: rgba(8, 10, 18, 205); border-top: 1px solid "
            "rgba(255,255,255,40); } QLabel { color: #e8ecf5; background: transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 18, 48, 18)
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 26pt; font-weight: 600;")
        self.counter = QLabel()
        self.counter.setStyleSheet("font-size: 12pt; color: #9aa4b8;")
        top.addWidget(self.title, 1)
        top.addWidget(self.counter)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        self.text.setStyleSheet("font-size: 16pt;")
        hint = QLabel(self.tr("← →  passos   ·   Espaço  pausa   ·   F5  sai da "
                              "apresentação   ·   Esc  encerra o tour"))
        hint.setStyleSheet("font-size: 10pt; color: #7d879b;")
        lay.addLayout(top)
        lay.addWidget(self.text)
        lay.addWidget(hint)
        self._evt = QEvent.Resize
        sky.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.sky and event.type() == self._evt and self.isVisible():
            self._place()
        return False

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._place()

    def _place(self) -> None:
        w = self.sky.width()
        self.setFixedWidth(w)
        self.adjustSize()
        h = min(self.sizeHint().height(), int(self.sky.height() * 0.42))
        self.setGeometry(0, self.sky.height() - h, w, h)

    def set_content(self, title: str, markdown: str, counter: str) -> None:
        from PySide6.QtGui import QFont, QTextDocument

        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 17))       # o HTML gerado leva o tamanho
        doc.setMarkdown(markdown)
        body = doc.toHtml()
        self.title.setText(title)
        self.counter.setText(counter)
        self.text.setText(body)
        self._place()

