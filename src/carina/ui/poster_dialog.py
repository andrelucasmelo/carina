"""Pôster do céu de uma data (v0.22 T3) — Arquivo ▸ Pôster do céu.

O céu inteiro visto do zênite, num círculo, com título, data e hora, local e
uma frase — o "céu da noite em que você nasceu". Sai em PDF (A3 ou A4) ou
PNG, com tema escuro (noite) ou claro (papel). O céu é desenhado fora da tela
pelo ``render_frame`` (ADR-044) sem mexer na vista do usuário.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from PySide6.QtCore import QDate, QDateTime, QRectF, Qt, QTime
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDateTimeEdit, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout)

from ..core.localtime import from_local_naive, to_local

PAPERS_MM = {"A3": (297.0, 420.0), "A4": (210.0, 297.0)}
THEMES = {
    "dark": {"bg": QColor(8, 11, 22), "title": QColor(240, 236, 226),
             "text": QColor(185, 192, 210), "ring": QColor(222, 190, 120)},
    "light": {"bg": QColor(250, 248, 242), "title": QColor(26, 30, 42),
              "text": QColor(80, 88, 104), "ring": QColor(150, 120, 70)},
}


@dataclass
class PosterSpec:
    title: str = "O céu daquela noite"
    phrase: str = ""
    when_utc: dt.datetime | None = None
    place: str = ""
    paper: str = "A3"
    theme: str = "dark"


def render_poster(sky, spec: PosterSpec, dpi: int = 150) -> QImage:
    """Página do pôster como imagem (A3 a 150 dpi ≈ 1754 × 2480)."""
    from .night_report import sky_dome_image

    wmm, hmm = PAPERS_MM.get(spec.paper, PAPERS_MM["A3"])
    W, H = int(wmm / 25.4 * dpi), int(hmm / 25.4 * dpi)
    col = THEMES.get(spec.theme, THEMES["dark"])
    page = QImage(W, H, QImage.Format_RGB32)
    page.fill(col["bg"])
    side = int(W * 0.82)
    dome = sky_dome_image(sky, spec.when_utc, 900, theme=spec.theme, scale=side / 900, dso=False)
    p = QPainter(page)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    x0, y0 = (W - side) / 2, H * 0.07
    p.drawImage(QRectF(x0, y0, side, side), dome)
    p.setPen(QPen(col["ring"], max(2, W // 500)))
    p.drawEllipse(QRectF(x0, y0, side, side))
    def font(family: str, frac: float, italic: bool = False) -> QFont:
        f = QFont(family)
        f.setPixelSize(max(6, int(W * frac)))          # proporcional à largura do papel
        f.setItalic(italic)
        return f

    y = y0 + side + H * 0.04
    p.setPen(col["title"])
    p.setFont(font("Georgia", 0.045))
    p.drawText(QRectF(W * 0.06, y, W * 0.88, H * 0.07), Qt.AlignHCenter | Qt.TextWordWrap,
               spec.title)
    y += H * 0.07
    lt = to_local(spec.when_utc) if spec.when_utc else None
    line = (f"{lt:%d/%m/%Y} · {lt:%H:%M}" if lt else "") + (f" · {spec.place}" if spec.place else "")
    p.setPen(col["text"])
    p.setFont(font("Georgia", 0.019))
    p.drawText(QRectF(W * 0.06, y, W * 0.88, H * 0.04), Qt.AlignHCenter, line)
    if spec.phrase:
        y += H * 0.045
        p.setFont(font("Georgia", 0.021, italic=True))
        p.drawText(QRectF(W * 0.1, y, W * 0.8, H * 0.08), Qt.AlignHCenter | Qt.TextWordWrap,
                   spec.phrase)
    p.setFont(font("Segoe UI", 0.009))
    p.setPen(col["text"])
    p.drawText(QRectF(0, H - H * 0.035, W, H * 0.025), Qt.AlignHCenter,
               "Carina — o céu calculado para o local e o instante")
    p.end()
    return page


def save_poster(path: str, sky, spec: PosterSpec, dpi: int = 150) -> None:
    img = render_poster(sky, spec, dpi)
    if path.lower().endswith(".pdf"):
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageSize, QPdfWriter

        w = QPdfWriter(path)
        w.setPageSize(QPageSize(QPageSize.A3 if spec.paper == "A3" else QPageSize.A4))
        w.setPageMargins(QMarginsF(0, 0, 0, 0))
        w.setResolution(dpi)
        w.setTitle(spec.title)
        w.setCreator("Carina")
        p = QPainter(w)
        p.drawImage(QRectF(0, 0, w.width(), w.height()), img)
        p.end()
    else:
        img.save(path)


class PosterDialog(QDialog):
    def __init__(self, main, parent=None) -> None:
        super().__init__(parent or main)
        self.main = main
        self.setWindowTitle(self.tr("Pôster do céu"))
        self.resize(820, 700)
        form = QFormLayout()
        self.title = QLineEdit(self.tr("O céu daquela noite"))
        self.phrase = QLineEdit()
        self.phrase.setPlaceholderText(self.tr("Uma frase (opcional) — um nome, uma dedicatória…"))
        self.when = QDateTimeEdit()
        self.when.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.when.setCalendarPopup(True)
        self.when.setMinimumDate(QDate(1850, 1, 1))
        lt = to_local(main.engine.time.current_datetime())
        self.when.setDateTime(QDateTime(QDate(lt.year, lt.month, lt.day), QTime(lt.hour, lt.minute)))
        self.place = QLineEdit(main.settings.location().name)
        self.paper = QComboBox()
        self.paper.addItems(["A3", "A4"])
        self.theme = QComboBox()
        self.theme.addItem(self.tr("Escuro (noite)"), "dark")
        self.theme.addItem(self.tr("Claro (papel)"), "light")
        form.addRow(self.tr("Título:"), self.title)
        form.addRow(self.tr("Frase:"), self.phrase)
        form.addRow(self.tr("Data e hora:"), self.when)
        form.addRow(self.tr("Local (texto):"), self.place)
        form.addRow(self.tr("Papel:"), self.paper)
        form.addRow(self.tr("Tema:"), self.theme)
        note = QLabel(self.tr("O céu é calculado para o local escolhido no programa "
                              "(Local ▸ Localização); o campo acima é só o texto do pôster."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a93a5")
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(360)
        row = QHBoxLayout()
        b_prev = QPushButton(self.tr("Pré-visualizar"))
        b_prev.clicked.connect(self._preview)
        b_save = QPushButton(self.tr("Salvar (PDF ou PNG)…"))
        b_save.clicked.connect(self._save)
        close = QPushButton(self.tr("Fechar"))
        close.clicked.connect(self.accept)
        row.addWidget(b_prev)
        row.addWidget(b_save)
        row.addStretch(1)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(note)
        lay.addWidget(self.preview, 1)
        lay.addLayout(row)

    def spec(self) -> PosterSpec:
        d = self.when.dateTime().toPython()
        return PosterSpec(self.title.text().strip(), self.phrase.text().strip(),
                          from_local_naive(d).astimezone(dt.timezone.utc),
                          self.place.text().strip(), self.paper.currentText(),
                          self.theme.currentData())

    def _preview(self) -> None:
        img = render_poster(self.main.sky, self.spec(), dpi=50)
        pm = QPixmap.fromImage(img)
        self.preview.setPixmap(pm.scaled(self.preview.size(), Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))

    def _save(self) -> None:
        sp = self.spec()
        lt = to_local(sp.when_utc)
        fn, _f = QFileDialog.getSaveFileName(self, self.tr("Salvar pôster"),
                                             f"Céu de {lt:%Y-%m-%d}.pdf",
                                             "PDF (*.pdf);;PNG (*.png)")
        if fn:
            save_poster(fn, self.main.sky, sp)
            QMessageBox.information(self, "Carina", self.tr("Pôster salvo em\n{f}").format(f=fn))
