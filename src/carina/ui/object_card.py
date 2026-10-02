"""Ficha unificada do objeto (v0.15 T5).

Uma única ficha serve ao painel lateral, ao popup do botão direito e à
janela de detalhes. Seções:

Resumo
    Nome, tipo, constelação, magnitude, tamanho; imagem (céu profundo);
    a **pontuação de observabilidade** da noite com a explicação.
Hoje
    Nasce, culmina, se põe; janela útil acima da altitude mínima e do
    horizonte do quintal; melhor hora; a Lua; o instrumento sugerido; o
    mini-gráfico da noite.
Posição
    AR/Dec J2000 e da data, azimute/altitude, ângulo horário e massa de ar
    — atualizada ao vivo.
Descrição
    O que esperar ao olho, ao binóculo e ao telescópio; para estrelas,
    distância, tipo espectral e cor.
Diário
    Quantas vezes foi observado, a última nota, em que listas está.
Ações
    Centralizar, Seguir, Rastrear, Detalhes, Enquadrar, Minha lista,
    Observado, Copiar — emitidas por :attr:`ObjectCard.actionRequested`.

O cálculo da noite (visibilidade + pontuação) é feito uma vez por objeto e
noite e reaproveitado; a atualização por segundo só mexe na posição.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from ..catalogs import names
from ..core.formats import angle_deg, dec_dms, ra_hms
from .widgets.altitude_mini import AltitudeMini

LY_PER_PC = 3.26156
MUTED = "#8a93a5"

ACTIONS = [
    ("center", "Centralizar", "Centraliza o objeto no mapa"),
    ("follow", "Seguir", "A vista acompanha o objeto (F)"),
    ("track", "Rastrear", "Trajetória da noite em carta polar (Ctrl+R)"),
    ("details", "Detalhes", "Imagem grande e gráfico anual"),
    ("frame", "Enquadrar", "Simulador de campo com o objeto ao centro"),
    ("goto_best", "Melhor hora", "Leva o relógio à melhor hora desta noite"),
    ("list", "★ Minha lista", "Acrescenta à lista de observação"),
    ("observed", "✓ Observado", "Registra no diário"),
    ("copy", "Copiar", "Copia nome e coordenadas"),
]

SCORE_COLORS = [(75, "#2e9d5b"), (55, "#5f9e2e"), (35, "#b8902a"), (1, "#b8602a"),
                (0, "#6b6f7a")]


@dataclass
class CardContext:
    """O que a ficha precisa do aplicativo, sem depender da MainWindow."""

    engine: object
    stars: object
    dso: object
    const_names: dict = field(default_factory=dict)
    userdata: object = None
    bortle: Callable[[], int] = lambda: 5
    horizon: Callable[[], object] = lambda: None
    min_alt: Callable[[], float] = lambda: 20.0
    instrument: Callable[[], str] = lambda: "pequeno"


@dataclass
class Tonight:
    """Resultado cacheado da noite para um objeto."""

    key: tuple
    vis: object
    score: object
    instrument: str
    sb: float | None


def _row(label: str, value: str) -> str:
    return (f"<tr><td style='color:{MUTED}; padding-right:10px'>{label}</td>"
            f"<td>{value}</td></tr>")


def _hm(when) -> str:
    from ..core.localtime import to_local

    return to_local(when).strftime("%H:%M") if when else "—"


def _duration(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d}" if h else f"{m} min"


def _section(title: str) -> QLabel:
    lab = QLabel(f"<b>{title}</b>")
    lab.setStyleSheet("margin-top:6px; color:#c9d3e6;")
    return lab


def _html_label() -> QLabel:
    lab = QLabel()
    lab.setTextFormat(Qt.RichText)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lab.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    return lab


class ObjectCard(QScrollArea):
    """Ficha do objeto selecionado (painel, popup e janela de detalhes)."""

    actionRequested = Signal(str, object)     # (chave da ação, seleção)

    def __init__(self, ctx: CardContext, show_image: bool = True,
                 compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.show_image = show_image
        self.ref = None
        self.selection = None
        self._tonight: Tonight | None = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumWidth(290)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size:15pt; font-weight:600;")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.subtitle = _html_label()
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.hide()
        self.badge = QLabel()
        self.badge.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.explain = _html_label()
        self.today = _html_label()
        self.chart = AltitudeMini()
        self.position = _html_label()
        self.description = _html_label()
        self.journal = _html_label()

        lay.addWidget(self.title)
        lay.addWidget(self.subtitle)
        lay.addWidget(self.image)
        badge_row = QHBoxLayout()
        badge_row.addWidget(self.badge)
        badge_row.addStretch(1)
        lay.addLayout(badge_row)
        lay.addWidget(self.explain)
        self.sec_today = _section(self.tr("Hoje"))
        lay.addWidget(self.sec_today)
        lay.addWidget(self.today)
        lay.addWidget(self.chart)
        lay.addWidget(_section(self.tr("Posição agora")))
        lay.addWidget(self.position)
        self.sec_desc = _section(self.tr("O que esperar"))
        lay.addWidget(self.sec_desc)
        lay.addWidget(self.description)
        self.sec_journal = _section(self.tr("Seu diário"))
        lay.addWidget(self.sec_journal)
        lay.addWidget(self.journal)

        self.buttons: dict[str, QToolButton] = {}
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, (key, label, tip) in enumerate(ACTIONS):
            btn = QToolButton()
            btn.setText(self.tr(label))
            btn.setToolTip(self.tr(tip))
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setSizePolicy(btn.sizePolicy().horizontalPolicy(),
                              btn.sizePolicy().verticalPolicy())
            btn.setMinimumWidth(84)
            btn.clicked.connect(lambda _c=False, k=key: self._on_action(k))
            grid.addWidget(btn, i // 3, i % 3)
            self.buttons[key] = btn
        lay.addSpacing(6)
        lay.addLayout(grid)
        lay.addStretch(1)
        self.setWidget(body)
        self._placeholder()

    # -- estado vazio ----------------------------------------------------
    def _placeholder(self) -> None:
        self.title.setText(self.tr("Nenhum objeto"))
        self.subtitle.setText(f"<i>{self.tr('Clique num objeto do céu para ver a ficha.')}</i>")
        for w in (self.badge, self.explain, self.today, self.chart, self.position,
                  self.description, self.journal, self.sec_today, self.sec_desc,
                  self.sec_journal, self.image):
            w.hide()
        for b in self.buttons.values():
            b.setEnabled(False)

    # -- entrada ---------------------------------------------------------
    def set_selection(self, selection) -> None:
        from ..core.objects import ObjectRef

        self.selection = selection
        self.ref = (ObjectRef.resolve(selection, self.ctx.stars, self.ctx.dso)
                    if selection is not None else None)
        if self.ref is None:
            self._tonight = None
            self._placeholder()
            return
        for w in (self.badge, self.explain, self.today, self.chart, self.position,
                  self.description, self.sec_today, self.sec_desc):
            w.show()
        for b in self.buttons.values():
            b.setEnabled(True)
        self.buttons["details"].setEnabled(self.ref.is_fixed)
        self._fill_static()
        self.refresh(force=True)

    def invalidate(self) -> None:
        """Força recalcular a noite (troca de local, horizonte ou Bortle)."""
        self._tonight = None
        self.refresh(force=True)

    # -- propriedades do objeto ------------------------------------------
    def _props(self) -> tuple[float | None, float | None, float | None, str]:
        """(magnitude, eixo maior, eixo menor, classe) para a pontuação."""
        ref = self.ref
        if ref.kind == "dso":
            d = ref.data
            return d.get("mag"), d.get("maj"), d.get("min"), d.get("klass", "")
        if ref.kind == "star":
            return float(self.ctx.stars.mag[ref.key]), None, None, "STAR"
        t = self.ctx.engine.time.current()
        state = next((b for b in self.ctx.engine.bodies(t) if b.name == ref.key), None)
        mag = state.magnitude if state else 0.0
        klass = {"Lua": "MOON", "Sol": "SUN"}.get(ref.key, "PLANET")
        return mag, None, None, klass

    def _constellation(self) -> str:
        ref = self.ref
        code = ""
        if ref.kind == "dso":
            code = ref.data.get("con") or ""
        elif ref.kind == "star":
            code = self.ctx.stars.con.get(ref.key, "")
        if not code:
            return ""
        from ..core.observing import _constellation_name

        return _constellation_name(code, self.ctx.const_names)

    # -- partes fixas ------------------------------------------------------
    def _fill_static(self) -> None:
        from ..catalogs.dso import type_label
        from ..core.observing import (
            BINOCULAR_HINTS, SOLAR_HINTS, VISUAL_HINTS, _star_color_hint,
        )

        ref = self.ref
        self.title.setText(ref.name)
        mag, maj, mnr, klass = self._props()
        bits = []
        if ref.kind == "dso":
            bits.append(type_label(ref.data["type"]))
        elif ref.kind == "star":
            bits.append(self.tr("Estrela"))
        else:
            bits.append({"MOON": self.tr("Satélite natural"), "SUN": self.tr("Estrela")}
                        .get(klass, self.tr("Planeta")))
        con = self._constellation()
        if con:
            bits.append(con)
        if mag is not None:
            bits.append(self.tr("mag {m:.1f}").format(m=mag))
        if maj:
            size = f"{maj:.1f}′" + (f" × {mnr:.1f}′" if mnr else "")
            bits.append(size)
        sub = " · ".join(bits)
        if ref.kind == "dso":
            desig = " · ".join(f"Sh2-{i}" if c == "SH2" else f"{c} {i}"
                               for c, i in ref.data.get("designations", []))
            if desig and desig != ref.data["name"]:
                sub += f"<br><span style='color:{MUTED}'>{desig}</span>"
        elif ref.kind == "star":
            sub += (f"<br><span style='color:{MUTED}'>"
                    f"{self.ctx.stars.full_designation(ref.key)}</span>")
        self.subtitle.setText(sub)

        # imagem (só céu profundo)
        self.image.hide()
        if self.show_image and ref.kind == "dso":
            path = ref.image_path()
            if path is not None:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    self.image.setPixmap(pix.scaled(270, 270, Qt.KeepAspectRatio,
                                                    Qt.SmoothTransformation))
                    self.image.show()
            else:
                from ..catalogs import images

                d = ref.data
                images.request_image(d["name"], d["ra"], d["dec"], d.get("maj"))

        # o que esperar
        if ref.kind == "dso":
            text = (f"{VISUAL_HINTS.get(klass, VISUAL_HINTS['OTHER'])}<br>"
                    f"<span style='color:{MUTED}'>"
                    f"{BINOCULAR_HINTS.get(klass, BINOCULAR_HINTS['OTHER'])}</span>")
            if ref.data.get("notes"):
                text += f"<br><i>{ref.data['notes']}</i>"
        elif ref.kind == "star":
            st = self.ctx.stars
            i = ref.key
            text = _star_color_hint(float(st.ci[i]))
            extra = []
            dist = float(st.dist[i]) if hasattr(st, "dist") else 0.0
            if dist > 0:
                ly = dist * LY_PER_PC
                extra.append(self.tr("distância {ly} anos-luz").format(
                    ly=f"{ly:,.0f}".replace(",", ".") if ly >= 100
                    else f"{ly:.1f}".replace(".", ",")))
            spect = (str(st.spect[i]) if hasattr(st, "spect") else "").rstrip(".")
            if spect:
                extra.append(self.tr("tipo espectral {s}").format(s=spect))
            extra.append(f"B–V {float(st.ci[i]):+.2f}")
            text += f"<br><span style='color:{MUTED}'>{' · '.join(extra)}</span>"
        else:
            vis_txt, bino = SOLAR_HINTS.get(ref.key, ("", ""))
            text = vis_txt + (f"<br><span style='color:{MUTED}'>{bino}</span>"
                              if bino else "")
        self.description.setText(text)
        self._fill_journal()

    def _fill_journal(self) -> None:
        ud = self.ctx.userdata
        ref = self.ref
        if ud is None or ref is None:
            self.sec_journal.hide()
            self.journal.hide()
            return
        obs = ud.observations(ref.kind, ref.ident)
        lists = ud.lists_containing(ref.kind, ref.ident)
        parts = []
        if obs:
            from ..core.localtime import to_local

            last = obs[0]
            line = self.tr("Observado {n}× · último em {d}").format(
                n=len(obs), d=to_local(last["when_utc"]).strftime("%d/%m/%Y"))
            if last.get("note"):
                line += f": <i>{last['note']}</i>"
            parts.append(line)
        if lists:
            parts.append(self.tr("Nas listas: {l}").format(l=", ".join(lists)))
        if not parts:
            self.sec_journal.hide()
            self.journal.hide()
            return
        self.journal.setText("<br>".join(parts))
        self.sec_journal.show()
        self.journal.show()

    # -- noite -------------------------------------------------------------
    def _tonight_key(self, now_utc) -> tuple:
        from ..core.visibility import _noon_before

        eng = self.ctx.engine
        topo = getattr(eng, "topos", None)
        loc = (round(topo.latitude.degrees, 4), round(topo.longitude.degrees, 4)) \
            if topo is not None else None
        hz = self.ctx.horizon()
        return (self.ref.kind, self.ref.ident, _noon_before(now_utc), loc,
                tuple(hz.points) if hz is not None else (),
                self.ctx.bortle(), self.ctx.min_alt(), self.ctx.instrument())

    def compute_tonight(self, now_utc) -> Tonight:
        from ..core.observing import instrument_for
        from ..core.score import score_visibility, surface_brightness
        from ..core.visibility import visibility_of

        key = self._tonight_key(now_utc)
        if self._tonight is not None and self._tonight.key == key:
            return self._tonight
        mag, maj, mnr, klass = self._props()
        vis = visibility_of(self.ctx.engine, self.ref, now_utc,
                            min_alt=self.ctx.min_alt(), horizon=self.ctx.horizon())
        score = score_visibility(vis, mag, maj, mnr, klass, bortle=self.ctx.bortle(),
                                 instrument=self.ctx.instrument())
        if klass in ("PLANET", "MOON", "SUN", "STAR"):
            instrument = "olho" if (mag is not None and mag < 5.5) else "binoculo"
        else:
            instrument = instrument_for(mag, maj, klass, mnr)
        sb = surface_brightness(mag, maj, mnr) if self.ref.kind == "dso" else None
        self._tonight = Tonight(key, vis, score, instrument, sb)
        return self._tonight

    def _fill_tonight(self, tn: Tonight, now_utc) -> None:
        from ..core.observing import INSTRUMENT_LABEL

        vis, sc = tn.vis, tn.score
        color = next(c for limit, c in SCORE_COLORS if sc.total >= limit)
        self.badge.setText(f"  {sc.verdict} · {sc.total}  " if sc.total
                           else f"  {sc.verdict}  ")
        self.badge.setStyleSheet(
            f"background:{color}; color:white; border-radius:9px; padding:2px 6px;"
            " font-weight:600;")
        text = (", ".join(f.text for f in sc.factors if f.text) if sc.total
                else sc.reason)
        self.explain.setText(text[:1].upper() + text[1:])

        rows = []
        if vis.always_up:
            rise_set = self.tr("não se põe (circumpolar)")
        elif vis.never_up:
            rise_set = self.tr("não nasce nesta data")
        else:
            rise_set = f"{_hm(vis.rise_utc)} · {_hm(vis.set_utc)}"
        rows.append(_row(self.tr("Nasce · se põe"), rise_set))
        if not vis.never_up:
            rows.append(_row(self.tr("Culmina"), f"{_hm(vis.transit_utc)} a "
                             f"{vis.transit_alt:.0f}°"))
        if vis.observable:
            win = f"{_hm(vis.window_start)} – {_hm(vis.window_end)}"
            win += f" ({_duration(vis.window_minutes)})"
            if len(vis.segments) > 1:
                win += self.tr(" em {n} trechos").format(n=len(vis.segments))
            rows.append(_row(self.tr("Janela útil"), win))
            rows.append(_row(self.tr("Melhor hora"),
                             f"{_hm(vis.best_utc)} · alt {vis.best_alt:.0f}° · "
                             f"az {vis.best_az:.0f}°"))
        else:
            rows.append(_row(self.tr("Janela útil"), self.tr(
                "nenhuma acima de {a:.0f}° na noite escura").format(a=vis.min_alt)))
        if vis.blocked_minutes >= 10:
            rows.append(_row(self.tr("Horizonte"), self.tr(
                "{d} atrás do seu horizonte").format(d=_duration(vis.blocked_minutes))))
        illum = vis.grid.moon_illum
        moon = self.tr("{p:.0f}% iluminada").format(p=illum * 100)
        if vis.observable and vis.moon_alt_best > 0:
            moon += self.tr(", a {s:.0f}° na melhor hora").format(s=vis.moon_sep_best)
        elif vis.observable:
            moon += self.tr(", abaixo do horizonte na melhor hora")
        if self.ref.key != "Lua":
            rows.append(_row(self.tr("Lua"), moon))
        inst = INSTRUMENT_LABEL.get(tn.instrument, tn.instrument)
        if tn.sb is not None and tn.sb > 13.5:
            inst += self.tr(" · difuso ({s:.1f} mag/arcmin²)").format(s=tn.sb)
        rows.append(_row(self.tr("Instrumento"), inst))
        self.today.setText(f"<table>{''.join(rows)}</table>")
        self.chart.set_visibility(vis, self.ctx.horizon(), now_utc)

    # -- atualização -------------------------------------------------------
    def refresh(self, force: bool = False) -> None:
        """Posição ao vivo; a noite só é recalculada quando muda."""
        if self.ref is None:
            return
        eng = self.ctx.engine
        now = eng.time.current_datetime()
        try:
            key_changed = (self._tonight is None
                           or self._tonight.key != self._tonight_key(now))
            if force or key_changed:
                self._fill_tonight(self.compute_tonight(now), now)
            else:
                self.chart.set_now(now)
        except Exception as exc:  # noqa: BLE001 — a ficha não pode derrubar a UI
            self.today.setText(f"<i>{self.tr('Sem dados da noite')}: {exc}</i>")
        self.position.setText(self._position_html())

    def _position_html(self) -> str:
        from ..core.visibility import airmass

        eng = self.ctx.engine
        t = eng.time.current()
        m = eng.horizontal_matrix(t)
        ref = self.ref
        if ref.icrs is not None:
            icrs = np.asarray(ref.icrs, dtype=np.float64)
            h = m @ icrs
        else:
            state = next((b for b in eng.bodies(t) if b.name == ref.key), None)
            if state is None:
                return ""
            h = state.vec
            icrs = m.T @ h
        alt = math.asin(max(-1.0, min(1.0, float(h[2]))))
        az = math.atan2(float(h[1]), float(h[0])) % (2 * math.pi)
        ra0 = math.atan2(icrs[1], icrs[0]) % (2 * math.pi)
        dec0 = math.asin(max(-1.0, min(1.0, float(icrs[2]))))
        vd = np.asarray(t.M) @ icrs                      # equador e equinócio da data
        ra_d = math.atan2(vd[1], vd[0]) % (2 * math.pi)
        dec_d = math.asin(max(-1.0, min(1.0, float(vd[2]))))
        lst = (t.gast + eng.topos.longitude.degrees / 15.0) % 24.0
        ha = (lst - math.degrees(ra_d) / 15.0 + 12.0) % 24.0 - 12.0
        ha_txt = f"{'+' if ha >= 0 else '−'}{int(abs(ha))}h{int(abs(ha) * 60 % 60):02d}m"
        am = airmass(math.degrees(alt))
        rows = [
            _row("AR · Dec J2000", f"{ra_hms(ra0)} · {dec_dms(dec0)}"),
            _row(self.tr("AR · Dec da data"), f"{ra_hms(ra_d)} · {dec_dms(dec_d)}"),
            _row("Az · Alt", f"{angle_deg(az)} · {angle_deg(alt)}"),
            _row(self.tr("Ângulo horário"), ha_txt + (self.tr(" (já culminou)") if ha > 0
                                                     else self.tr(" (subindo)"))),
            _row(self.tr("Massa de ar"), f"{am:.2f}" if math.isfinite(am)
                 else self.tr("abaixo do horizonte")),
        ]
        if ref.kind == "body":
            state = next((b for b in eng.bodies(t) if b.name == ref.key), None)
            if state is not None:
                if ref.key == "Lua":
                    rows.append(_row(self.tr("Distância"),
                                     f"{state.distance_au * 149_597_870.7:,.0f} km"
                                     .replace(",", ".")))
                else:
                    rows.append(_row(self.tr("Distância"), f"{state.distance_au:.3f} UA"))
                if state.angular_radius > 0:
                    rows.append(_row(self.tr("Diâmetro"),
                                     f"{math.degrees(state.angular_radius) * 120:.1f}′"))
        return f"<table>{''.join(rows)}</table>"

    # -- ações -------------------------------------------------------------
    def copy_text(self) -> str:
        if self.ref is None:
            return ""
        ra_dec = self.ref.ra_dec
        if ra_dec is None:
            return self.ref.name
        return f"{self.ref.name} — AR {ra_hms(ra_dec[0])} Dec {dec_dms(ra_dec[1])} (J2000)"

    def _on_action(self, key: str) -> None:
        if key == "copy":
            QGuiApplication.clipboard().setText(self.copy_text())
        self.actionRequested.emit(key, self.selection)

    def summary(self) -> dict:
        """Dados da seção Hoje (para testes e para quem quiser reaproveitar)."""
        if self._tonight is None:
            return {}
        v, s = self._tonight.vis, self._tonight.score
        return {"rise": v.rise_utc, "transit": v.transit_utc, "set": v.set_utc,
                "best": v.best_utc, "window_minutes": v.window_minutes,
                "score": s.total, "verdict": s.verdict,
                "instrument": self._tonight.instrument}
