"""Painel de informações do objeto selecionado (item 8 do escopo).

Fase 1: dados astronômicos ao vivo. A imagem do objeto entra junto com o
banco de céu profundo (download sob demanda com cache, ADR-004).
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea

from ..catalogs import images
from ..catalogs.dso import DsoCatalog, type_label
from ..catalogs.stars import GENITIVE, StarCatalog
from ..core.engine import SkyEngine
from ..core.formats import angle_deg, dec_dms, ra_hms

AU_KM = 149_597_870.7


class InfoPanel(QScrollArea):
    """Painel lateral de informações do objeto selecionado (a ficha HTML é
    montada por :func:`build_info_html`, compartilhada com o popup)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._label.setMargin(10)
        self.setWidget(self._label)
        self.setMinimumWidth(260)

    def show_html(self, html: str) -> None:
        self._label.setText(html)


def _row(label: str, value: str) -> str:
    return (
        f"<tr><td style='color:#8a93a5; padding-right:8px'>{label}</td>"
        f"<td>{value}</td></tr>"
    )


def build_info_html(selection, engine: SkyEngine, stars: StarCatalog,
                    const_names: dict[str, dict],
                    dso: DsoCatalog | None = None) -> str:
    """Monta o HTML do painel para a seleção atual."""
    if selection is None:
        return "<i>Clique num objeto do céu para ver os detalhes.</i>"

    t = engine.time.current()
    m = engine.horizontal_matrix(t)
    kind, key = selection

    if kind == "dso" and dso is not None:
        return _dso_html(int(key), engine, m, dso, const_names)

    if kind == "star":
        idx = int(key)
        title = stars.proper.get(idx) or stars.label(idx, "bayer") or (
            f"HIP {int(stars.hip[idx])}" if stars.hip[idx] else "Estrela"
        )
        vec_h = stars.xyz[idx] @ m.T
        alt = float(np.arcsin(np.clip(vec_h[2], -1, 1)))
        az = float(np.arctan2(vec_h[1], vec_h[0]) % (2 * np.pi))
        con = stars.con.get(idx, "")
        con_info = const_names.get(con)
        con_txt = (
            f"{con_info['name']} ({GENITIVE.get(con, con)})" if con_info
            else GENITIVE.get(con, con or "—")
        )
        rows = [
            _row("Designações", stars.full_designation(idx)),
            _row("Magnitude", f"{stars.mag[idx]:.2f}"),
            _row("Índice de cor B–V", f"{stars.ci[idx]:+.2f}"),
            _row("Constelação", con_txt),
            _row("AR (J2000)", ra_hms(float(stars.ra[idx]))),
            _row("Dec (J2000)", dec_dms(float(stars.dec[idx]))),
            _row("Azimute", angle_deg(az)),
            _row("Altitude", angle_deg(alt)),
        ]
        body_note = ""
    else:
        state = next((b for b in engine.bodies(t) if b.name == key), None)
        if state is None:
            return "<i>Objeto indisponível.</i>"
        title = state.name
        v_icrs = m.T @ state.vec
        ra = float(np.arctan2(v_icrs[1], v_icrs[0]) % (2 * np.pi))
        dec = float(np.arcsin(np.clip(v_icrs[2], -1, 1)))
        rows = [_row("Magnitude", f"{state.magnitude:.1f}")]
        if state.name == "Lua":
            from ..core.eclipses import moon_influence_radii

            illum = engine.moon_illumination(t)
            rows.append(_row("Distância", f"{state.distance_au * AU_KM:,.0f} km"))
            rows.append(_row("Iluminação", f"{illum * 100:.0f}%"))
            r1, r2 = moon_influence_radii(illum)
            rows.append(
                _row(
                    "Astrofotografia",
                    f"evitar alvos a menos de {math.degrees(r1):.0f}° "
                    f"(cautela até {math.degrees(r2):.0f}°)",
                )
            )
        else:
            rows.append(_row("Distância", f"{state.distance_au:.3f} UA"))
        if state.angular_radius > 0:
            arcmin = np.degrees(state.angular_radius) * 2 * 60
            rows.append(_row("Diâmetro aparente", f"{arcmin:.1f}′"))
        rows += [
            _row("AR (data)", ra_hms(ra)),
            _row("Dec (data)", dec_dms(dec)),
            _row("Azimute", angle_deg(state.az)),
            _row("Altitude", angle_deg(state.alt)),
        ]
        body_note = (
            "<p style='color:#8a93a5; font-size: 8pt'>"
            "AR/Dec derivadas da direção aparente.</p>"
        )

    table = "".join(rows)
    return (
        f"<h2 style='margin-bottom:2px'>{title}</h2>"
        f"<table style='font-size:9pt'>{table}</table>{body_note}"
    )


def _dso_html(object_id: int, engine: SkyEngine, m, dso: DsoCatalog,
              const_names: dict[str, dict]) -> str:
    data = dso.get(object_id)
    if data is None:
        return "<i>Objeto removido do banco.</i>"

    ra, dec = data["ra"], data["dec"]
    cd = math.cos(dec)
    vec_h = np.array(
        [cd * math.cos(ra), cd * math.sin(ra), math.sin(dec)]
    ) @ m.T
    alt = float(np.arcsin(np.clip(vec_h[2], -1, 1)))
    az = float(np.arctan2(vec_h[1], vec_h[0]) % (2 * np.pi))

    desig = " · ".join(
        f"{cat} {ident}" if cat not in ("SH2",) else f"Sh2-{ident}"
        for cat, ident in data["designations"]
    ) or data["name"]
    con = data.get("con") or ""
    con_info = const_names.get(con)
    rows = [
        _row("Designações", desig),
        _row("Tipo", type_label(data["type"])),
    ]
    if data.get("common"):
        rows.append(_row("Nomes", data["common"]))
    if data.get("mag") is not None:
        rows.append(_row("Magnitude", f"{data['mag']:.1f}"))
    if data.get("maj"):
        size = f"{data['maj']:.1f}′"
        if data.get("min"):
            size += f" × {data['min']:.1f}′"
        rows.append(_row("Tamanho", size))
    if data.get("pa") is not None and data.get("maj"):
        rows.append(_row("Ângulo de posição", f"{data['pa']:.0f}°"))
    if con:
        rows.append(
            _row("Constelação", con_info["name"] if con_info else con)
        )
    rows += [
        _row("AR (J2000)", ra_hms(ra)),
        _row("Dec (J2000)", dec_dms(dec)),
        _row("Azimute", angle_deg(az)),
        _row("Altitude", angle_deg(alt)),
    ]
    if data["categories"]:
        rows.append(_row("Categorias", ", ".join(data["categories"])))
    if data.get("notes"):
        rows.append(_row("Notas", data["notes"]))
    if not data["enabled"]:
        rows.append(_row("Estado", "desabilitado no banco"))

    img_path = images.image_path_for(data["name"])
    if img_path is not None:
        img_html = (
            f"<p><img src='{img_path.as_uri()}' width='300'></p>"
            "<p style='color:#8a93a5; font-size:7pt'>Imagem: DSS2 color"
            " (CDS hips2fits)</p>"
        )
    else:
        images.request_image(
            data["name"], ra, dec, data.get("maj")
        )
        img_html = (
            "<p style='color:#8a93a5; font-size:8pt'><i>Baixando imagem…"
            " (ficará em cache local)</i></p>"
        )

    title = data["name"]
    if data.get("common"):
        title = f"{data['name']} — {data['common'].split(',')[0]}"
    return (
        f"<h2 style='margin-bottom:2px'>{title}</h2>"
        f"<table style='font-size:9pt'>{''.join(rows)}</table>{img_html}"
    )
