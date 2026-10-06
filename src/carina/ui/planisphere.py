"""Planisfério interativo (v0.22 T3) — Exibir ▸ Planisfério.

Como o planisfério de papel: um **disco de estrelas** em projeção polar em
volta do polo celeste visível (sul, para quem está no hemisfério sul), com
o **anel de datas** na borda, gira sob uma **janela fixa** que mostra o
horizonte do local, os pontos cardeais e o **anel de horas**. Alinhar a data
com a hora mostra o céu daquele momento.

Geometria: o desenho é feito em ângulo horário (HA = TSL − AR), então o que
é fixo no céu local — horizonte, zênite, meridiano — fica parado na tela e
as estrelas giram com o tempo sideral. O tique da data *d* no anel fica na
AR que culmina à meia-noite local de *d*; o tique da hora *T* do anel de
horas fica em HA = 15°·T (de meia-noite), e por isso os dois se alinham
exatamente quando a hora local é *T* naquela data.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
from PySide6.QtCore import QDate, QDateTime, QPointF, QRectF, Qt, QTime, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QDateTimeEdit, QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..core.localtime import from_local_naive, to_local

MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def eq_from_altaz(alt: np.ndarray, az: np.ndarray, lat: float) -> tuple[np.ndarray, np.ndarray]:
    """(HA, dec) em radianos a partir de (alt, az) em radianos; az do norte para leste."""
    sl, cl = math.sin(lat), math.cos(lat)
    dec = np.arcsin(sl * np.sin(alt) + cl * np.cos(alt) * np.cos(az))
    ha = np.arctan2(-np.sin(az) * np.cos(alt), cl * np.sin(alt) - sl * np.cos(alt) * np.cos(az))
    return ha, dec


class PlanisphereModel:
    """A parte geométrica (sem Qt): projeção, horizonte, anéis."""

    def __init__(self, latitude_deg: float, longitude_deg: float) -> None:
        self.lat = math.radians(latitude_deg)
        self.lon_deg = longitude_deg
        self.south = latitude_deg < 0
        # declinação-limite: estrelas além dela nunca nascem (com 3° de folga)
        self.dlim = math.radians(90.0 - abs(latitude_deg) + 3.0)
        self.sign = 1.0 if self.south else -1.0

    # -- projeção (coordenadas unitárias: raio 1 = borda do disco) --------------
    def radius(self, dec: np.ndarray) -> np.ndarray:
        d = np.asarray(dec, float)
        from_pole = d + math.pi / 2 if self.south else math.pi / 2 - d
        return from_pole / (self.dlim + math.pi / 2)

    def project(self, ha: np.ndarray, dec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        r = self.radius(dec)
        x = self.sign * r * np.sin(ha)
        y = -r * np.cos(ha)               # HA = 0 (meridiano) para cima
        return x, y

    def lst_hours(self, when_utc: dt.datetime) -> float:
        """Tempo sidéreo local (h), fórmula do GMST (precisão de segundos)."""
        jd = when_utc.timestamp() / 86400.0 + 2440587.5
        t = (jd - 2451545.0) / 36525.0
        gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
                + 0.000387933 * t * t) % 360.0
        return ((gmst + self.lon_deg) % 360.0) / 15.0

    def horizon(self, n: int = 361) -> tuple[np.ndarray, np.ndarray]:
        az = np.linspace(0, 2 * math.pi, n)
        ha, dec = eq_from_altaz(np.zeros(n), az, self.lat)
        return self.project(ha, dec)

    def altaz_point(self, alt_deg: float, az_deg: float):
        ha, dec = eq_from_altaz(np.array([math.radians(alt_deg)]),
                                np.array([math.radians(az_deg)]), self.lat)
        x, y = self.project(ha, dec)
        return float(x[0]), float(y[0])

    def midnight_ra_hours(self, day: dt.date) -> float:
        """AR (h) que passa no meridiano à meia-noite local entre ``day`` e o dia seguinte."""
        mid = from_local_naive(dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0)))
        return self.lst_hours(mid.astimezone(dt.timezone.utc))

    def date_angle(self, day: dt.date, lst_h: float) -> float:
        """Ângulo horário (rad) do tique da data no anel de datas, agora."""
        return math.radians((lst_h - self.midnight_ra_hours(day)) * 15.0)

    @staticmethod
    def hour_angle_of_clock(local_hour: float) -> float:
        """Ângulo horário (rad) do tique da hora local no anel de horas (fixo)."""
        return math.radians(local_hour * 15.0 * 1.0027379)


class PlanisphereWidget(QWidget):
    timeChanged = Signal(object)          # datetime UTC

    def __init__(self, stars, const_lines, const_info, latitude: float, longitude: float,
                 parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 560)
        self.model = PlanisphereModel(latitude, longitude)
        self.when = dt.datetime.now(dt.timezone.utc)
        n = stars.count_brighter_than(5.0)
        self.ra = np.asarray(stars.ra[:n], float)
        self.dec = np.asarray(stars.dec[:n], float)
        self.mag = np.asarray(stars.mag[:n], float)
        v = np.asarray(const_lines.verts, float)
        self.l_ra = np.arctan2(v[:, 1], v[:, 0])
        self.l_dec = np.arcsin(np.clip(v[:, 2], -1, 1))
        self.l_seg = np.asarray(const_lines.segments)
        self.c_info = [(c["id"], math.radians(c["ra"]), math.radians(c["dec"]))
                       for c in const_info]
        self._drag = None

    def set_time(self, when_utc: dt.datetime) -> None:
        self.when = when_utc
        self.update()
        self.timeChanged.emit(when_utc)

    # -- desenho -------------------------------------------------------------
    def _geom(self):
        side = min(self.width(), self.height()) - 20
        R = side / 2 * 0.86                       # disco de estrelas; resto: anéis
        return self.width() / 2, self.height() / 2, R

    def paintEvent(self, _e) -> None:
        from ..catalogs.constnames import CONSTELLATIONS

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(14, 17, 26))
        cx, cy, R = self._geom()
        m = self.model
        lst = m.lst_hours(self.when)

        def to_px(x, y):
            return cx + x * R, cy + y * R

        # disco
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 20, 44))
        p.drawEllipse(QPointF(cx, cy), R, R)
        # linhas das constelações
        ha_l = np.radians(lst * 15.0) - self.l_ra
        lx, ly = m.project(ha_l, self.l_dec)
        rl = m.radius(self.l_dec)
        p.setPen(QPen(QColor(80, 110, 170, 170), 1))
        for a, b in self.l_seg:
            if rl[a] <= 1.0 and rl[b] <= 1.0:
                xa, ya = to_px(lx[a], ly[a])
                xb, yb = to_px(lx[b], ly[b])
                p.drawLine(QPointF(xa, ya), QPointF(xb, yb))
        # estrelas
        ha_s = np.radians(lst * 15.0) - self.ra
        sx, sy = m.project(ha_s, self.dec)
        rs = m.radius(self.dec)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 240, 255))
        for x, y, r, mg in zip(sx, sy, rs, self.mag):
            if r <= 1.0:
                size = max(0.8, 3.6 - 0.6 * mg)
                px, py = to_px(x, y)
                p.drawEllipse(QPointF(px, py), size, size)
        # nomes das constelações
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor(130, 160, 210))
        for cid, ra, dec in self.c_info:
            if m.radius(dec) > 0.97:
                continue
            x, y = m.project(math.radians(lst * 15.0) - ra, dec)
            px, py = to_px(float(x), float(y))
            name = CONSTELLATIONS.get(cid, (cid, cid))[1]
            p.drawText(QRectF(px - 50, py - 7, 100, 14), Qt.AlignCenter, name)
        # anel de datas (gira com as estrelas)
        p.setPen(QPen(QColor(150, 160, 190), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R * 1.07, R * 1.07)
        year = to_local(self.when).year
        p.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        for month in range(1, 13):
            for day in (1, 10, 20):
                d = dt.date(year, month, day)
                ang = m.date_angle(d, lst)
                x, y = m.sign * math.sin(ang), -math.cos(ang)
                r0, r1 = (1.0, 1.07) if day == 1 else (1.03, 1.07)
                p.drawLine(QPointF(cx + x * R * r0, cy + y * R * r0),
                           QPointF(cx + x * R * r1, cy + y * R * r1))
                if day == 1:
                    ang2 = m.date_angle(dt.date(year, month, 15), lst)
                    x2, y2 = m.sign * math.sin(ang2), -math.cos(ang2)
                    p.drawText(QRectF(cx + x2 * R * 1.035 - 16, cy + y2 * R * 1.035 - 7, 32, 14),
                               Qt.AlignCenter, MONTHS[month - 1])
        # janela do horizonte (fixa): escurece o que está abaixo dele
        hx, hy = m.horizon()
        win = QPainterPath()
        win.moveTo(*to_px(hx[0], hy[0]))
        for x, y in zip(hx[1:], hy[1:]):
            win.lineTo(*to_px(x, y))
        win.closeSubpath()
        outer = QPainterPath()
        outer.addEllipse(QPointF(cx, cy), R * 1.0, R * 1.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(4, 6, 12, 200))
        p.drawPath(outer.subtracted(win))
        p.setPen(QPen(QColor(230, 190, 110), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(win)
        # zênite e pontos cardeais
        zx, zy = m.altaz_point(90, 0)
        p.setPen(QPen(QColor(230, 190, 110), 1))
        zp = QPointF(*to_px(zx, zy))
        p.drawLine(zp + QPointF(-5, 0), zp + QPointF(5, 0))
        p.drawLine(zp + QPointF(0, -5), zp + QPointF(0, 5))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        for label, az in (("N", 0), ("L", 90), ("S", 180), ("O", 270)):
            x, y = m.altaz_point(-4, az)
            px, py = to_px(x, y)
            p.drawText(QRectF(px - 10, py - 9, 20, 18), Qt.AlignCenter, label)
        # anel de horas (fixo)
        p.setPen(QPen(QColor(200, 205, 220), 1))
        p.drawEllipse(QPointF(cx, cy), R * 1.11, R * 1.11)
        p.setFont(QFont("Segoe UI", 8))
        for hh in range(24):
            ang = m.hour_angle_of_clock(hh)
            x, y = m.sign * math.sin(ang), -math.cos(ang)
            p.drawLine(QPointF(cx + x * R * 1.11, cy + y * R * 1.11),
                       QPointF(cx + x * R * 1.14, cy + y * R * 1.14))
            p.drawText(QRectF(cx + x * R * 1.18 - 14, cy + y * R * 1.18 - 7, 28, 14),
                       Qt.AlignCenter, f"{hh}h")
        # o "agora": a data de hoje no anel de datas aponta para a hora atual
        lt = to_local(self.when)
        ang = m.date_angle(lt.date() if lt.hour >= 12 else lt.date() - dt.timedelta(days=1),
                           lst)
        x, y = m.sign * math.sin(ang), -math.cos(ang)
        p.setPen(QPen(QColor(255, 120, 90), 2))
        p.drawLine(QPointF(cx + x * R * 1.0, cy + y * R * 1.0),
                   QPointF(cx + x * R * 1.16, cy + y * R * 1.16))
        p.end()

    # -- arrastar gira o disco (muda a hora) ------------------------------------
    def mousePressEvent(self, e) -> None:
        cx, cy, _R = self._geom()
        pos = e.position()
        self._drag = (math.atan2(pos.x() - cx, -(pos.y() - cy)), self.when)

    def mouseMoveEvent(self, e) -> None:
        if self._drag is None:
            return
        cx, cy, _R = self._geom()
        pos = e.position()
        a1 = math.atan2(pos.x() - cx, -(pos.y() - cy))
        a0, t0 = self._drag
        dang = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        hours = self.model.sign * math.degrees(dang) / 15.0 / 1.0027379
        self.set_time(t0 + dt.timedelta(hours=hours))

    def mouseReleaseEvent(self, _e) -> None:
        self._drag = None


class PlanisphereDialog(QDialog):
    """Janela do planisfério com data e hora editáveis."""

    def __init__(self, main, parent=None) -> None:
        super().__init__(parent or main)
        self.main = main
        self.setWindowTitle(self.tr("Planisfério"))
        self.resize(760, 820)
        loc = main.settings.location()
        self.widget = PlanisphereWidget(main.star_catalog, main.sky.const_lines,
                                        main.sky.const_info, loc.latitude, loc.longitude)
        lay = QVBoxLayout(self)
        lay.addWidget(self.widget, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Data e hora:")))
        self.edit = QDateTimeEdit()
        self.edit.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.edit.setCalendarPopup(True)
        self.edit.dateTimeChanged.connect(self._edited)
        row.addWidget(self.edit)
        now = QPushButton(self.tr("Agora"))
        now.clicked.connect(lambda: self.set_time(dt.datetime.now(dt.timezone.utc)))
        row.addWidget(now)
        sky_btn = QPushButton(self.tr("Levar o céu a este instante"))
        sky_btn.clicked.connect(self._to_sky)
        row.addWidget(sky_btn)
        row.addStretch(1)
        hint = QLabel(self.tr("Arraste o disco para girar o céu; o tique vermelho marca a "
                              "data no anel de datas, alinhada com a hora."))
        hint.setStyleSheet("color:#8a93a5")
        hint.setWordWrap(True)
        lay.addLayout(row)
        lay.addWidget(hint)
        self.widget.timeChanged.connect(self._from_widget)
        self.set_time(main.engine.time.current_datetime())

    def set_time(self, when_utc: dt.datetime) -> None:
        self.widget.set_time(when_utc)

    def _from_widget(self, when_utc) -> None:
        lt = to_local(when_utc)
        self.edit.blockSignals(True)
        self.edit.setDateTime(QDateTime(QDate(lt.year, lt.month, lt.day),
                                        QTime(lt.hour, lt.minute)))
        self.edit.blockSignals(False)

    def _edited(self, qdt) -> None:
        d = qdt.toPython()
        self.widget.when = from_local_naive(d).astimezone(dt.timezone.utc)
        self.widget.update()

    def _to_sky(self) -> None:
        self.main.engine.time.set_fixed(self.widget.when)
