"""Janela de detalhes de um objeto: imagem grande e altitude ao longo do ano.

O gráfico mostra, a cada 10 dias, a altitude do objeto no meio da noite
astronômica (ou à meia-noite local, se não houver noite escura), junto com a
altitude máxima daquela data — é a leitura prática de "quando este alvo está
bem posicionado".
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget,
)

STEP_DAYS = 10


# Um dia solar tem 24 h; o mesmo intervalo vale 24 × 1,0027379 h siderais.
# É essa razão que converte um deslocamento em ângulo horário (sideral)
# no tempo de relógio correspondente.
SIDEREAL_RATIO = 1.00273790935


def _transit_time(engine, ra_hours: float, near: dt.datetime) -> dt.datetime:
    """Instante do trânsito (culminação) mais próximo de ``near``.

    O objeto culmina quando o tempo sideral local iguala sua ascensão
    reta. Calculamos a diferença entre os dois e a convertemos em tempo
    de relógio — resultado exato, sem varredura.
    """
    t = engine.ts.from_datetime(near)
    lon_hours = engine.topos.longitude.degrees / 15.0
    lst = (t.gast + lon_hours) % 24.0
    # diferença em horas siderais, trazida para (−12, +12]
    delta = (ra_hours - lst + 12.0) % 24.0 - 12.0
    return near + dt.timedelta(hours=delta / SIDEREAL_RATIO)


def yearly_altitude(engine, icrs_vec, start: dt.datetime,
                    step_days: int = STEP_DAYS):
    """Altitude do objeto ao longo de um ano.

    Retorna (datas, alt_meia_noite, alt_maxima) em graus.

    A altitude máxima da noite é obtida do INSTANTE DO TRÂNSITO, não de
    uma varredura por amostragem (B-021). A altitude tem um único máximo
    — a culminação — e amostrar de hora em hora quase nunca cai nele: o
    horário do trânsito desliza ~4 min por dia, então o erro variava de
    forma errática entre 0° e ~1,5°, produzindo quedas no meio de uma
    rampa que deveria ser suave. Quando a culminação acontece fora da
    janela da noite, o máximo está numa das bordas (pôr ou nascer do
    Sol), e é isso que se avalia.
    """
    from ..core.localtime import to_local
    from ..core.twilight import night_info

    icrs = np.asarray(icrs_vec, dtype=np.float64)
    ra_hours = (math.degrees(math.atan2(icrs[1], icrs[0])) / 15.0) % 24.0

    def altitude_at(when: dt.datetime) -> float:
        m = engine.horizontal_matrix(engine.ts.from_datetime(when))
        v = icrs @ m.T
        return math.degrees(math.asin(max(-1.0, min(1.0, float(v[2])))))

    dates: list[dt.date] = []
    alt_mid: list[float] = []
    alt_max: list[float] = []

    day = start
    for _ in range(int(365 / step_days) + 1):
        info = night_info(engine, day)
        # instante de referência: meio da noite astronômica, se existir
        if info.astro_dusk and info.astro_dawn:
            ref = info.astro_dusk + (info.astro_dawn - info.astro_dusk) / 2
        else:
            local = to_local(day).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + dt.timedelta(days=1)
            ref = local.astimezone(dt.timezone.utc)
        alt_mid.append(altitude_at(ref))

        # --- máxima da noite ---
        begin = info.sunset or ref - dt.timedelta(hours=6)
        end = info.sunrise or ref + dt.timedelta(hours=6)
        transit = _transit_time(engine, ra_hours, ref)
        if begin <= transit <= end:
            best = altitude_at(transit)      # culmina durante a noite
        else:
            # culmina de dia: o melhor da noite está numa das pontas
            best = max(altitude_at(begin), altitude_at(end))
        alt_max.append(best)

        dates.append(to_local(day).date())
        day = day + dt.timedelta(days=step_days)
    return dates, alt_mid, alt_max


class AltitudeChart(QWidget):
    """Gráfico de linha: altitude no meio da noite e máxima, por data."""

    def __init__(self, dates, alt_mid, alt_max, parent=None) -> None:
        super().__init__(parent)
        self.dates = dates
        self.alt_mid = alt_mid
        self.alt_max = alt_max
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        p.fillRect(rect, QColor(18, 20, 26))
        if not self.dates:
            return

        left, right, top, bottom = 44.0, 12.0, 26.0, 34.0
        plot = QRectF(
            rect.left() + left, rect.top() + top,
            max(40.0, rect.width() - left - right),
            max(40.0, rect.height() - top - bottom),
        )
        n = len(self.dates)

        def to_xy(i: int, alt: float) -> QPointF:
            fx = i / max(1, n - 1)
            fy = 1.0 - (max(-10.0, min(90.0, alt)) + 10.0) / 100.0
            return QPointF(plot.left() + fx * plot.width(),
                           plot.top() + fy * plot.height())

        # grade horizontal a cada 15°
        p.setFont(QFont("Segoe UI", 8))
        for alt in range(0, 91, 15):
            y = to_xy(0, alt).y()
            p.setPen(QPen(QColor(60, 70, 88), 1.0,
                          Qt.SolidLine if alt == 0 else Qt.DotLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(150, 160, 175))
            p.drawText(QRectF(rect.left() + 4, y - 9, left - 10, 18),
                       Qt.AlignRight | Qt.AlignVCenter, f"{alt}°")

        # meses no eixo x
        last_month = None
        for i, d in enumerate(self.dates):
            if d.month != last_month:
                last_month = d.month
                x = to_xy(i, 0).x()
                p.setPen(QPen(QColor(60, 70, 88), 1.0, Qt.DotLine))
                p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
                p.setPen(QColor(150, 160, 175))
                p.drawText(QRectF(x - 16, plot.bottom() + 4, 32, 16),
                           Qt.AlignCenter,
                           ["jan", "fev", "mar", "abr", "mai", "jun", "jul",
                            "ago", "set", "out", "nov", "dez"][d.month - 1])

        # curvas
        for values, color, width in (
            (self.alt_max, QColor(120, 200, 255), 1.6),
            (self.alt_mid, QColor(255, 190, 90), 2.4),
        ):
            p.setPen(QPen(color, width))
            pts = [to_xy(i, v) for i, v in enumerate(values)]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)

        # legenda
        p.setFont(QFont("Segoe UI", 8))
        items = [
            (QColor(255, 190, 90), "meio da noite astronômica"),
            (QColor(120, 200, 255), "altitude máxima da noite"),
        ]
        x = plot.left()
        for color, text in items:
            p.setPen(QPen(color, 2.4))
            p.drawLine(QPointF(x, rect.top() + 14), QPointF(x + 22, rect.top() + 14))
            p.setPen(QColor(200, 210, 225))
            p.drawText(QPointF(x + 28, rect.top() + 18), text)
            x += 190
        p.end()


class ObjectWindow(QMainWindow):
    """Janela de detalhes do objeto: imagem grande, ficha completa e o
    gráfico anual de altitude (amostrado a cada 10 dias)."""

    def __init__(self, title: str, html: str, image_path, dates, alt_mid,
                 alt_max, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Detalhes — {t}").format(t=title))
        self.resize(1000, 720)

        central = QWidget()
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        img_label = QLabel()
        if image_path is not None:
            pix = QPixmap(str(image_path))
            if not pix.isNull():
                img_label.setPixmap(
                    pix.scaled(430, 430, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
                )
        else:
            img_label.setText(self.tr("(sem imagem local)"))
            img_label.setMinimumSize(430, 200)
            img_label.setAlignment(Qt.AlignCenter)
        top.addWidget(img_label)

        info = QLabel(html)
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(info)
        top.addWidget(scroll, 1)
        layout.addLayout(top, 3)

        layout.addWidget(QLabel(self.tr(
            "<b>Altitude ao longo do ano</b> (amostragem a cada 10 dias)"
        )))
        layout.addWidget(AltitudeChart(dates, alt_mid, alt_max), 2)
        self.setCentralWidget(central)

        if dates:
            best = int(np.argmax(alt_mid))
            self.statusBar().showMessage(
                self.tr("Melhor época: {d} — {a:.0f}° no meio da noite")
                .format(d=dates[best].strftime("%d/%m"), a=alt_mid[best])
            )
