"""Testes da v0.13: janela configurável, regra do crepúsculo, planos
genéricos (mês/estação/estrelas) e cartas de localização."""

import datetime as dt
import math
import tempfile
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
REF = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride não disponível")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


@pytest.fixture(scope="module")
def catalogs():
    from carina.catalogs import skygeometry
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog

    tmp = Path(tempfile.mkdtemp()) / "dso.sqlite"
    dso = DsoCatalog(DATA / "dso.sqlite", tmp)
    stars = StarCatalog(DATA)
    const = {c["id"]: c for c in skygeometry.load_constellation_info(DATA)}
    return dso, stars, const


# --- janela de observação -------------------------------------------------

def test_window_modes_nest_correctly(engine):
    """Pôr do sol ⊃ crepúsculo civil ⊃ noite astronômica."""
    from carina.core.observing import PlanSettings, resolve_window

    astro = resolve_window(engine, REF, PlanSettings(start_mode="astro",
                                                     end_mode="astro"))
    civil = resolve_window(engine, REF, PlanSettings(start_mode="civil",
                                                     end_mode="civil"))
    sun = resolve_window(engine, REF, PlanSettings(start_mode="sunset",
                                                   end_mode="sunset"))
    assert sun.start < civil.start < astro.start
    assert astro.end < civil.end < sun.end
    # a noite escura é a mesma em qualquer modo (é do céu, não da escolha)
    for w in (astro, civil, sun):
        assert w.dark_start == astro.start
        assert w.dark_end == astro.end


def test_custom_window_uses_observer_clock(engine):
    """Horário fixo é interpretado no fuso do observador."""
    from carina.core.localtime import to_local
    from carina.core.observing import PlanSettings, resolve_window

    s = PlanSettings(start_mode="custom", end_mode="custom",
                     custom_start=dt.time(20, 30), custom_end=dt.time(2, 15))
    w = resolve_window(engine, REF, s)
    assert to_local(w.start).hour == 20 and to_local(w.start).minute == 30
    assert to_local(w.end).hour == 2 and to_local(w.end).minute == 15
    assert w.end > w.start, "fim na madrugada seguinte"


def test_astronomical_window_is_the_default():
    from carina.core.observing import PlanSettings

    d = PlanSettings()
    assert d.start_mode == "astro" and d.end_mode == "astro"


# --- regra do crepúsculo --------------------------------------------------

def _plan(engine, catalogs, kind, **kw):
    from carina.core.observing import PlanSettings, build_marathon

    dso, stars, const = catalogs
    return build_marathon(engine, dso, stars, kind, REF, const,
                          settings=PlanSettings(**kw))


def test_only_bright_objects_during_twilight(engine, catalogs):
    """Fora da noite astronômica só entram objetos bem brilhantes."""
    plan = _plan(engine, catalogs, "M", start_mode="sunset",
                 end_mode="sunset", twilight_mag_limit=5.5)
    twilight = [e for e in plan.entries if e.in_twilight]
    assert twilight, "a janela até o pôr do sol deveria ter trecho claro"
    for e in twilight:
        assert e.magnitude is not None and e.magnitude <= 5.5, (
            f"{e.catalog_id} (mag {e.magnitude}) não deveria estar no "
            f"crepúsculo"
        )


def test_twilight_limit_is_configurable(engine, catalogs):
    """Um limite mais generoso admite mais objetos no céu claro."""
    strict = _plan(engine, catalogs, "M", start_mode="sunset",
                   end_mode="sunset", twilight_mag_limit=4.0)
    loose = _plan(engine, catalogs, "M", start_mode="sunset",
                  end_mode="sunset", twilight_mag_limit=7.0)
    n_strict = len([e for e in strict.entries if e.in_twilight])
    n_loose = len([e for e in loose.entries if e.in_twilight])
    assert n_loose > n_strict


def test_astronomical_window_has_no_twilight_entries(engine, catalogs):
    plan = _plan(engine, catalogs, "M")       # padrão: noite astronômica
    assert not [e for e in plan.entries if e.in_twilight]


# --- planos genéricos -----------------------------------------------------

def test_season_depends_on_hemisphere():
    """A mesma data é inverno no sul e verão no norte."""
    from carina.core.observing import season_of

    south, months_s = season_of(REF, -22.9)     # Rio de Janeiro
    north, months_n = season_of(REF, 48.8)      # Paris
    assert south == "Inverno" and north == "Verão"
    assert months_s == months_n, "o trimestre é o mesmo; muda o nome"


def test_month_plan_objects_stay_visible_all_period(engine, catalogs):
    from carina.core.observing import build_period_plan

    dso, stars, const = catalogs
    plan = build_period_plan(engine, dso, stars, "MONTH", REF, const, -22.9)
    assert not plan.timed, "lista curada não tem horário de parada"
    assert 10 <= len(plan.entries) <= 40
    assert plan.subtitle and "agosto" in plan.subtitle
    for e in plan.entries:
        assert e.altitude >= 20.0
        assert e.instrument in ("olho", "binoculo", "pequeno", "medio")
        assert e.note, "deve explicar por que o objeto está na lista"


def test_curated_lists_skip_non_showpieces(engine, catalogs):
    """Novas, duplicatas e entradas sem designação útil ficam de fora."""
    from carina.core.observing import build_period_plan

    dso, stars, const = catalogs
    plan = build_period_plan(engine, dso, stars, "SEASON", REF, const, -22.9)
    for e in plan.entries:
        assert e.type_label not in ("Nova", "Duplicata")
        assert not e.catalog_id.startswith("MWSC")


def test_bright_stars_are_sorted_and_naked_eye(engine, catalogs):
    from carina.core.observing import build_bright_stars

    _dso, stars, const = catalogs
    plan = build_bright_stars(engine, stars, REF, const)
    assert len(plan.entries) >= 20
    mags = [e.magnitude for e in plan.entries]
    assert mags == sorted(mags), "as mais brilhantes primeiro"
    assert mags[0] < 0, "Sirius/Canopus lideram um céu do sul"
    for e in plan.entries:
        assert e.instrument == "olho"
        assert e.klass == "STAR"
        assert e.constellation


def test_instrument_classification():
    from carina.core.observing import instrument_for

    assert instrument_for(3.0, 100.0) == "olho"      # M45
    assert instrument_for(7.0, 10.0) == "binoculo"   # M13
    assert instrument_for(9.5, 5.0) == "pequeno"
    assert instrument_for(12.0, 2.0) == "medio"
    assert instrument_for(None, 300.0, "DARK") == "binoculo"
    # objeto grande ganha um degrau: brilho espalhado, mas campo largo
    assert instrument_for(6.2, 120.0) == "olho"


# --- cartas de localização ------------------------------------------------

def test_finder_always_gives_more_than_one_reference(engine, catalogs):
    """Uma guia dá direção; duas permitem triangular o campo."""
    from carina.core.observing import build_period_plan

    dso, stars, const = catalogs
    plan = build_period_plan(engine, dso, stars, "MONTH", REF, const, -22.9)
    for e in plan.entries:
        assert len(e.guides) >= 2, f"{e.catalog_id} tem só {len(e.guides)}"
        for g in e.guides:
            assert {"name", "ra", "dec", "mag", "sep", "direction"} <= set(g)
            assert g["sep"] > 0
        assert sum(1 for g in e.guides if g.get("primary")) == 1


def test_finder_text_mentions_degrees_of_each_guide(engine, catalogs):
    from carina.core.observing import build_period_plan

    dso, stars, const = catalogs
    plan = build_period_plan(engine, dso, stars, "MONTH", REF, const, -22.9)
    e = plan.entries[0]
    for g in e.guides:
        assert f"{g['sep']:.1f}°" in e.how_to_find, (
            "a distância de cada referência precisa estar no texto"
        )


def test_finder_chart_renders_with_compass(engine, catalogs):
    """A carta sai com tamanho certo e desenha algo (não fica em branco)."""
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is None:
        pytest.skip("sem QGuiApplication para renderizar")
    from carina.catalogs import skygeometry
    from carina.core.observing import build_period_plan
    from carina.ui.finderchart import render_finder_chart

    dso, stars, const = catalogs
    plan = build_period_plan(engine, dso, stars, "MONTH", REF, const, -22.9)
    lines = skygeometry.load_constellation_lines(DATA)
    img = render_finder_chart(plan.entries[0], stars, lines, size_px=300)
    assert img.width() == 300 and img.height() == 300
    # a rosa fica no canto superior direito: deve haver tinta vermelha lá
    reds = 0
    for x in range(230, 300):
        for y in range(0, 70):
            c = img.pixelColor(x, y)
            if c.red() > 150 and c.green() < 100 and c.blue() < 100:
                reds += 1
    assert reds > 20, "a seta do norte deveria aparecer na rosa"


# --- configuração persistida ---------------------------------------------

def test_plan_settings_roundtrip():
    from carina.core.observing import PlanSettings
    from carina.ui.plan_settings_dialog import load_settings, save_settings

    class _Store:
        def __init__(self):
            self.d = {}

        def value(self, key, default, type_):
            return self.d.get(key, default)

        def set_value(self, key, value):
            self.d[key] = value

    store = _Store()
    original = PlanSettings(
        minutes_per_object=7, start_mode="civil", end_mode="custom",
        custom_start=dt.time(21, 15), custom_end=dt.time(3, 45),
        min_altitude=25.0, twilight_mag_limit=4.5,
    )
    save_settings(store, original)
    back = load_settings(store)
    assert back.minutes_per_object == 7
    assert back.start_mode == "civil" and back.end_mode == "custom"
    assert back.custom_start == dt.time(21, 15)
    assert back.custom_end == dt.time(3, 45)
    assert back.min_altitude == 25.0
    assert math.isclose(back.twilight_mag_limit, 4.5)


def test_plan_settings_clamped():
    from carina.core.observing import PlanSettings

    assert PlanSettings(minutes_per_object=99).clamp().minutes_per_object == 10
    assert PlanSettings(minutes_per_object=1).clamp().minutes_per_object == 3
    assert PlanSettings(min_altitude=99).clamp().min_altitude == 60.0
