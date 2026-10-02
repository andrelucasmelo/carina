"""PDF de campo do roteiro de observação — v2 (v0.15 T13).

Conteúdo:

1. capa com título, noite, local, resumo e a **carta geral da noite** (céu
   inteiro com os alvos numerados na posição do horário de cada um);
2. **checklist compacto** (uma linha por parada, com caixa para marcar);
3. um **cartão por objeto** com instruções e carta de localização.

Cada página tem cabeçalho (título e noite) e rodapé numerado. Três
**temas**: claro (papel), escuro (o visual do Carina) e vermelho (para não
perder a adaptação ao escuro no campo).

O texto é sempre MEDIDO antes de desenhado (``boundingRect``) e o cursor
vertical avança pela altura real — nunca há linhas sobrepostas.

Também exporta o roteiro em **CSV** (planilhas) e **texto** (celular,
mensagens).
"""

from __future__ import annotations

import csv
import datetime as dt
import io

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from ..core.localtime import to_local
from ..core.observing import INSTRUMENT_LABEL

THEMES = {
    "light": {"bg": None, "fg": QColor(0, 0, 0), "muted": QColor(105, 110, 120),
              "line": QColor(190, 190, 190), "box": QColor(90, 90, 90),
              "accent": QColor(180, 40, 40)},
    "dark": {"bg": QColor(10, 14, 28), "fg": QColor(225, 230, 242),
             "muted": QColor(140, 152, 176), "line": QColor(55, 66, 92),
             "box": QColor(150, 160, 185), "accent": QColor(255, 120, 110)},
    "red": {"bg": QColor(0, 0, 0), "fg": QColor(230, 55, 40),
            "muted": QColor(160, 40, 28), "line": QColor(90, 18, 12),
            "box": QColor(200, 45, 30), "accent": QColor(255, 80, 50)},
}
THEME_LABELS = {"light": "Claro (papel)", "dark": "Escuro (Carina)",
                "red": "Vermelho (visão noturna)"}
CSV_COLUMNS = ["ordem", "hora", "designacao", "nome", "tipo", "magnitude",
               "tamanho_arcmin", "altitude", "azimute", "janela_inicio", "janela_fim",
               "nota", "instrumento", "constelacao", "lua_graus", "anotacao"]


def _hm(value: dt.datetime | None) -> str:
    return to_local(value).strftime("%H:%M") if value else "—"


# ---------------------------------------------------------------------------
# CSV e texto
# ---------------------------------------------------------------------------

def plan_to_csv(plan) -> str:
    """Roteiro em CSV (separador ';', vírgula decimal, como no Excel PT)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(CSV_COLUMNS)

    def num(value, fmt="{:.1f}"):
        return "" if value is None else fmt.format(value).replace(".", ",")

    for i, e in enumerate(plan.entries, 1):
        w.writerow([
            i, _hm(e.when_utc) if plan.timed else "", e.designation,
            e.common or "", e.type_label, num(e.magnitude), num(e.size_arcmin, "{:.0f}"),
            num(e.altitude, "{:.0f}"), num(e.azimuth, "{:.0f}"),
            _hm(e.window_start) if e.window_start else "",
            _hm(e.window_end) if e.window_end else "", e.score or "",
            INSTRUMENT_LABEL.get(e.instrument, e.instrument), e.constellation,
            "" if e.moon_sep > 360 else num(e.moon_sep, "{:.0f}"), e.note,
        ])
    return buf.getvalue()


def plan_to_text(plan) -> str:
    """Roteiro em texto corrido, bom para levar no celular."""
    lines = [plan.title]
    if plan.timed and plan.night_start and plan.night_end:
        lines.append(f"{to_local(plan.night_start):%d/%m/%Y} · {_hm(plan.night_start)}–"
                     f"{_hm(plan.night_end)} · {plan.location}")
    elif plan.subtitle:
        lines.append(f"{plan.subtitle} · {plan.location}")
    lines.append("")
    for i, e in enumerate(plan.entries, 1):
        when = f"{_hm(e.when_utc)} " if plan.timed else ""
        extra = [e.type_label, f"alt {e.altitude:.0f}°"]
        if e.constellation:
            extra.append(e.constellation)
        extra.append(INSTRUMENT_LABEL.get(e.instrument, e.instrument))
        lines.append(f"{i:>2}. {when}{e.label} — {', '.join(extra)}")
        if e.note:
            lines.append(f"     nota: {e.note}")
    lines.append("")
    lines.append(f"Gerado pelo Carina em {dt.datetime.now():%d/%m/%Y %H:%M}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def write_plan_pdf(path: str, plan, stars=None, const_lines=None, progress=None,
                   theme: str = "light") -> bool:
    """Desenha o PDF. Devolve False se o usuário cancelou no meio."""
    pal = THEMES.get(theme, THEMES["light"])
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageOrientation(QPageLayout.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
    writer.setResolution(300)
    writer.setTitle(plan.title)
    writer.setCreator("Carina")

    p = QPainter(writer)
    W, H = writer.width(), writer.height()
    M = int(14 / 25.4 * 300)                 # margem de 14 mm
    FOOT = 70
    f_title = QFont("Segoe UI", 18, QFont.Bold)
    f_head = QFont("Segoe UI", 12, QFont.Bold)
    f_meta = QFont("Segoe UI", 9)
    f_body = QFont("Segoe UI", 9)
    f_row = QFont("Segoe UI", 8)
    f_small = QFont("Segoe UI", 7)

    if plan.timed and plan.night_start and plan.night_end:
        night = (f"{to_local(plan.night_start):%d/%m/%Y} · "
                 f"{_hm(plan.night_start)} – {_hm(plan.night_end)}")
    else:
        night = plan.subtitle or ""
    state = {"y": float(M), "page": 1}

    def begin_page() -> None:
        if pal["bg"] is not None:
            p.fillRect(QRectF(0, 0, W, H), pal["bg"])
        p.setFont(f_small)
        p.setPen(pal["muted"])
        p.drawText(QRectF(M, H - M + 10, W - 2 * M, FOOT), Qt.AlignHCenter | Qt.AlignTop,
                   f"Carina · {plan.title} · {night} — página {state['page']}")
        state["y"] = float(M)
        if state["page"] > 1:
            p.drawText(QRectF(M, M - 50, W - 2 * M, 40), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{plan.title} · {night} · {plan.location}")
            p.setPen(pal["line"])
            p.drawLine(M, M - 6, W - M, M - 6)
            state["y"] = float(M + 14)

    def ensure(space: float) -> None:
        if state["y"] + space > H - M - FOOT:
            writer.newPage()
            state["page"] += 1
            begin_page()

    def measure(text: str, width: float, font: QFont) -> float:
        p.setFont(font)
        return p.boundingRect(QRectF(0, 0, width, 100000), Qt.TextWordWrap, text).height()

    def paragraph(text: str, x: float, width: float, font: QFont, color=None,
                  advance: bool = True) -> float:
        h = measure(text, width, font)
        p.setPen(color or pal["fg"])
        p.drawText(QRectF(x, state["y"], width, h), Qt.TextWordWrap, text)
        if advance:
            state["y"] += h + 8
        return h

    begin_page()
    # --- capa ----------------------------------------------------------------
    if plan.timed:
        resumo = (f"Lua {plan.moon_illumination * 100:.0f}% iluminada · "
                  f"{len(plan.entries)} objetos · {plan.minutes_per_object} min por objeto")
    else:
        resumo = f"{len(plan.entries)} objetos bem posicionados durante todo o período"
    horizon = getattr(plan, "horizon", None)
    if horizon is not None:
        resumo += f" · horizonte: {horizon.name}"
    paragraph(plan.title, M, W - 2 * M, f_title)
    paragraph(f"{night}{' (' + plan.window_label + ')' if plan.window_label else ''} · "
              f"{plan.location}\n{resumo} · gerado pelo Carina em "
              f"{dt.datetime.now():%d/%m/%Y %H:%M}", M, W - 2 * M, f_meta, pal["muted"])
    state["y"] += 6

    if plan.timed and getattr(plan, "engine", None) is not None and stars is not None \
            and plan.entries:
        from .finderchart import render_overview_chart

        size = int(min(W - 2 * M, (H - M - FOOT - state["y"]) * 0.82))
        img = render_overview_chart(plan, stars, const_lines, size_px=size, theme=theme)
        x0 = (W - size) / 2
        p.drawImage(QRectF(x0, state["y"], size, size), img)
        state["y"] += size + 10
        paragraph("Mapa da noite: segure acima da cabeça com o N voltado para o norte "
                  "(leste à esquerda). Cada número é uma parada do roteiro, na direção e "
                  "na altura em que o objeto estará no horário dela. Círculos "
                  "tracejados: 20°, 40°, 60° e 80° de altitude; o ponto central é o "
                  "zênite.", M, W - 2 * M, f_small, pal["muted"])
        writer.newPage()
        state["page"] += 1
        begin_page()
    else:
        state["y"] += 10

    # --- checklist -------------------------------------------------------------
    paragraph("Checklist da noite" if plan.timed else "Checklist", M, W - 2 * M, f_head)
    p.setFont(f_row)
    row_h = p.boundingRect(QRectF(0, 0, 1000, 1000), 0, "Ag").height() + 10
    box = row_h * 0.55
    col1 = (W - 2 * M) * 0.52
    for i, e in enumerate(plan.entries, 1):
        ensure(row_h)
        y = state["y"]
        p.setPen(pal["box"])
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(M, y + (row_h - box) / 2 - 2, box, box))
        p.setPen(pal["fg"])
        p.setFont(f_row)
        hora = f"{_hm(e.when_utc)}  " if plan.timed else ""
        p.drawText(QRectF(M + box + 14, y, col1, row_h), Qt.AlignVCenter,
                   f"{i:>3}.  {hora}{e.label}")
        extra = (f"{e.type_label} · alt {e.altitude:.0f}° · "
                 f"{INSTRUMENT_LABEL.get(e.instrument, '')}")
        if e.score:
            extra += f" · nota {e.score}"
        if e.constellation:
            extra += f" · {e.constellation}"
        if e.moon_warning:
            extra += " · LUA PRÓXIMA"
        if e.in_twilight:
            extra += " · CÉU CLARO"
        if e.late:
            extra += " · FORA DA JANELA"
        p.setPen(pal["muted"])
        p.drawText(QRectF(M + box + 14 + col1, y, W - 2 * M - box - 14 - col1, row_h),
                   Qt.AlignVCenter, extra)
        state["y"] += row_h
    state["y"] += 20

    # --- cartões com carta de localização -------------------------------------
    chart_px = int(62 / 25.4 * 300) if stars is not None else 0
    for i, e in enumerate(plan.entries, 1):
        if progress is not None:
            progress.setValue(i - 1)
            QApplication.processEvents()
            if progress.wasCanceled():
                p.end()
                return False
        chart_img = None
        if stars is not None and e.klass not in ("PLANET", "MOON"):
            from .finderchart import render_finder_chart

            chart_img = render_finder_chart(e, stars, const_lines, theme=theme)
        text_x = M + (chart_px + 24 if chart_img is not None else 0)
        text_w = W - M - text_x
        hora = f"{_hm(e.when_utc)} — " if plan.timed else ""
        title = f"{i}. {hora}{e.label}"
        meta = e.type_label + (f" em {e.constellation}" if e.constellation else "")
        meta += f" · alt {e.altitude:.0f}° · az {e.azimuth:.0f}°"
        if e.magnitude is not None:
            meta += f" · mag {e.magnitude:.1f}"
        if e.size_arcmin:
            meta += f" · {e.size_arcmin:.0f}'"
        if e.moon_sep <= 360:
            meta += f" · Lua a {e.moon_sep:.0f}°" + (" (ATRAPALHA)" if e.moon_warning else "")
        vis = ""
        if e.rise_utc or e.set_utc:
            vis = (f"Nasce {_hm(e.rise_utc)} · culmina {_hm(e.transit_utc)} · "
                   f"se põe {_hm(e.set_utc)}")
        if e.window_start and e.window_end:
            vis += f"{' · ' if vis else ''}janela útil {_hm(e.window_start)}–{_hm(e.window_end)}"
        instr = f"Instrumento:  {INSTRUMENT_LABEL.get(e.instrument, '')}"
        if e.score_text:
            instr += f"   ·   Nota {e.score_text}"
        if e.in_twilight:
            instr += "   ·   Céu ainda claro neste horário: só entrou por ser bem brilhante."
        if e.note:
            instr += f"   ·   {e.note}"
        blocks = [(title, f_head, pal["fg"]), (meta, f_meta, pal["muted"])]
        if vis:
            blocks.append((vis, f_meta, pal["muted"]))
        blocks += [(instr, f_meta, pal["muted"]),
                   (f"O que ver:  {e.what_to_see}", f_body, pal["fg"]),
                   (e.binocular, f_body, pal["fg"]),
                   (f"Como encontrar:  {e.how_to_find}", f_body, pal["fg"])]
        total = sum(measure(t, text_w, f) + 8 for t, f, _c in blocks)
        card_h = max(total, chart_px if chart_img is not None else 0) + 26
        ensure(card_h)
        top = state["y"]
        if chart_img is not None:
            p.drawImage(QRectF(M, top, chart_px, chart_px), chart_img)
        for text, font, color in blocks:
            paragraph(text, text_x, text_w, font, color)
        state["y"] = max(state["y"], top + (chart_px if chart_img is not None else 0) + 8)
        p.setPen(pal["line"])
        p.drawLine(M, int(state["y"]), W - M, int(state["y"]))
        state["y"] += 18

    if progress is not None:
        progress.setValue(len(plan.entries))
    p.end()
    return True
