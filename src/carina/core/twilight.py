"""Crepúsculos e limites da noite (civil, náutica, astronômica)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, fields

from skyfield import almanac

# Estados de almanac.dark_twilight_day:
# 0 = noite escura, 1 = crep. astronômico, 2 = náutico, 3 = civil, 4 = dia


@dataclass
class NightInfo:
    """Limites da noite que contém (ou segue) o instante de referência.

    Todos em UTC; None quando o evento não ocorre (latitudes extremas).
    """

    sunset: dt.datetime | None = None
    civil_dusk: dt.datetime | None = None      # Sol em -6°: começa a noite civil
    nautical_dusk: dt.datetime | None = None   # -12°: começa a noite náutica
    astro_dusk: dt.datetime | None = None      # -18°: começa a noite astronômica
    astro_dawn: dt.datetime | None = None
    nautical_dawn: dt.datetime | None = None
    civil_dawn: dt.datetime | None = None
    sunrise: dt.datetime | None = None

    def label_date(self) -> tuple[dt.date, dt.date] | None:
        """Datas locais (início, fim) da noite, para rótulos."""
        if self.sunset is None or self.sunrise is None:
            return None
        from .localtime import to_local

        return (
            to_local(self.sunset).date(),
            to_local(self.sunrise).date(),
        )


_FALLING = {(4, 3): "sunset", (3, 2): "civil_dusk", (2, 1): "nautical_dusk",
            (1, 0): "astro_dusk"}
_RISING = {(0, 1): "astro_dawn", (1, 2): "nautical_dawn",
           (2, 3): "civil_dawn", (3, 4): "sunrise"}


def night_info(engine, ref_utc: dt.datetime) -> NightInfo:
    """Limites da noite associada ao instante dado.

    A janela vai do meio-dia local anterior ao meio-dia local seguinte, de
    modo que qualquer hora da tarde/madrugada caia na mesma noite.
    """
    from .localtime import to_local

    # "meio-dia local" é o do OBSERVADOR: com uma cidade em outro fuso, a
    # noite calculada seria a errada se usássemos o relógio do computador
    local = to_local(ref_utc)
    noon = local.replace(hour=12, minute=0, second=0, microsecond=0)
    if local < noon:
        noon -= dt.timedelta(days=1)
    t0 = engine.ts.from_datetime(noon.astimezone(dt.timezone.utc))
    t1 = engine.ts.from_datetime(
        (noon + dt.timedelta(days=1)).astimezone(dt.timezone.utc)
    )
    f = almanac.dark_twilight_day(engine.eph, engine.topos)
    times, states = almanac.find_discrete(t0, t1, f)

    info = NightInfo()
    prev = int(f(t0))
    for ti, si in zip(times, states):
        si = int(si)
        key = _FALLING.get((prev, si)) or _RISING.get((prev, si))
        if key and getattr(info, key) is None:
            setattr(info, key, ti.utc_datetime())
        prev = si
    return info


def sun_altitude_band(sun_alt_deg: float) -> str:
    """Classifica o instante: 'day', 'civil', 'nautical' ou 'astro'."""
    if sun_alt_deg > -6.0:
        return "day"
    if sun_alt_deg > -12.0:
        return "civil"
    if sun_alt_deg > -18.0:
        return "nautical"
    return "astro"


def format_night_summary(info: NightInfo) -> list[tuple[str, str]]:
    """Pares (título, 'HH:MM – HH:MM') para exibição no painel."""
    from .localtime import to_local

    def hm(value: dt.datetime | None) -> str:
        return to_local(value).strftime("%H:%M") if value else "—"

    return [
        ("Sol", f"{hm(info.sunset)} – {hm(info.sunrise)}"),
        ("Civil −6°", f"{hm(info.civil_dusk)} – {hm(info.civil_dawn)}"),
        ("Náutica −12°", f"{hm(info.nautical_dusk)} – {hm(info.nautical_dawn)}"),
        ("Astron. −18°", f"{hm(info.astro_dusk)} – {hm(info.astro_dawn)}"),
    ]
