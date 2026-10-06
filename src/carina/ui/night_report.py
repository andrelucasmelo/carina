"""Relatório da noite e cartão compartilhável (v0.22 T2).

- **Relatório** (PDF A4): o céu inteiro na hora do meio das observações,
  o local, o Sol e a Lua da noite e a tabela das observações (hora, objeto,
  instrumento, condições, nota);
- **Cartão** (PNG 1080×1350, o formato vertical das redes sociais): o céu da
  noite em cima e a lista do que foi observado embaixo.

Os dois saem do diário (``core.report``); o céu é desenhado fora da tela pelo
mesmo ``render_frame`` das cartas (ADR-044), sem mexer na vista do usuário.
"""

from __future__ import annotations

import datetime as dt
import math

from PySide6.QtCore import QDate, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QTextBrowser, QVBoxLayout)

from ..core.localtime import to_local
from ..core.report import NightReport, build_report, nights_with_observations


def sky_dome_image(sky, when_utc, size: int = 900, theme: str = "dark",
                   fov_deg: float = 175.0, scale: float = 1.0, dso: bool = True) -> QImage:
    """O céu inteiro visto do zênite, com o norte para cima no hemisfério sul
    (o sul para cima no norte) — a mesma orientação do planisfério.
    ``dso=False`` tira os marcadores de céu profundo (pôster)."""
    from ..core.projection import Camera

    lat = sky.engine.topos.latitude.degrees
    az = math.pi if lat < 0 else 0.0        # câmera voltada para o polo visível
    opts = sky.render_options()
    opts.layers = dict(opts.layers)
    for k, v in (("const_lines", True), ("ground", False), ("below_horizon", False),
                 ("grid_altaz", False), ("dso_images", False), ("cardinals", True),
                 ("const_names", True), ("asterisms", False)):
        opts.layers[k] = v
    if not dso:
        opts.layers["dso"] = opts.layers["dso_names"] = False
    opts.const_label_mode = "pt"
    cam = Camera(az, math.radians(89.9), math.radians(fov_deg))
    img = sky.render_frame(size, size, options=opts, camera=cam, when_utc=when_utc,
                           scale=scale, theme=theme)
    # recorte circular (o horizonte)
    out = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, img.width(), img.height()))
    p.setClipPath(path)
    p.drawImage(0, 0, img)
    p.end()
    return out


def _fmt(when) -> str:
    return f"{to_local(when):%H:%M}" if when else "—"


def report_html(rep: NightReport) -> str:
    rows = "".join(
        f"<tr><td>{to_local(o['when_utc']):%H:%M}</td><td><b>{o['name']}</b></td>"
        f"<td>{o.get('instrument') or ''}</td>"
        f"<td>{'★' * int(o['rating']) if o.get('rating') else ''}</td>"
        f"<td>{o.get('note') or ''}</td></tr>" for o in rep.observations)
    return (f"<h2>Noite de {rep.night:%d/%m/%Y}</h2>"
            f"<p>{rep.location} · Sol se põe {_fmt(rep.sunset)} · noite escura "
            f"{_fmt(rep.astro_dusk)}–{_fmt(rep.astro_dawn)} · Lua {rep.moon_phase.lower()} "
            f"({rep.moon_illum:.0f}%)</p>"
            + (f"<table cellspacing=4><tr><th>Hora</th><th>Objeto</th><th>Instrumento</th>"
               f"<th>Nota</th><th>Anotações</th></tr>{rows}</table>" if rows
               else "<p><i>Nenhuma observação registrada nesta noite.</i></p>"))


def make_report_pdf(path, sky, rep: NightReport) -> None:
    """PDF A4 retrato: cabeçalho, o céu da noite e a tabela de observações."""
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

    w = QPdfWriter(str(path))
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageOrientation(QPageLayout.Portrait)
    w.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
    w.setResolution(150)
    w.setTitle(f"Relatório da noite de {rep.night:%d/%m/%Y}")
    w.setCreator("Carina")
    p = QPainter(w)
    W, H = w.width(), w.height()
    p.setPen(QColor(20, 24, 34))
    p.setFont(QFont("Segoe UI", 20, QFont.Bold))
    p.drawText(QRectF(0, 0, W, 80), Qt.AlignLeft | Qt.AlignTop,
               f"Relatório da noite — {rep.night:%d/%m/%Y}")
    p.setFont(QFont("Segoe UI", 10))
    p.setPen(QColor(80, 88, 104))
    p.drawText(QRectF(0, 70, W, 60), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
               f"{rep.location} · {rep.count} observação(ões) · Lua {rep.moon_phase.lower()} "
               f"({rep.moon_illum:.0f}%) · Sol se põe {_fmt(rep.sunset)} · noite escura "
               f"{_fmt(rep.astro_dusk)}–{_fmt(rep.astro_dawn)}")
    side = int(min(W, H * 0.5))
    dome = sky_dome_image(sky, rep.mid_utc, 760, theme="light", scale=side / 760)
    x0 = (W - side) // 2
    p.drawImage(QRectF(x0, 140, side, side), dome)
    p.setPen(QPen(QColor(120, 128, 144), 2))
    p.drawEllipse(QRectF(x0, 140, side, side))
    p.setFont(QFont("Segoe UI", 8))
    p.drawText(QRectF(0, 140 + side + 6, W, 30), Qt.AlignHCenter,
               f"O céu às {_fmt(rep.mid_utc)} — o horizonte é o círculo")
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(w)           # medidas na resolução do PDF
    doc.setDefaultFont(QFont("Segoe UI", 9))
    # papel branco: cores explícitas (a paleta do programa é escura)
    doc.setDefaultStyleSheet("body, td, th, p { color: #1a1e28; }")
    doc.setTextWidth(W)
    rows = "".join(
        f"<tr><td>{to_local(o['when_utc']):%H:%M}</td><td><b>{o['name']}</b></td>"
        f"<td>{o.get('instrument') or ''}</td>"
        f"<td>{'★' * int(o['rating']) if o.get('rating') else ''}</td>"
        f"<td>{o.get('note') or ''}</td></tr>" for o in rep.observations)
    doc.setHtml("<table width='100%' cellspacing=0 cellpadding=4 border=0>"
                "<tr style='background:#e8ecf3'><th align=left>Hora</th><th align=left>Objeto"
                "</th><th align=left>Instrumento</th><th align=left>Nota</th>"
                f"<th align=left>Anotações</th></tr>{rows}</table>" if rows else
                "<p><i>Nenhuma observação registrada nesta noite.</i></p>")
    top = 140 + side + 50
    p.translate(0, top)
    doc.drawContents(p, QRectF(0, 0, W, H - top))
    p.end()


def make_card_png(path, sky, rep: NightReport) -> QImage:
    """Cartão 1080×1350: o céu da noite e a lista do que foi visto."""
    W, H = 1080, 1350
    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor(9, 12, 24))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    dome = sky_dome_image(sky, rep.mid_utc, 760, theme="dark", scale=840 / 760)
    p.drawImage(QRectF(120, 70, 840, 840), dome)
    p.setPen(QPen(QColor(222, 190, 120, 160), 3))
    p.drawEllipse(QRectF(120, 70, 840, 840))
    p.setPen(QColor(235, 238, 248))
    p.setFont(QFont("Segoe UI", 34, QFont.Bold))
    p.drawText(QRectF(60, 935, W - 120, 60), Qt.AlignHCenter,
               f"Noite de {rep.night:%d/%m/%Y}")
    p.setPen(QColor(170, 180, 200))
    p.setFont(QFont("Segoe UI", 18))
    p.drawText(QRectF(60, 995, W - 120, 40), Qt.AlignHCenter,
               f"{rep.location} · Lua {rep.moon_phase.lower()}")
    names = rep.object_names()
    shown = names[:12]
    text = "  ·  ".join(shown) + (f"  ·  +{len(names) - len(shown)}" if len(names) > 12 else "")
    p.setPen(QColor(222, 190, 120))
    p.setFont(QFont("Segoe UI", 20, QFont.DemiBold))
    p.drawText(QRectF(80, 1050, W - 160, 210), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
               text or "Uma noite olhando para cima")
    p.setPen(QColor(110, 120, 140))
    p.setFont(QFont("Segoe UI", 14))
    p.drawText(QRectF(60, H - 60, W - 120, 40), Qt.AlignHCenter,
               f"{len(names)} objeto(s) observado(s) · Carina")
    p.end()
    img.save(str(path))
    return img


class NightReportDialog(QDialog):
    """Arquivo ▸ Relatório da noite."""

    def __init__(self, main, parent=None) -> None:
        super().__init__(parent or main)
        self.main = main
        self.setWindowTitle(self.tr("Relatório da noite"))
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Noite:")))
        self.cb = QComboBox()
        nights = nights_with_observations(main.userdata)
        from ..core.report import night_of

        tonight = night_of(main.engine.time.current_datetime())
        if tonight not in nights:
            nights.insert(0, tonight)
        for d in nights:
            self.cb.addItem(f"{d:%d/%m/%Y}", d)
        self.cb.currentIndexChanged.connect(self._fill)
        top.addWidget(self.cb)
        top.addStretch(1)
        lay.addLayout(top)
        self.view = QTextBrowser()
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        b_pdf = QPushButton(self.tr("Salvar relatório (PDF)…"))
        b_pdf.clicked.connect(self._save_pdf)
        b_card = QPushButton(self.tr("Salvar cartão para compartilhar (PNG)…"))
        b_card.clicked.connect(self._save_card)
        close = QPushButton(self.tr("Fechar"))
        close.clicked.connect(self.accept)
        row.addWidget(b_pdf)
        row.addWidget(b_card)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self._fill()

    def report(self) -> NightReport:
        return build_report(self.main.engine, self.main.userdata, self.cb.currentData(),
                            self.main.settings.location().name)

    def _fill(self, *_a) -> None:
        self.view.setHtml(report_html(self.report()))

    def _save_pdf(self) -> None:
        rep = self.report()
        fn, _f = QFileDialog.getSaveFileName(self, self.tr("Salvar relatório"),
                                             f"Noite {rep.night:%Y-%m-%d}.pdf", "PDF (*.pdf)")
        if fn:
            make_report_pdf(fn, self.main.sky, rep)
            QMessageBox.information(self, "Carina", self.tr("Relatório salvo em\n{f}").format(f=fn))

    def _save_card(self) -> None:
        rep = self.report()
        fn, _f = QFileDialog.getSaveFileName(self, self.tr("Salvar cartão"),
                                             f"Noite {rep.night:%Y-%m-%d}.png", "PNG (*.png)")
        if fn:
            make_card_png(fn, self.main.sky, rep)
            QMessageBox.information(self, "Carina", self.tr("Cartão salvo em\n{f}").format(f=fn))
