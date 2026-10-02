"""Editor do horizonte do quintal (v0.15 T4).

Um painel panorâmico (azimute 0–360° na horizontal, altitude 0–60° na
vertical) mostra o céu deste instante — estrelas brilhantes, planetas,
Lua — e, se houver objeto selecionado, a trajetória dele durante a noite.
Por cima, o perfil do horizonte: clique num lugar vazio para acrescentar
um ponto, arraste um ponto para movê-lo, clique com o botão direito para
removê-lo. Assim fica fácil "desenhar" o prédio olhando onde as estrelas
somem atrás dele.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..core.horizon import PRESETS, HorizonProfile

ALT_MAX = 60.0
CARDINALS = [(0, "N"), (45, "NE"), (90, "L"), (135, "SE"), (180, "S"),
             (225, "SO"), (270, "O"), (315, "NO"), (360, "N")]
PICK_PX = 9.0


class HorizonEditor(QWidget):
    """Painel panorâmico editável do perfil do horizonte."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(720, 260)
        self.setMouseTracking(True)
        self.profile = HorizonProfile()
        self.sky_points: list[tuple[float, float, float, str]] = []  # az, alt, mag, nome
        self.track: list[tuple[float, float]] = []                    # az, alt
        self.track_label = ""
        self._drag: int | None = None
        self._hover: int | None = None
        self.margin_l, self.margin_r, self.margin_t, self.margin_b = 36, 12, 12, 26

    # -- geometria -----------------------------------------------------
    def _plot(self) -> QRectF:
        return QRectF(self.margin_l, self.margin_t,
                      self.width() - self.margin_l - self.margin_r,
                      self.height() - self.margin_t - self.margin_b)

    def to_px(self, az: float, alt: float) -> QPointF:
        r = self._plot()
        x = r.left() + (az % 360.0 if az != 360.0 else 360.0) / 360.0 * r.width()
        y = r.bottom() - max(-2.0, min(ALT_MAX, alt)) / ALT_MAX * r.height()
        return QPointF(x, y)

    def from_px(self, x: float, y: float) -> tuple[float, float]:
        r = self._plot()
        az = (x - r.left()) / r.width() * 360.0
        alt = (r.bottom() - y) / r.height() * ALT_MAX
        return max(0.0, min(359.9, az)), max(0.0, min(ALT_MAX, alt))

    def _point_at(self, x: float, y: float) -> int | None:
        best, best_d = None, PICK_PX
        for i, (az, alt) in enumerate(self.profile.points):
            p = self.to_px(az, alt)
            d = math.hypot(p.x() - x, p.y() - y)
            if d < best_d:
                best, best_d = i, d
        return best

    # -- dados ---------------------------------------------------------
    def set_profile(self, profile: HorizonProfile) -> None:
        self.profile = HorizonProfile(list(profile.points), profile.name)
        self.update()

    def set_sky(self, points, track=None, track_label: str = "") -> None:
        self.sky_points = list(points)
        self.track = list(track or [])
        self.track_label = track_label
        self.update()

    # -- desenho ---------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._plot()
        p.fillRect(self.rect(), QColor(10, 14, 26))
        p.fillRect(r, QColor(14, 22, 44))

        # grade: 30° em azimute, 10° em altitude
        p.setPen(QPen(QColor(60, 75, 110), 1, Qt.DotLine))
        for az in range(30, 360, 30):
            x = self.to_px(az, 0).x()
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1))
        p.setFont(small)
        for alt in range(10, int(ALT_MAX) + 1, 10):
            y = self.to_px(0, alt).y()
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor(150, 165, 200))
            p.drawText(QRectF(0, y - 8, self.margin_l - 4, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"{alt}°")
            p.setPen(QPen(QColor(60, 75, 110), 1, Qt.DotLine))
        p.setPen(QColor(190, 200, 225))
        for az, name in CARDINALS:
            x = self.to_px(az, 0).x()
            p.drawText(QRectF(x - 20, r.bottom() + 4, 40, 18), Qt.AlignCenter, name)

        # céu deste instante
        for az, alt, mag, name in self.sky_points:
            if alt < -1 or alt > ALT_MAX + 1:
                continue
            pt = self.to_px(az, alt)
            size = max(1.5, 4.5 - 0.7 * mag)
            col = QColor(255, 220, 150) if name and mag < -0.5 else QColor(230, 235, 255)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(pt, size / 2 + 0.5, size / 2 + 0.5)
            if name:
                p.setPen(QColor(200, 210, 235))
                p.drawText(pt + QPointF(5, -4), name)

        # trajetória do objeto selecionado esta noite
        if self.track:
            p.setPen(QPen(QColor(110, 210, 255), 1.6, Qt.DashLine))
            prev = None
            p.save()
            p.setClipRect(r)                 # acima de 60° fica fora do painel
            for az, alt in self.track:
                cur = self.to_px(az, min(alt, ALT_MAX + 30.0))
                if (prev is not None and abs(prev[0] - az) < 180 and alt >= 0
                        and min(prev[2], alt) <= ALT_MAX):
                    p.drawLine(prev[1], cur)
                prev = (az, cur, alt)
            p.restore()
            visible = [t for t in self.track if 2.0 <= t[1] <= ALT_MAX - 6.0]
            if self.track_label and visible:
                az, alt = max(visible, key=lambda t: t[1])
                p.setPen(QColor(110, 210, 255))
                p.drawText(self.to_px(az, alt) + QPointF(8, 4), self.track_label)

        # perfil: polígono preenchido até o chão
        poly = QPolygonF()
        poly.append(self.to_px(0, 0))
        for az in np.arange(0.0, 360.5, 0.5):
            poly.append(self.to_px(float(az), float(self.profile.altitude_at(az))))
        poly.append(self.to_px(360.0, 0))
        path = QPainterPath()
        path.addPolygon(poly)
        p.setPen(QPen(QColor(205, 160, 110), 1.6))
        p.setBrush(QColor(60, 44, 30, 215))
        p.drawPath(path)

        for i, (az, alt) in enumerate(self.profile.points):
            pt = self.to_px(az, alt)
            hot = i in (self._drag, self._hover)
            p.setPen(QPen(QColor(255, 230, 190), 1.2))
            p.setBrush(QColor(240, 170, 90) if hot else QColor(150, 105, 60))
            p.drawEllipse(pt, 5.5 if hot else 4.5, 5.5 if hot else 4.5)
        if self._hover is not None or self._drag is not None:
            az, alt = self.profile.points[self._drag if self._drag is not None
                                          else self._hover]
            p.setPen(QColor(255, 235, 200))
            p.drawText(QRectF(r.left() + 6, r.top() + 4, 220, 18), Qt.AlignLeft,
                       f"Az {az:.0f}° · Alt {alt:.0f}°")
        p.end()

    # -- interação -------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        idx = self._point_at(x, y)
        if event.button() == Qt.RightButton:
            if idx is not None:
                pts = list(self.profile.points)
                pts.pop(idx)
                self.profile.set_points(pts)
                self._hover = None
                self.changed.emit()
                self.update()
            return
        if event.button() != Qt.LeftButton:
            return
        if idx is None:
            az, alt = self.from_px(x, y)
            pts = list(self.profile.points) + [(round(az, 1), round(alt, 1))]
            self.profile.set_points(pts)
            idx = self._point_at(x, y)
            self.changed.emit()
        self._drag = idx
        self.update()

    def mouseMoveEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        if self._drag is not None:
            az, alt = self.from_px(x, y)
            pts = list(self.profile.points)
            pts[self._drag] = (round(az, 1), round(alt, 1))
            # mantém o índice do ponto arrastado depois da reordenação
            self.profile.set_points(pts)
            self._drag = min(range(len(self.profile.points)),
                             key=lambda i: abs(self.profile.points[i][0] - round(az, 1))
                             + abs(self.profile.points[i][1] - round(alt, 1)))
            self.changed.emit()
            self.update()
            return
        hover = self._point_at(x, y)
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.SizeAllCursor if hover is not None else Qt.CrossCursor)
            self.update()

    def mouseReleaseEvent(self, _event) -> None:
        self._drag = None
        self.update()


class HorizonDialog(QDialog):
    """Diálogo Local ▸ Horizonte do quintal…"""

    profileApplied = Signal(object)        # HorizonProfile | None

    def __init__(self, engine, stars, userdata, location_name: str = "",
                 selection_ref=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Horizonte do quintal"))
        self.engine, self.stars, self.ud = engine, stars, userdata
        self.location_name = location_name
        self.selection_ref = selection_ref

        intro = QLabel(self.tr(
            "Desenhe a silhueta de prédios, muros e árvores. Clique para "
            "acrescentar um ponto, arraste para mover, botão direito remove. "
            "As estrelas mostram o céu deste instante."))
        intro.setWordWrap(True)

        self.saved = QComboBox()
        self.name = QLineEdit()
        self.name.setPlaceholderText(self.tr("Nome do perfil"))
        self.preset = QComboBox()
        self.preset.addItem(self.tr("Modelo…"))
        self.preset.addItems(list(PRESETS))
        btn_import = QPushButton(self.tr("Importar CSV…"))
        btn_export = QPushButton(self.tr("Exportar CSV…"))
        btn_clear = QPushButton(self.tr("Limpar"))
        self.btn_delete = QPushButton(self.tr("Excluir perfil"))

        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Perfil:")))
        top.addWidget(self.saved, 1)
        top.addWidget(self.name, 1)
        top.addWidget(self.preset)
        tools = QHBoxLayout()
        for b in (btn_import, btn_export, btn_clear, self.btn_delete):
            tools.addWidget(b)
        tools.addStretch(1)

        self.editor = HorizonEditor()
        self.info = QLabel()
        self.active = QCheckBox(self.tr(
            "Usar este horizonte no céu, na pontuação e no planejamento"))
        self.active.setChecked(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Save).setText(self.tr("Salvar"))
        buttons.button(QDialogButtonBox.Close).setText(self.tr("Fechar"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addLayout(top)
        lay.addWidget(self.editor, 1)
        lay.addWidget(self.info)
        lay.addLayout(tools)
        lay.addWidget(self.active)
        lay.addWidget(buttons)
        self.resize(960, 600)

        self.saved.currentIndexChanged.connect(self._load_saved)
        self.preset.activated.connect(self._apply_preset)
        btn_import.clicked.connect(self._import_csv)
        btn_export.clicked.connect(self._export_csv)
        btn_clear.clicked.connect(
            lambda: self._set_profile(HorizonProfile([], self.name.text())))
        self.btn_delete.clicked.connect(self._delete)
        self.editor.changed.connect(self._update_info)

        self._fill_sky()
        self._refresh_saved()

    # -- conteúdo ------------------------------------------------------
    def _fill_sky(self) -> None:
        t = self.engine.time.current()
        m = self.engine.horizontal_matrix(t)
        pts = []
        n = self.stars.count_brighter_than(4.2)
        h = self.stars.xyz[:n].astype(np.float64) @ m.T
        alt = np.degrees(np.arcsin(np.clip(h[:, 2], -1, 1)))
        az = np.degrees(np.arctan2(h[:, 1], h[:, 0])) % 360.0
        for i in np.nonzero(alt > -1.0)[0]:
            mag = float(self.stars.mag[i])
            name = self.stars.proper.get(int(i), "") if mag < 1.3 else ""
            pts.append((float(az[i]), float(alt[i]), mag, name))
        for b in self.engine.bodies(t):
            if b.name == "Sol":
                continue
            pts.append((math.degrees(b.az) % 360.0, math.degrees(b.alt),
                        min(b.magnitude, -1.0), b.name))
        track, label = [], ""
        if self.selection_ref is not None:
            from ..core.visibility import visibility_of

            vis = visibility_of(self.engine, self.selection_ref,
                                self.engine.time.current_datetime(), min_alt=0.0)
            dark = vis.grid.sun_alt < -6.0
            track = [(float(a), float(h_)) for a, h_, d in
                     zip(vis.azs, vis.alts, dark) if d]
            label = self.selection_ref.name
        self.editor.set_sky(pts, track, label)

    def _refresh_saved(self, select: str | None = None) -> None:
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem(self.tr("(novo perfil)"), None)
        active_name = None
        for h in self.ud.horizons():
            self.saved.addItem(h["name"] + (" ✓" if h["active"] else ""), h["name"])
            if h["active"]:
                active_name = h["name"]
        self.saved.blockSignals(False)
        target = select or active_name
        idx = self.saved.findData(target) if target else 0
        self.saved.setCurrentIndex(max(0, idx))
        self._load_saved()

    def _load_saved(self) -> None:
        name = self.saved.currentData()
        if name:
            self._set_profile(self.ud.horizon(name))
            self.active.setChecked(any(h["active"] for h in self.ud.horizons()
                                       if h["name"] == name))
        else:
            self._set_profile(HorizonProfile([], self.tr("Meu quintal")))
        self.btn_delete.setEnabled(bool(name))

    def _set_profile(self, prof: HorizonProfile) -> None:
        self.name.setText(prof.name)
        self.editor.set_profile(prof)
        self._update_info()

    def _update_info(self) -> None:
        prof = self.editor.profile
        if prof.is_flat:
            self.info.setText(self.tr("Horizonte plano — nada bloqueado."))
            return
        alt = prof.altitude_at(np.arange(0.0, 360.0, 1.0))
        self.info.setText(self.tr(
            "{n} pontos · altura máxima {m:.0f}° · {f:.0f}% da faixa de 0° a 30° "
            "bloqueada").format(n=len(prof.points), m=float(alt.max()),
                                f=float(np.clip(alt, 0, 30).mean() / 30 * 100)))

    # -- ações -----------------------------------------------------------
    def _apply_preset(self, index: int) -> None:
        if index <= 0:
            return
        prof = PRESETS[self.preset.itemText(index)]()
        prof.name = self.name.text() or prof.name
        self.editor.set_profile(prof)
        self._update_info()
        self.preset.setCurrentIndex(0)

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Importar horizonte"), "", "CSV (*.csv *.txt)")
        if not path:
            return
        prof = HorizonProfile.from_csv(Path(path).read_text(encoding="utf-8-sig"),
                                       Path(path).stem)
        if not prof.points:
            QMessageBox.warning(self, self.tr("Horizonte"), self.tr(
                "Nenhum par azimute;altitude encontrado no arquivo."))
            return
        self._set_profile(prof)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar horizonte"),
            f"{self.name.text() or 'horizonte'}.csv", "CSV (*.csv)")
        if path:
            Path(path).write_text(self.editor.profile.to_csv(), encoding="utf-8")

    def current_profile(self) -> HorizonProfile:
        prof = self.editor.profile
        return HorizonProfile(list(prof.points),
                              self.name.text().strip() or self.tr("Meu quintal"))

    def _save(self) -> None:
        prof = self.current_profile()
        self.ud.save_horizon(prof, self.location_name, active=self.active.isChecked())
        if not self.active.isChecked():
            current = self.ud.active_horizon()
            if current is not None and current.name == prof.name:
                self.ud.set_active_horizon(None)
        self.profileApplied.emit(self.ud.active_horizon())
        self._refresh_saved(prof.name)

    def _delete(self) -> None:
        name = self.saved.currentData()
        if not name:
            return
        if QMessageBox.question(self, self.tr("Horizonte"), self.tr(
                "Excluir o perfil \"{n}\"?").format(n=name)) != QMessageBox.Yes:
            return
        self.ud.delete_horizon(name)
        self.profileApplied.emit(self.ud.active_horizon())
        self._refresh_saved()
