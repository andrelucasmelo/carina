"""Painel de informações do objeto selecionado (item 8 do escopo).

Fase 1: dados astronômicos ao vivo. A imagem do objeto entra junto com o
banco de céu profundo (download sob demanda com cache, ADR-004).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea

from ..catalogs.stars import GENITIVE, StarCatalog
from ..core.engine import SkyEngine
from ..core.formats import angle_deg, dec_dms, ra_hms

AU_KM = 149_597_870.7


class InfoPanel(QScrollArea):
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
                    const_names: dict[str, dict]) -> str:
    """Monta o HTML do painel para a seleção atual."""
    if selection is None:
        return "<i>Clique num objeto do céu para ver os detalhes.</i>"

    t = engine.time.current()
    m = engine.horizontal_matrix(t)
    kind, key = selection

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
            rows.append(_row("Distância", f"{state.distance_au * AU_KM:,.0f} km"))
            rows.append(
                _row("Iluminação", f"{engine.moon_illumination(t) * 100:.0f}%")
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
