"""Popup de informações da noite: crepúsculos, Lua e dados do observador."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout,
)

from ..core.eclipses import moon_influence_radii
from ..core.twilight import format_night_summary, night_info


class NightInfoDialog(QDialog):
    def __init__(self, engine, location_name: str, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.location_name = location_name
        self.setWindowTitle(self.tr("Informações da noite"))
        self.setMinimumWidth(420)

        self.label = QLabel()
        self.label.setTextFormat(Qt.RichText)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

        buttons = QDialogButtonBox(parent=self)
        btn_refresh = QPushButton(self.tr("Atualizar"))
        btn_refresh.clicked.connect(self.refresh)
        buttons.addButton(btn_refresh, QDialogButtonBox.ActionRole)
        buttons.addButton(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        t = self.engine.time.current()
        when = self.engine.time.current_datetime().astimezone()
        try:
            info = night_info(self.engine, self.engine.time.current_datetime())
            rows = "".join(
                f"<tr><td style='color:#8a93a5;padding-right:14px'><b>{k}</b>"
                f"</td><td>{v}</td></tr>"
                for k, v in format_night_summary(info)
            )
            dates = info.label_date()
            title = ""
            if dates:
                d0, d1 = dates
                title = (
                    f"<h3 style='margin-bottom:2px'>Noite de "
                    f"{d0.strftime('%d/%m/%Y')} → {d1.strftime('%d/%m/%Y')}</h3>"
                )
            dark = ""
            if info.astro_dusk and info.astro_dawn:
                hours = (info.astro_dawn - info.astro_dusk).total_seconds() / 3600
                dark = (
                    f"<p><b>{hours:.1f} h</b> de noite astronômica "
                    f"(céu totalmente escuro).</p>"
                )
        except Exception as exc:  # noqa: BLE001
            return self.label.setText(f"<i>Indisponível ({exc})</i>")

        moon = next((b for b in self.engine.bodies(t) if b.name == "Lua"), None)
        moon_html = ""
        if moon is not None:
            illum = self.engine.moon_illumination(t)
            r1, r2 = moon_influence_radii(illum)
            status = (
                f"acima do horizonte (alt {math.degrees(moon.alt):.0f}°)"
                if moon.alt > 0 else "abaixo do horizonte"
            )
            moon_html = (
                "<h4 style='margin-bottom:2px'>Lua</h4>"
                f"<p>Iluminação <b>{illum * 100:.0f}%</b> · {status}<br>"
                f"Astrofotografia: evitar alvos a menos de "
                f"<b>{math.degrees(r1):.0f}°</b> "
                f"(cautela até {math.degrees(r2):.0f}°)</p>"
            )

        self.label.setText(
            f"{title}"
            f"<p style='color:#8a93a5'>{self.location_name} · instante da "
            f"simulação: {when.strftime('%d/%m/%Y %H:%M')}</p>"
            f"<table style='font-size:10pt'>{rows}</table>"
            f"{dark}{moon_html}"
        )
