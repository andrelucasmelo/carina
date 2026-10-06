"""Dados do relatório da noite (v0.22 T2).

Uma "noite" vai do meio-dia local ao meio-dia seguinte, como em
:func:`core.twilight.night_info`: uma observação às 2h da manhã pertence à
noite que começou na véspera.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

UTC = dt.timezone.utc


@dataclass
class NightReport:
    night: dt.date                       # data local do início da noite
    location: str
    observations: list[dict] = field(default_factory=list)
    sunset: dt.datetime | None = None
    astro_dusk: dt.datetime | None = None
    astro_dawn: dt.datetime | None = None
    moon_phase: str = ""
    moon_illum: float = 0.0
    mid_utc: dt.datetime | None = None   # instante do mapa (meio das observações)

    @property
    def count(self) -> int:
        return len(self.observations)

    def object_names(self) -> list[str]:
        seen, out = set(), []
        for o in self.observations:
            if (o["kind"], o["ident"]) not in seen:
                seen.add((o["kind"], o["ident"]))
                out.append(o["name"])
        return out


def night_bounds(night: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Meio-dia local da data e meio-dia seguinte, em UTC."""
    from .localtime import from_local_naive

    a = from_local_naive(dt.datetime(night.year, night.month, night.day, 12, 0))
    return a.astimezone(UTC), (a + dt.timedelta(days=1)).astimezone(UTC)


def night_of(when_utc: dt.datetime) -> dt.date:
    from .localtime import to_local

    lt = to_local(when_utc)
    return (lt - dt.timedelta(days=1)).date() if lt.hour < 12 else lt.date()


def nights_with_observations(userdata) -> list[dt.date]:
    """Noites do diário, da mais recente para a mais antiga."""
    if userdata is None:
        return []
    out = []
    for o in userdata.observations():
        d = night_of(o["when_utc"])
        if d not in out:
            out.append(d)
    return out


def build_report(engine, userdata, night: dt.date, location: str = "") -> NightReport:
    from .tonight import moon_phase_name
    from .twilight import night_info

    a, b = night_bounds(night)
    obs = [o for o in (userdata.observations() if userdata is not None else [])
           if a <= o["when_utc"] < b]
    obs.sort(key=lambda o: o["when_utc"])
    rep = NightReport(night, location, obs)
    info = night_info(engine, a + dt.timedelta(hours=1))
    rep.sunset, rep.astro_dusk, rep.astro_dawn = info.sunset, info.astro_dusk, info.astro_dawn
    if obs:
        t0, t1 = obs[0]["when_utc"], obs[-1]["when_utc"]
        rep.mid_utc = t0 + (t1 - t0) / 2
    else:
        rep.mid_utc = (info.astro_dusk or a + dt.timedelta(hours=9)) + dt.timedelta(hours=1)
    from skyfield import almanac

    t = engine.ts.from_datetime(rep.mid_utc)
    rep.moon_phase, _deg = moon_phase_name(engine, t)
    rep.moon_illum = float(almanac.fraction_illuminated(engine.eph, "moon", t)) * 100.0
    return rep
