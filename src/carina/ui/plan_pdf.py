"""PDF de campo do roteiro de observação.

Duas seções:

1. um **checklist compacto** (uma linha por objeto, com caixa para marcar);
2. um **cartão por objeto** com as instruções completas e uma **carta de
   localização** desenhada no estilo do modo de impressão.

O texto é sempre MEDIDO antes de desenhado (``boundingRect``) e o cursor
vertical avança pela altura real — foi assim que o problema de linhas
sobrepostas da primeira versão foi eliminado.

Extraído da antiga janela de maratonas na v0.15 (a janela de planejamento
v2 e a exportação pela linha de comando usam a mesma função).
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from ..core.localtime import to_local
from ..core.observing import INSTRUMENT_LABEL


def _hm(value: dt.datetime | None) -> str:
    return to_local(value).strftime("%H:%M") if value else "—"


def write_plan_pdf(path: str, plan, stars=None, const_lines=None,
                   progress=None) -> bool:
    """Desenha o PDF. Retorna False se o usuário cancelou no meio."""
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageOrientation(QPageLayout.Portrait)
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
    writer.setResolution(300)
    writer.setTitle(plan.title)

    p = QPainter(writer)
    width = writer.width()
    height = writer.height()
    margin = 30
    y = margin

    f_title = QFont("Segoe UI", 18, QFont.Bold)
    f_head = QFont("Segoe UI", 12, QFont.Bold)
    f_meta = QFont("Segoe UI", 9)
    f_body = QFont("Segoe UI", 9)
    f_row = QFont("Segoe UI", 8)

    def ensure(space: float) -> None:
        """Quebra de página quando o próximo bloco não couber inteiro."""
        nonlocal y
        if y + space > height - margin:
            writer.newPage()
            y = margin

    def paragraph(text: str, x: float, wrap_w: float,
                  font: QFont, advance: bool = True) -> float:
        """Mede, desenha e devolve a ALTURA REAL do parágrafo.

        Medir antes de desenhar (e avançar o cursor pela altura medida)
        é o que garante que nenhuma linha sobreponha a seguinte.
        """
        nonlocal y
        p.setFont(font)
        probe = QRectF(x, 0, wrap_w, 100000)
        used = p.boundingRect(probe, Qt.TextWordWrap, text)
        rect = QRectF(x, y, wrap_w, used.height())
        p.drawText(rect, Qt.TextWordWrap, text)
        if advance:
            y += used.height() + 8
        return used.height()

    # --- cabeçalho ---------------------------------------------------
    p.setPen(QColor(0, 0, 0))
    if plan.timed and plan.night_start and plan.night_end:
        periodo = (f"{to_local(plan.night_start):%d/%m/%Y} · "
                   f"{_hm(plan.night_start)} – {_hm(plan.night_end)}")
        if plan.window_label:
            periodo += f" ({plan.window_label})"
        resumo = (
            f"Lua {plan.moon_illumination * 100:.0f}% iluminada · "
            f"{len(plan.entries)} objetos · "
            f"{plan.minutes_per_object} min por objeto"
        )
    else:
        periodo = plan.subtitle
        resumo = (f"{len(plan.entries)} objetos bem posicionados "
                  f"durante todo o período")
    paragraph(plan.title, margin, width - 2 * margin, f_title)
    paragraph(
        f"{periodo} · {plan.location}\n{resumo} · "
        f"gerado pelo Carina em {dt.datetime.now():%d/%m/%Y %H:%M}",
        margin, width - 2 * margin, f_meta,
    )
    y += 10

    # --- seção 1: checklist compacto ---------------------------------
    paragraph("Checklist" if not plan.timed else "Checklist da noite",
              margin, width - 2 * margin, f_head)
    p.setFont(f_row)
    row_h = p.boundingRect(
        QRectF(0, 0, 1000, 1000), 0, "Ag"
    ).height() + 10
    box = row_h * 0.55
    for i, e in enumerate(plan.entries, 1):
        ensure(row_h)
        p.setPen(QColor(90, 90, 90))
        p.drawRect(QRectF(margin, y + (row_h - box) / 2 - 2, box, box))
        p.setPen(QColor(0, 0, 0))
        hora = f"{_hm(e.when_utc)}  " if plan.timed else ""
        label = f"{i:>3}.  {hora}{e.catalog_id}"
        if e.common and e.common != e.catalog_id:
            label += f" — {e.common}"
        extra = (f"{e.type_label} · alt {e.altitude:.0f}° · "
                 f"{INSTRUMENT_LABEL.get(e.instrument, '')}")
        if e.constellation:
            extra += f" · {e.constellation}"
        if e.moon_warning:
            extra += " · LUA PRÓXIMA"
        if e.in_twilight:
            extra += " · CÉU CLARO"
        p.drawText(QRectF(margin + box + 14, y, width * 0.52, row_h),
                   Qt.AlignVCenter, label)
        p.setPen(QColor(110, 110, 110))
        p.drawText(
            QRectF(margin + box + 14 + width * 0.52, y,
                   width - 2 * margin - box - 14 - width * 0.52, row_h),
            Qt.AlignVCenter, extra,
        )
        y += row_h
    y += 20

    # --- seção 2: um cartão por objeto, com carta de localização -----
    chart_px = 0
    chart_img = None
    if stars is not None:
        from .finderchart import render_finder_chart

        # ~62 mm a 300 dpi; a carta fica à esquerda, o texto à direita
        chart_px = int(62 / 25.4 * 300)

    for i, e in enumerate(plan.entries, 1):
        if progress is not None:
            progress.setValue(i - 1)
            QApplication.processEvents()
            if progress.wasCanceled():
                p.end()
                return False

        if stars is not None:
            chart_img = render_finder_chart(e, stars,
                                            const_lines)

        # mede os textos antes de reservar espaço para o cartão
        text_x = margin + (chart_px + 24 if chart_img else 0)
        text_w = width - margin - text_x
        hora = f"{_hm(e.when_utc)} — " if plan.timed else ""
        title = f"{i}. {hora}{e.catalog_id}"
        if e.common and e.common != e.catalog_id:
            title += f" ({e.common})"
        meta = f"{e.type_label}"
        if e.constellation:
            meta += f" em {e.constellation}"
        meta += f" · alt {e.altitude:.0f}° · az {e.azimuth:.0f}°"
        if e.magnitude is not None:
            meta += f" · mag {e.magnitude:.1f}"
        if e.size_arcmin:
            meta += f" · {e.size_arcmin:.0f}'"
        if e.moon_sep <= 360:
            meta += f" · Lua a {e.moon_sep:.0f}°"
            if e.moon_warning:
                meta += " (ATRAPALHA)"
        instrumento = (
            f"Instrumento:  {INSTRUMENT_LABEL.get(e.instrument, '')}"
        )
        if e.in_twilight:
            instrumento += ("   ·   Céu ainda claro neste horário: "
                            "só entrou por ser bem brilhante.")
        if e.note:
            instrumento += f"   ·   {e.note}"
        blocks = [
            (title, f_head), (meta, f_meta), (instrumento, f_meta),
            (f"O que ver:  {e.what_to_see}", f_body),
            (e.binocular, f_body),
            (f"Como encontrar:  {e.how_to_find}", f_body),
        ]
        total_text = 0.0
        for text, font in blocks:
            p.setFont(font)
            used = p.boundingRect(
                QRectF(0, 0, text_w, 100000), Qt.TextWordWrap, text
            )
            total_text += used.height() + 8
        card_h = max(total_text, chart_px if chart_img else 0) + 26

        ensure(card_h)
        top = y
        if chart_img is not None:
            p.drawImage(
                QRectF(margin, top, chart_px, chart_px), chart_img
            )
        for text, font in blocks:
            paragraph(text, text_x, text_w, font)
        y = max(y, top + (chart_px if chart_img else 0) + 8)
        p.setPen(QColor(190, 190, 190))
        p.drawLine(QRectF(margin, y, width - 2 * margin, 0).topLeft(),
                   QRectF(margin, y, width - 2 * margin, 0).topRight())
        p.setPen(QColor(0, 0, 0))
        y += 18

    if progress is not None:
        progress.setValue(len(plan.entries))
    p.end()
    return True
