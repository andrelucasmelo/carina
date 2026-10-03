"""Motor do Calendário do céu (v0.17 T4, ADR-047).

Junta num único fluxo, ordenado e sem duplicatas, tudo o que vale a pena
anotar na agenda de quem observa:

==============  ==========================================================
categoria       origem
==============  ==========================================================
``lua``         fases (``almanac``), perigeu/apogeu e superlua, libração,
                Lunar X, Alça Dourada, Rupes Recta, luz cinérea
                (:mod:`core.moon`)
``eclipse``     eclipses do Sol e da Lua (:mod:`core.eclipses`)
``planeta``     oposições, conjunções com o Sol e elongações
                (:mod:`core.planetpath`)
``encontro``    Lua perto de planetas e de estrelas brilhantes; planetas
                perto entre si
``ocultacao``   ocultações visíveis do local (:mod:`core.occultations`)
``meteoros``    picos das chuvas (IMO), com a Lua na noite do pico
``noite``       noites escuras — mais de 8 h sem Lua (:mod:`core.dark_nights`)
``estacao``     equinócios e solstícios, nomeados pelo hemisfério
==============  ==========================================================

Cada evento tem um **UID estável** (categoria + título + minuto), que é o
que o ``.ics`` exporta e o que os lembretes guardam no ``carina.sqlite``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from .formats import num

UTC = dt.timezone.utc

CATEGORIES = {
    "lua": ("Lua", (190, 200, 220)),
    "eclipse": ("Eclipses", (255, 120, 90)),
    "planeta": ("Planetas", (240, 190, 90)),
    "encontro": ("Encontros", (150, 200, 120)),
    "ocultacao": ("Ocultações", (200, 140, 230)),
    "meteoros": ("Meteoros", (110, 190, 255)),
    "noite": ("Noites escuras", (120, 130, 200)),
    "estacao": ("Estações", (230, 230, 150)),
}

BRIGHT_STARS = {
    # nome: (AR em graus, Dec em graus) J2000 — estrelas perto da eclíptica
    "Aldebaran": (68.980, 16.509),
    "Regulus": (152.093, 11.967),
    "Spica": (201.298, -11.161),
    "Antares": (247.352, -26.432),
    "Plêiades": (56.75, 24.12),
    "Pollux": (116.329, 28.026),
}
PLANETS = ("Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno")
OUTER = ("Marte", "Júpiter", "Saturno", "Urano", "Netuno")


@dataclass
class SkyEvent:
    start_utc: dt.datetime
    category: str
    title: str
    detail: str = ""
    end_utc: dt.datetime | None = None
    importance: int = 1           # 1 normal · 2 destaque · 3 imperdível
    visible: bool | None = None   # do local escolhido (None = não se aplica)
    target: str = ""              # identidade para "ir até" (corpo, HIP…)
    extra: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        key = f"{self.category}|{self.title}|{self.start_utc:%Y%m%dT%H%M}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    @property
    def category_label(self) -> str:
        return CATEGORIES.get(self.category, (self.category,))[0]

    def local_start(self) -> dt.datetime:
        from .localtime import to_local

        return to_local(self.start_utc)

    def to_ics(self, location: str = "", alarm_minutes: int | None = None):
        from .ics import IcsEvent

        return IcsEvent(self.uid, self.start_utc, self.title, self.detail,
                        self.end_utc, self.category_label, location, alarm_minutes)


def _aware(when: dt.datetime) -> dt.datetime:
    return when if when.tzinfo else when.replace(tzinfo=UTC)


# --------------------------------------------------------------------------
# fontes
def moon_phase_events(engine, start, end) -> list[SkyEvent]:
    from skyfield import almanac

    names = {0: "Lua nova", 1: "Quarto crescente", 2: "Lua cheia", 3: "Quarto minguante"}
    t, y = almanac.find_discrete(engine.ts.from_datetime(start),
                                 engine.ts.from_datetime(end),
                                 almanac.moon_phases(engine.eph))
    return [SkyEvent(ti.utc_datetime(), "lua", names[int(yi)],
                     importance=2 if int(yi) in (0, 2) else 1, target="Lua")
            for ti, yi in zip(t, y)]


def moon_events(engine, start, end) -> list[SkyEvent]:
    from . import moon

    if not moon.kernels_available():
        return []
    fulls = [e.start_utc for e in moon_phase_events(engine, start - dt.timedelta(days=3),
                                                    end + dt.timedelta(days=3))
             if e.title == "Lua cheia"]
    out = []
    for ev in moon.all_events(engine, start, end):
        imp = 1
        title = ev.title
        if ev.kind == "perigeu" and any(abs((f - ev.when_utc).total_seconds()) < 1.5 * 86400
                                        for f in fulls):
            title, imp = "Superlua: Lua cheia perto do perigeu", 2
        if ev.kind in ("lunar_x", "alca_dourada"):
            imp = 2
        out.append(SkyEvent(ev.when_utc, "lua", title, ev.detail, ev.end_utc, imp,
                            target="Lua", extra={"kind": ev.kind}))
    return out


def eclipse_events(engine, start, end) -> list[SkyEvent]:
    from .eclipses import find_eclipses
    from .localtime import to_local  # noqa: F401

    years = max((end - start).days / 365.25, 0.01)
    out = []
    for e in find_eclipses(engine, start, years):
        if not (start <= _aware(e.when_utc) <= end):
            continue
        astro = "Lua" if e.kind == "lunar" else "Sol"
        title = f"Eclipse {e.type_label.lower()} {'da Lua' if e.kind == 'lunar' else 'do Sol'}"
        vis = ("visível daqui" if e.visible else "não visível daqui")
        out.append(SkyEvent(_aware(e.when_utc), "eclipse", title,
                            f"{e.detail} · {astro} a {e.alt_deg:.0f}° no máximo — {vis}.",
                            importance=3 if e.visible else 1, visible=e.visible,
                            target=astro))
    return out


def planet_events(engine, start, end) -> list[SkyEvent]:
    from .planetpath import compute_path

    days = max(int((end - start).total_seconds() / 86400) + 2, 2)
    labels = {"oposicao": "em oposição", "conjuncao": "em conjunção com o Sol",
              "elong_leste": "na maior elongação leste",
              "elong_oeste": "na maior elongação oeste"}
    hints = {"oposicao": "Melhor época do ano: a noite inteira no céu, maior e mais brilhante.",
             "conjuncao": "Escondido no brilho do Sol por algumas semanas.",
             "elong_leste": "Melhor momento para vê-lo ao anoitecer, no oeste.",
             "elong_oeste": "Melhor momento para vê-lo antes do amanhecer, no leste."}
    out = []
    for name in ("Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno"):
        path = compute_path(engine, name, start - dt.timedelta(days=1), days=days + 1)
        for ev in path.events:
            when = _aware(ev.when_utc)
            if not (start <= when <= end):
                continue
            detail = hints[ev.kind]
            if ev.kind.startswith("elong"):
                detail = f"{ev.value:.0f}° do Sol. " + detail
            imp = 2 if ev.kind in ("oposicao", "elong_leste", "elong_oeste") else 1
            out.append(SkyEvent(when, "planeta", f"{name} {labels[ev.kind]}", detail,
                                importance=imp, target=name))
    return out


def _radec_vec(ra_deg: float, dec_deg: float) -> np.ndarray:
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra),
                     math.sin(dec)])


def _minima(times, sep_deg, limit) -> list[int]:
    return [i for i in range(1, len(times) - 1)
            if sep_deg[i] <= sep_deg[i - 1] and sep_deg[i] < sep_deg[i + 1]
            and sep_deg[i] < limit]


def conjunction_events(engine, start, end, moon_limit: float = 4.0,
                       planet_limit: float = 2.0) -> list[SkyEvent]:
    """Lua perto de planetas e estrelas brilhantes; planetas entre si."""
    n = int((end - start).total_seconds() / 3600.0) + 2
    times = [start + dt.timedelta(hours=i) for i in range(n)]
    t = engine.ts.from_datetimes(times)
    obs = engine.site.at(t)

    def unit(body):
        p = np.asarray(obs.observe(engine.eph[body]).apparent().position.au, np.float64)
        return p / np.linalg.norm(p, axis=0)

    sun = unit("sun")
    moon_v = unit("moon")
    vecs = {name: unit(engine.body_key(name)) for name in PLANETS + ("Urano", "Netuno")}
    out = []

    def sep(a, b):
        return np.degrees(np.arccos(np.clip(np.sum(a * b, axis=0), -1, 1)))

    def elong_ok(v, i):
        return math.degrees(math.acos(max(-1.0, min(1.0, float(sun[:, i] @ v[:, i]))))) > 15

    for name in PLANETS:
        s = sep(moon_v, vecs[name])
        for i in _minima(times, s, moon_limit):
            if not elong_ok(vecs[name], i):
                continue
            out.append(SkyEvent(times[i], "encontro", f"Lua perto de {name}",
                                f"Separação de {num(s[i])}° (geocêntrica ao local).",
                                importance=2 if s[i] < 2 else 1, target=name))
    for star, (ra, dec) in BRIGHT_STARS.items():
        v = _radec_vec(ra, dec)
        s = np.degrees(np.arccos(np.clip(v @ moon_v, -1, 1)))
        for i in _minima(times, s, 3.0):
            if math.degrees(math.acos(max(-1.0, min(1.0, float(sun[:, i] @ v))))) < 15:
                continue
            out.append(SkyEvent(times[i], "encontro", f"Lua perto de {star}",
                                f"Separação de {num(s[i])}°.", target=star))
    names = list(PLANETS) + ["Urano", "Netuno"]
    step = 12
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            s = sep(vecs[names[a]], vecs[names[b]])[::step]
            sub = times[::step]
            for i in _minima(sub, s, planet_limit):
                if not elong_ok(vecs[names[a]], i * step):
                    continue
                if names[a] in ("Urano", "Netuno") or names[b] in ("Urano", "Netuno"):
                    if s[i] > 1.0:
                        continue
                out.append(SkyEvent(sub[i], "encontro",
                                    f"{names[a]} perto de {names[b]}",
                                    f"Separação de {num(s[i])}°.",
                                    importance=2 if s[i] < 1 else 1, target=names[a]))
    return out


def occultation_events(engine, start, end, mag_limit: float = 4.5) -> list[SkyEvent]:
    from . import moon
    from .occultations import find_occultations

    if not moon.kernels_available():
        return []
    out = []
    for o in find_occultations(engine, start, end, mag_limit=mag_limit, only_visible=True):
        what = o.target if o.kind == "planet" else f"{o.target} (mag {o.mag:.1f})"
        imp = 3 if o.kind == "planet" or o.mag < 1.5 else 2
        out.append(SkyEvent(o.immersion_utc or o.mid_utc, "ocultacao",
                            f"Ocultação de {what} pela Lua", o.describe().capitalize() + ".",
                            o.emersion_utc, imp, True, o.ident))
    return out


@lru_cache(maxsize=1)
def meteor_showers() -> tuple[dict, ...]:
    from ..config import package_data_dir

    path = package_data_dir() / "meteors.json"
    if not path.exists():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8"))["showers"])


def solar_longitude_times(engine, longitudes: list[float], start, end) -> list[list[dt.datetime]]:
    """Instantes em que a longitude solar (J2000) passa por cada valor."""
    from skyfield.framelib import ecliptic_J2000_frame

    n = int((end - start).total_seconds() / 86400.0) + 2
    times = [start + dt.timedelta(days=i) for i in range(n)]
    t = engine.ts.from_datetimes(times)
    earth = engine.earth

    def lon_of(tt):
        return earth.at(tt).observe(engine.eph["sun"]).frame_latlon(ecliptic_J2000_frame)[1].degrees

    lons = np.asarray(lon_of(t))
    out = []
    for target in longitudes:
        d = np.mod(lons - target + 180.0, 360.0) - 180.0
        hits = []
        for i in range(1, n):
            if d[i - 1] < 0 <= d[i]:
                a, b = times[i - 1], times[i]
                for _ in range(30):
                    mid = a + (b - a) / 2
                    dm = (float(lon_of(engine.ts.from_datetime(mid))) - target + 180) % 360 - 180
                    if dm < 0:
                        a = mid
                    else:
                        b = mid
                hits.append(a + (b - a) / 2)
        out.append(hits)
    return out


def meteor_events(engine, start, end) -> list[SkyEvent]:
    from skyfield import almanac

    showers = meteor_showers()
    if not showers:
        return []
    hits = solar_longitude_times(engine, [s["peak"] for s in showers],
                                 start - dt.timedelta(days=1), end + dt.timedelta(days=1))
    out = []
    lat = engine.topos.latitude.degrees if engine.site is not None else 0.0
    for s, peaks in zip(showers, hits):
        for when in peaks:
            if not (start <= when <= end):
                continue
            illum = float(almanac.fraction_illuminated(
                engine.eph, "moon", engine.ts.from_datetime(when)))
            # altura máxima do radiante (culminação) no local
            max_alt = 90.0 - abs(lat - s["dec"])
            if max_alt <= 0:
                vis, vis_ok = "o radiante não sobe neste local", False
            else:
                vis, vis_ok = f"radiante culmina a {max_alt:.0f}°", True
            zhr = "variável" if s["zhr"] == 0 else f"até {s['zhr']} meteoros/h (THZ)"
            moon_txt = ("Lua quase nova: noite ótima" if illum < 0.25 else
                        "Lua cheia atrapalha" if illum > 0.75 else
                        f"Lua {illum * 100:.0f}% iluminada")
            imp = 1
            if s["zhr"] >= 50 and vis_ok:
                imp = 3 if illum < 0.5 else 2
            elif s["zhr"] >= 15 and vis_ok:
                imp = 2
            out.append(SkyEvent(
                when, "meteoros", f"Pico das {s['name']}",
                f"{zhr}; {vis}; {moon_txt}. {s['note']}",
                importance=imp, visible=vis_ok, target=s["code"],
                extra={"zhr": s["zhr"], "moon": illum}))
    return out


def dark_night_events(engine, start, end) -> list[SkyEvent]:
    from .dark_nights import best_nights, month_nights
    from .localtime import from_local_naive, to_local

    out = []
    y, m = to_local(start).year, to_local(start).month
    last = (to_local(end).year, to_local(end).month)
    while (y, m) <= last:
        best = best_nights(month_nights(engine, y, m))
        # agrupa noites consecutivas
        groups: list[list] = []
        for n in best:
            if groups and (n.date - groups[-1][-1].date).days == 1:
                groups[-1].append(n)
            else:
                groups.append([n])
        for g in groups:
            first = from_local_naive(dt.datetime.combine(g[0].date, dt.time(18))).astimezone(UTC)
            lastn = from_local_naive(dt.datetime.combine(g[-1].date, dt.time(18))).astimezone(UTC)
            if not (start <= first <= end):
                continue
            hours = max(n.moonless_hours for n in g)
            title = ("Noite escura" if len(g) == 1 else f"{len(g)} noites escuras seguidas")
            out.append(SkyEvent(first, "noite", title,
                                f"Até {num(hours)} h de noite astronômica sem a Lua.",
                                lastn + dt.timedelta(hours=12), 2 if len(g) > 2 else 1))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def season_events(engine, start, end) -> list[SkyEvent]:
    from skyfield import almanac

    t, y = almanac.find_discrete(engine.ts.from_datetime(start),
                                 engine.ts.from_datetime(end),
                                 almanac.seasons(engine.eph))
    south = engine.site is not None and engine.topos.latitude.degrees < 0
    names_n = {0: "Equinócio de março: início da primavera",
               1: "Solstício de junho: início do verão",
               2: "Equinócio de setembro: início do outono",
               3: "Solstício de dezembro: início do inverno"}
    names_s = {0: "Equinócio de março: início do outono",
               1: "Solstício de junho: início do inverno",
               2: "Equinócio de setembro: início da primavera",
               3: "Solstício de dezembro: início do verão"}
    names = names_s if south else names_n
    return [SkyEvent(ti.utc_datetime(), "estacao", names[int(yi)],
                     "No hemisfério " + ("sul." if south else "norte."))
            for ti, yi in zip(t, y)]


SOURCES = {
    "lua": lambda e, s, f, o: moon_phase_events(e, s, f) + moon_events(e, s, f),
    "eclipse": lambda e, s, f, o: eclipse_events(e, s, f),
    "planeta": lambda e, s, f, o: planet_events(e, s, f),
    "encontro": lambda e, s, f, o: conjunction_events(e, s, f),
    "ocultacao": lambda e, s, f, o: occultation_events(e, s, f, o.get("occ_mag", 4.5)),
    "meteoros": lambda e, s, f, o: meteor_events(e, s, f),
    "noite": lambda e, s, f, o: dark_night_events(e, s, f),
    "estacao": lambda e, s, f, o: season_events(e, s, f),
}

_CACHE: dict = {}


def compute_events(engine, start: dt.datetime, end: dt.datetime,
                   categories=None, min_importance: int = 1,
                   occ_mag: float = 4.5, use_cache: bool = True) -> list[SkyEvent]:
    """Eventos do período, ordenados, sem duplicatas (pelo UID)."""
    start, end = _aware(start), _aware(end)
    cats = list(categories) if categories is not None else list(SOURCES)
    loc = (round(engine.topos.latitude.degrees, 3),
           round(engine.topos.longitude.degrees, 3)) if engine.site is not None else None
    out: list[SkyEvent] = []
    for cat in cats:
        key = (cat, loc, start, end, occ_mag)
        if use_cache and key in _CACHE:
            evs = _CACHE[key]
        else:
            evs = SOURCES[cat](engine, start, end, {"occ_mag": occ_mag})
            if use_cache:
                if len(_CACHE) > 64:
                    _CACHE.clear()
                _CACHE[key] = evs
        out.extend(evs)
    seen, uniq = set(), []
    for ev in sorted(out, key=lambda e: (e.start_utc, e.category, e.title)):
        if ev.uid in seen or ev.importance < min_importance:
            continue
        seen.add(ev.uid)
        uniq.append(ev)
    return uniq


def month_range(year: int, month: int) -> tuple[dt.datetime, dt.datetime]:
    """Início e fim do mês no fuso do observador, em UTC."""
    from .localtime import from_local_naive

    start = from_local_naive(dt.datetime(year, month, 1)).astimezone(UTC)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    end = from_local_naive(dt.datetime(ny, nm, 1)).astimezone(UTC)
    return start, end


def events_on(events: list[SkyEvent], day: dt.date) -> list[SkyEvent]:
    """Eventos cujo início (ou intervalo) cai na data local ``day``."""
    from .localtime import to_local

    out = []
    for ev in events:
        a = to_local(ev.start_utc).date()
        b = to_local(ev.end_utc).date() if ev.end_utc else a
        if a <= day <= b:
            out.append(ev)
    return out


# --------------------------------------------------------------------------
# lembretes (guardados no carina.sqlite, perfis kind='reminder')
REMINDER_KIND = "reminder"


def add_reminder(ev: SkyEvent, data=None) -> None:
    from . import userdata

    db = data if data is not None else userdata.get()
    db.save_profile(REMINDER_KIND, ev.uid, {
        "title": ev.title, "category": ev.category, "detail": ev.detail,
        "start": ev.start_utc.isoformat(),
        "end": ev.end_utc.isoformat() if ev.end_utc else None,
    })


def remove_reminder(uid: str, data=None) -> None:
    from . import userdata

    db = data if data is not None else userdata.get()
    db.delete_profile(REMINDER_KIND, uid)


def reminders(data=None) -> list[SkyEvent]:
    from . import userdata

    db = data if data is not None else userdata.get()
    out = []
    for uid in db.profiles(REMINDER_KIND):
        d = db.profile(REMINDER_KIND, uid) or {}
        try:
            ev = SkyEvent(dt.datetime.fromisoformat(d["start"]), d.get("category", "lua"),
                          d["title"], d.get("detail", ""),
                          dt.datetime.fromisoformat(d["end"]) if d.get("end") else None)
        except (KeyError, ValueError, TypeError):
            continue
        out.append(ev)
    out.sort(key=lambda e: e.start_utc)
    return out


def is_reminded(ev: SkyEvent, data=None) -> bool:
    from . import userdata

    db = data if data is not None else userdata.get()
    return db.profile(REMINDER_KIND, ev.uid) is not None


def due_reminders(now: dt.datetime, hours: float = 36.0, data=None) -> list[SkyEvent]:
    """Lembretes que começam nas próximas ``hours`` horas (ou em curso)."""
    now = _aware(now)
    limit = now + dt.timedelta(hours=hours)
    return [ev for ev in reminders(data)
            if ev.start_utc <= limit and (ev.end_utc or ev.start_utc + dt.timedelta(hours=3)) >= now]


def purge_old_reminders(now: dt.datetime, data=None) -> int:
    now = _aware(now)
    n = 0
    for ev in reminders(data):
        if (ev.end_utc or ev.start_utc) < now - dt.timedelta(days=2):
            remove_reminder(ev.uid, data)
            n += 1
    return n
