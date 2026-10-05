"""Tours guiados (v0.20 T1).

Um **tour** é uma sequência de **passos**. Cada passo leva o céu a um
instante, aponta para um alvo com um campo, destaca uma constelação ou um
asterismo e mostra um texto curto. Dois tipos usam o mesmo motor:

- **autorais**: JSON embarcado em ``data/processed/tours/`` (gerado de
  Markdown curado por ``scripts/build_tours.py``);
- **gerados**: montados em Python para a data e o local do usuário
  (``core/tours_generated.py``).

Este módulo não conhece o Qt: :class:`TourRun` resolve os alvos, calcula o
instante de cada passo e decide o que pular (alvo abaixo do horizonte); o
player (``ui/tour_player.py``) só aplica o resultado ao céu.

Regras do relógio do tour (``Tour.when``):

- ``agora`` — o instante da simulação ao iniciar;
- ``inicio_da_noite`` — o fim do crepúsculo náutico desta noite (ou agora,
  se a noite já começou);
- ``hora:HH:MM`` — esta noite, na hora local dada (antes do meio-dia conta
  como madrugada seguinte);
- ``data:MM-DD hora:HH:MM`` — data típica (tours de estação), no ano atual.

Instante de cada passo (``Step.time``): vazio (o do tour), ``+2h``/``-30m``
(deslocamento), ``HH:MM`` (hora local da mesma noite) ou ``melhor`` (melhor
hora do alvo na noite).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

UTC = dt.timezone.utc

CATEGORIES = {
    "iniciante": "Iniciantes — Primeiro céu",
    "intermediario": "Intermediário — Lendo o céu",
    "astrofoto": "Astrofotografia — Planejando a captura",
    "aplicativo": "Aplicativo — O Carina por dentro",
    "extra": "Extras",
}
STEP_KINDS = ("intro", "goto", "highlight", "object", "pause", "fim", "ui")
TARGET_KINDS = ("star", "dso", "body", "const", "asterism", "altaz")
# graus: abaixo disso o alvo "não está no céu" para o passo (por tipo de alvo);
# uma constelação a 3° do horizonte não serve para aprender a figura
SKIP_BELOW = {"const": 10.0, "asterism": 10.0, "dso": 10.0, "star": 5.0, "body": 3.0}
DEFAULT_SKIP_BELOW = 2.0
TOUR_DONE_KIND = "tour_done"      # perfil no carina.sqlite


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

@dataclass
class Step:
    title: str = ""
    text: str = ""                        # Markdown
    kind: str = "goto"
    target: str = ""                      # "star:Betelgeuse", "dso:M 42", "const:Ori"…
    fov: float | None = None              # graus
    time: str = ""                        # "", "+2h", "21:30", "melhor"
    highlight: list[str] = field(default_factory=list)   # "const:Ori", "asterism:bule"
    layers: dict[str, bool] = field(default_factory=dict)
    bortle: int | None = None
    image: str = ""                       # "dss:M 42" ou caminho relativo
    duration_s: float = 20.0
    skip_if_below: float | None = None    # graus; None = padrão
    optional: bool = True                 # pular (True) ou mostrar com aviso
    card: dict | None = None              # dados extras (tours gerados)

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        names = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Tour:
    key: str
    title: str
    category: str = "extra"
    subtitle: str = ""
    level: int = 1
    minutes: int = 10
    when: str = "inicio_da_noite"
    lat_range: tuple[float, float] | None = None    # (mín, máx); fora: aviso
    tags: list[str] = field(default_factory=list)
    author: str = ""
    generated: bool = False
    steps: list[Step] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Tour":
        names = set(cls.__dataclass_fields__) - {"steps"}
        tour = cls(**{k: v for k, v in d.items() if k in names})
        if tour.lat_range is not None:
            tour.lat_range = (float(tour.lat_range[0]), float(tour.lat_range[1]))
        tour.steps = [Step.from_dict(s) for s in d.get("steps", [])]
        return tour

    def to_dict(self) -> dict:
        return asdict(self)

    def targets(self) -> list[str]:
        """Alvos citados (passos e destaques), sem repetição, na ordem."""
        out: list[str] = []
        for s in self.steps:
            for t in [s.target, *s.highlight]:
                if t and t not in out:
                    out.append(t)
        return out


def validate(tour: Tour) -> list[str]:
    """Problemas de esquema (lista vazia = válido). Não resolve alvos."""
    errs = []
    if not tour.key or not re.fullmatch(r"[a-z0-9-]+", tour.key):
        errs.append(f"chave inválida: {tour.key!r}")
    if tour.category not in CATEGORIES:
        errs.append(f"{tour.key}: categoria desconhecida {tour.category!r}")
    if not _WHEN.match(tour.when):
        errs.append(f"{tour.key}: regra de relógio inválida {tour.when!r}")
    if not tour.steps:
        errs.append(f"{tour.key}: sem passos")
    for i, s in enumerate(tour.steps, 1):
        where = f"{tour.key} passo {i}"
        if s.kind not in STEP_KINDS:
            errs.append(f"{where}: tipo {s.kind!r}")
        if not s.title.strip() or not s.text.strip():
            errs.append(f"{where}: sem título ou sem texto")
        for t in [s.target, *s.highlight]:
            if t and t.split(":", 1)[0] not in TARGET_KINDS:
                errs.append(f"{where}: alvo {t!r}")
        if s.time and not _STEP_TIME.match(s.time):
            errs.append(f"{where}: hora {s.time!r}")
        if s.fov is not None and not 0.05 <= float(s.fov) <= 180:
            errs.append(f"{where}: campo {s.fov}")
        if s.bortle is not None and not 1 <= int(s.bortle) <= 9:
            errs.append(f"{where}: Bortle {s.bortle}")
    return errs


_WHEN = re.compile(r"^(agora|inicio_da_noite|hora:\d{1,2}:\d{2}|data:\d{2}-\d{2} hora:\d{1,2}:\d{2})$")
_STEP_TIME = re.compile(r"^([+-]\d+(\.\d+)?[hm]|\d{1,2}:\d{2}|melhor)$")


def load_dir(path: Path) -> list[Tour]:
    """Tours embarcados (``*.json``; arquivos que começam com ``_`` são dados
    auxiliares). Um JSON quebrado é ignorado em vez de derrubar a galeria."""
    tours = []
    if not path.exists():
        return tours
    for f in sorted(path.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            tours.append(Tour.from_dict(json.loads(f.read_text(encoding="utf-8"))))
        except (ValueError, TypeError, KeyError):
            continue
    return tours


def builtin_dir() -> Path:
    from ..config import package_data_dir

    return package_data_dir() / "tours"


# ---------------------------------------------------------------------------
# Resolução de alvos
# ---------------------------------------------------------------------------

GREEK = {
    "alf": "Alp", "alp": "Alp", "alpha": "Alp", "bet": "Bet", "beta": "Bet",
    "gam": "Gam", "gamma": "Gam", "del": "Del", "delta": "Del", "eps": "Eps",
    "zet": "Zet", "zeta": "Zet", "eta": "Eta", "the": "The", "theta": "The",
    "iot": "Iot", "kap": "Kap", "lam": "Lam", "mu": "Mu", "nu": "Nu", "xi": "Xi",
    "omi": "Omi", "pi": "Pi", "rho": "Rho", "sig": "Sig", "tau": "Tau",
    "ups": "Ups", "phi": "Phi", "chi": "Chi", "psi": "Psi", "ome": "Ome",
}


@dataclass
class Resolved:
    spec: str
    kind: str                     # star | dso | body | const | asterism | altaz
    label: str
    selection: tuple | None = None    # seleção do céu (star/dso/body)
    icrs: np.ndarray | None = None    # direção fixa (estrelas, DSO, constelação…)
    body: str | None = None           # corpo do Sistema Solar (posição varia)
    altaz: tuple[float, float] | None = None   # direção horizontal fixa (graus)
    key: str = ""                     # sigla da constelação / chave do asterismo
    size_deg: float = 0.0             # extensão aproximada (campo sugerido)


def _unit(ra: float, dec: float) -> np.ndarray:
    cd = math.cos(dec)
    return np.array([cd * math.cos(ra), cd * math.sin(ra), math.sin(dec)])


class Resolver:
    """Converte os alvos textuais dos passos em direções no céu."""

    def __init__(self, stars, dso, const_info: list[dict] | None = None,
                 asterisms: list[dict] | None = None, bodies=None) -> None:
        from .engine import _BODIES

        self.stars = stars
        self.dso = dso
        self.const_info = {c["id"]: c for c in (const_info or [])}
        self.asterisms = {a["key"]: a for a in (asterisms or [])}
        self.bodies = list(bodies) if bodies is not None else [b[0] for b in _BODIES]
        self._proper = {v.lower(): k for k, v in stars.proper.items()} if stars else {}
        self._cache: dict[str, Resolved | None] = {}

    # -- estrelas ------------------------------------------------------------
    def star_index(self, spec: str) -> int | None:
        """Nome próprio ("Alnilam"), Bayer ("eps Ori", "mu-1 Sco") ou HIP."""
        s = spec.strip()
        if s.lower() in self._proper:
            return self._proper[s.lower()]
        m = re.fullmatch(r"HIP\s*(\d+)", s, re.I)
        if m:
            from .objects import _hip_index

            return _hip_index(self.stars).get(int(m.group(1)))
        m = re.fullmatch(r"([A-Za-z]+)(?:-(\d))?\s+([A-Za-z]{3})", s)
        if m:
            code = GREEK.get(m.group(1).lower())
            if code is None:
                return None
            if m.group(2):
                code = f"{code}-{m.group(2)}"
            con = m.group(3).lower()
            hits = [i for i, b in self.stars.bayer.items()
                    if b == code and self.stars.con.get(i, "").lower() == con]
            if not hits and not m.group(2):
                # "alf Cen" sem número: a componente mais brilhante (−1, −2…)
                hits = [i for i, b in self.stars.bayer.items()
                        if b.split("-")[0] == code
                        and self.stars.con.get(i, "").lower() == con]
            return min(hits) if hits else None     # índices crescem com a magnitude
        return None

    def asterism_vectors(self, key: str) -> list[np.ndarray]:
        a = self.asterisms.get(key)
        if a is None:
            return []
        from .objects import _hip_index

        hip = _hip_index(self.stars)
        out = []
        for line in a.get("lines", []):
            for h in line:
                i = hip.get(int(h))
                if i is not None:
                    out.append(np.asarray(self.stars.xyz[i], np.float64))
        return out

    # -- geral -----------------------------------------------------------------
    def resolve(self, spec: str) -> Resolved | None:
        if spec in self._cache:
            return self._cache[spec]
        r = self._resolve(spec)
        self._cache[spec] = r
        return r

    def _resolve(self, spec: str) -> Resolved | None:
        if ":" not in spec:
            return None
        kind, name = spec.split(":", 1)
        name = name.strip()
        if kind == "star":
            i = self.star_index(name)
            if i is None:
                return None
            label = self.stars.label(int(i), "proper") or name
            return Resolved(spec, "star", label, ("star", int(i)),
                            np.asarray(self.stars.xyz[i], np.float64))
        if kind == "dso":
            row = self.dso.cx.execute(
                "SELECT id, ra, dec, maj, common FROM objects WHERE name = ? COLLATE NOCASE",
                (name,)).fetchone()
            if row is None:
                return None
            from ..catalogs import names as _names

            common = _names.common_label(row["common"]) if row["common"] else ""
            label = f"{name} — {common}" if common else name
            return Resolved(spec, "dso", label, ("dso", int(row["id"])),
                            _unit(float(row["ra"]), float(row["dec"])),
                            size_deg=float(row["maj"] or 0.0) / 60.0)
        if kind == "body":
            if name not in self.bodies:
                return None
            return Resolved(spec, "body", name, ("body", name), body=name)
        if kind == "const":
            c = self.const_info.get(name)
            if c is None:
                return None
            from ..catalogs.constnames import label_for

            return Resolved(spec, "const", label_for(name, "pt", c.get("name", name)),
                            icrs=_unit(math.radians(c["ra"]), math.radians(c["dec"])),
                            key=name)
        if kind == "asterism":
            a = self.asterisms.get(name)
            vecs = self.asterism_vectors(name)
            if a is None or not vecs:
                return None
            v = np.mean(vecs, axis=0)
            v /= np.linalg.norm(v)
            spread = max(math.degrees(math.acos(max(-1.0, min(1.0, float(u @ v)))))
                         for u in vecs)
            return Resolved(spec, "asterism", a["name"], icrs=v, key=name,
                            size_deg=2 * spread)
        if kind == "altaz":
            try:
                az, alt = (float(x) for x in name.split(","))
            except ValueError:
                return None
            return Resolved(spec, "altaz", f"az {az:.0f}°, alt {alt:.0f}°", altaz=(az, alt))
        return None

    def unresolved(self, tour: Tour) -> list[str]:
        return [t for t in tour.targets() if self.resolve(t) is None]


# ---------------------------------------------------------------------------
# Geometria do instante
# ---------------------------------------------------------------------------

def horizontal_vec(engine, target: Resolved, t) -> np.ndarray | None:
    """Vetor horizontal (sem refração) do alvo no instante ``t``."""
    if target.altaz is not None:
        az, alt = (math.radians(x) for x in target.altaz)
        from .projection import altaz_to_vec

        return np.asarray(altaz_to_vec(az, alt), np.float64)
    if target.icrs is not None:
        return np.asarray(engine.horizontal_matrix(t), np.float64) @ target.icrs
    if target.body is not None:
        st = next((b for b in engine.bodies(t) if b.name == target.body), None)
        return None if st is None else np.asarray(st.vec, np.float64)
    return None


def altitude(engine, target: Resolved, t) -> float | None:
    v = horizontal_vec(engine, target, t)
    if v is None:
        return None
    return math.degrees(math.asin(max(-1.0, min(1.0, float(v[2]) / float(np.linalg.norm(v))))))


def default_fov(target: Resolved | None) -> float:
    """Campo sugerido quando o passo não diz: cabe o alvo com folga."""
    if target is None:
        return 60.0
    if target.kind == "const":
        return 45.0
    if target.kind == "asterism":
        return max(15.0, min(100.0, 1.6 * target.size_deg))
    if target.kind == "dso":
        return max(1.0, min(30.0, 3.0 * target.size_deg)) if target.size_deg else 5.0
    if target.kind == "star":
        return 25.0
    if target.kind == "body":
        return 2.0 if target.body not in ("Sol", "Lua") else 3.0
    return 80.0


# ---------------------------------------------------------------------------
# Relógio do tour
# ---------------------------------------------------------------------------

def _local(when: dt.datetime) -> dt.datetime:
    from .localtime import to_local

    return to_local(when)


def _at_local(day: dt.date, hh: int, mm: int, ref_local: dt.datetime) -> dt.datetime:
    """``day`` às HH:MM no fuso do observador (o de ``ref_local``)."""
    if hh < 12:                                   # madrugada: noite de ``day``
        day = day + dt.timedelta(days=1)
    return dt.datetime(day.year, day.month, day.day, hh, mm,
                       tzinfo=ref_local.tzinfo).astimezone(UTC)


def evening_date(now_utc: dt.datetime) -> dt.date:
    """Data local da noite em curso (antes do meio-dia, a da véspera)."""
    lt = _local(now_utc)
    return (lt - dt.timedelta(days=1)).date() if lt.hour < 12 else lt.date()


def base_time(engine, rule: str, now_utc: dt.datetime) -> dt.datetime:
    """Instante de partida do tour pela regra ``Tour.when``."""
    lt = _local(now_utc)
    if rule == "agora":
        return now_utc
    if rule.startswith("hora:"):
        hh, mm = (int(x) for x in rule[5:].split(":"))
        return _at_local(evening_date(now_utc), hh, mm, lt)
    if rule.startswith("data:"):
        m = re.match(r"data:(\d{2})-(\d{2}) hora:(\d{1,2}):(\d{2})", rule)
        mo, d, hh, mm = (int(x) for x in m.groups())
        day = dt.date(lt.year, mo, d)
        return _at_local(day, hh, mm, lt)
    # inicio_da_noite
    from .twilight import night_info

    info = night_info(engine, now_utc)
    dusk, dawn = info.nautical_dusk, info.nautical_dawn
    if dusk is not None and dawn is not None and dusk <= now_utc < dawn:
        return now_utc                                       # a noite já começou
    if dusk is None or now_utc >= (dawn or now_utc):
        # depois do amanhecer (manhã): a noite que vem
        noon = lt.replace(hour=12, minute=1, second=0, microsecond=0)
        if lt.hour >= 12:
            noon += dt.timedelta(days=1)
        info = night_info(engine, noon.astimezone(UTC))
        dusk = info.nautical_dusk
    if dusk is None:                                         # latitudes extremas
        return _at_local(evening_date(now_utc), 21, 0, lt)
    return dusk.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)


def step_time(engine, spec: str, base: dt.datetime, target: Resolved | None) -> dt.datetime:
    """Instante de um passo a partir do do tour."""
    if not spec:
        return base
    if spec[0] in "+-":
        val, unit = float(spec[1:-1]), spec[-1]
        delta = dt.timedelta(hours=val) if unit == "h" else dt.timedelta(minutes=val)
        return base + delta if spec[0] == "+" else base - delta
    if spec == "melhor":
        if target is None or (target.icrs is None and target.body is None):
            return base
        from .visibility import Target, compute_visibility

        tg = Target(icrs=target.icrs) if target.icrs is not None else Target(body=target.body)
        vis = compute_visibility(engine, tg, base, 15.0, refine=False)
        return vis.best_utc or base
    hh, mm = (int(x) for x in spec.split(":"))
    return _at_local(evening_date(base), hh, mm, _local(base))


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

@dataclass
class PreparedStep:
    step: Step
    number: int                       # posição no tour original (1…)
    when: dt.datetime
    target: Resolved | None
    alt: float | None
    below: bool = False               # alvo abaixo do limite (mostrado com aviso)
    highlights: list[Resolved] = field(default_factory=list)

    @property
    def fov(self) -> float:
        return float(self.step.fov) if self.step.fov else default_fov(self.target)


@dataclass
class Skipped:
    number: int
    title: str
    reason: str


class TourRun:
    """Um tour preparado para uma data e um local: passos com instante,
    alvo resolvido e o que foi pulado (e por quê)."""

    def __init__(self, tour: Tour, engine, resolver: Resolver, now_utc: dt.datetime,
                 latitude: float | None = None) -> None:
        self.tour = tour
        self.engine = engine
        self.resolver = resolver
        self.now = now_utc
        self.latitude = latitude
        self.base: dt.datetime | None = None
        self.steps: list[PreparedStep] = []
        self.skipped: list[Skipped] = []
        self.warnings: list[str] = []
        self.index = 0

    def prepare(self) -> "TourRun":
        tour = self.tour
        self.base = base_time(self.engine, tour.when, self.now)
        if tour.lat_range and self.latitude is not None:
            lo, hi = tour.lat_range
            if not lo <= self.latitude <= hi:
                self.warnings.append(
                    "Este tour foi escrito para latitudes entre "
                    f"{_lat_txt(lo)} e {_lat_txt(hi)}; no seu local alguns objetos "
                    "ficam baixos ou não nascem.")
        if tour.when.startswith("data:"):
            today = _local(self.now).date()
            day = _local(self.base).date()
            if abs((day - today).days) > 45:
                self.warnings.append(
                    f"O tour mostra o céu de {day:%d/%m} — a época para a qual foi "
                    "escrito. Ao sair, o relógio volta ao que era.")
        for n, s in enumerate(tour.steps, 1):
            target = self.resolver.resolve(s.target) if s.target else None
            if s.target and target is None:
                self.skipped.append(Skipped(n, s.title, f"alvo desconhecido: {s.target}"))
                continue
            when = step_time(self.engine, s.time, self.base, target)
            t = self.engine.ts.from_datetime(when)
            alt = altitude(self.engine, target, t) if target is not None else None
            limit = (SKIP_BELOW.get(target.kind, DEFAULT_SKIP_BELOW) if target is not None
                     else DEFAULT_SKIP_BELOW) if s.skip_if_below is None else float(s.skip_if_below)
            below = (target is not None and target.kind != "altaz" and alt is not None
                     and alt < limit)
            if below and s.optional and s.kind not in ("intro", "fim"):
                self.skipped.append(Skipped(
                    n, s.title, f"{target.label} está abaixo do horizonte "
                                f"({alt:.0f}°) nesta data e local"))
                continue
            hl = [r for r in (self.resolver.resolve(h) for h in s.highlight) if r is not None]
            self.steps.append(PreparedStep(s, n, when, target, alt, below, hl))
        self.index = 0
        return self

    # -- navegação -------------------------------------------------------------
    @property
    def current(self) -> PreparedStep | None:
        return self.steps[self.index] if 0 <= self.index < len(self.steps) else None

    @property
    def at_end(self) -> bool:
        return self.index >= len(self.steps) - 1

    def next(self) -> PreparedStep | None:
        if self.index < len(self.steps) - 1:
            self.index += 1
        return self.current

    def prev(self) -> PreparedStep | None:
        if self.index > 0:
            self.index -= 1
        return self.current

    def go(self, index: int) -> PreparedStep | None:
        self.index = max(0, min(len(self.steps) - 1, index))
        return self.current

    @property
    def viable_tonight(self) -> bool:
        """Todos os passos com alvo ficaram no céu (nada pulado por altura)."""
        return not any("abaixo do horizonte" in s.reason for s in self.skipped)


def _lat_txt(v: float) -> str:
    return f"{abs(v):.0f}° {'S' if v < 0 else 'N'}"


# ---------------------------------------------------------------------------
# Progresso (carina.sqlite)
# ---------------------------------------------------------------------------

def mark_done(userdata, key: str, when: dt.datetime | None = None) -> None:
    when = when or dt.datetime.now(UTC)
    userdata.save_profile(TOUR_DONE_KIND, key, {"when": when.isoformat()})


def done_keys(userdata) -> set[str]:
    if userdata is None:
        return set()
    return set(userdata.profiles(TOUR_DONE_KIND))
