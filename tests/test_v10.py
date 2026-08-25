"""Testes das funcionalidades da v0.10: catálogos extras, Bortle, nomes de
constelações, caminho dos planetas e altitude anual."""

import datetime as dt
import math
from pathlib import Path

import pytest

from carina.catalogs.constnames import CONSTELLATIONS, label_for
from carina.catalogs.dso import ALL_CATALOGS, EXTRA_CATALOGS, DsoCatalog

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "processed" / "dso.sqlite"
EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"


@pytest.fixture
def catalog(tmp_path):
    return DsoCatalog(BUNDLED, tmp_path / "dso.sqlite")


@pytest.fixture(scope="module")
def engine():
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride não disponível")
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    return e


# --- catálogos extras -----------------------------------------------------

def test_extra_catalogs_present(catalog):
    for cat, minimum in (("LDN", 1500), ("VdB", 150), ("Abell", 2500),
                         ("Cr", 150)):
        n = catalog.cx.execute(
            "SELECT COUNT(DISTINCT object_id) c FROM designations"
            " WHERE catalog = ?", (cat,),
        ).fetchone()["c"]
        assert n >= minimum, f"{cat} tem apenas {n} objetos"


def test_extra_catalogs_hidden_by_default(catalog):
    for cat in EXTRA_CATALOGS:
        assert cat not in catalog.visible_catalogs
    assert set(ALL_CATALOGS) - set(EXTRA_CATALOGS) <= catalog.visible_catalogs


def test_enabling_extra_catalog_adds_objects(catalog):
    before = len(catalog)
    catalog.set_catalog_visible("Abell", True)
    assert len(catalog) > before
    catalog.set_catalog_visible("Abell", False)
    assert len(catalog) == before


# --- nomes de constelações ------------------------------------------------

def test_constellation_names_complete():
    assert len(CONSTELLATIONS) == 88
    assert label_for("Cru", "pt") == "Cruzeiro do Sul"
    assert label_for("Cru", "latin") == "Crux"
    assert label_for("Cru", "abbr") == "Cru"
    assert label_for("Sco", "pt") == "Escorpião"


# --- Bortle ---------------------------------------------------------------

def test_bortle_scale_monotonic():
    from carina.ui.skywidget import SkyWidget

    nelm = SkyWidget.BORTLE_NELM
    glow = SkyWidget.BORTLE_GLOW
    assert sorted(nelm, reverse=True) == list(range(9, 0, -1))
    for i in range(1, 9):
        assert nelm[i] > nelm[i + 1], "magnitude-limite deve cair com Bortle"
        assert glow[i] < glow[i + 1], "brilho do céu deve subir com Bortle"
    assert glow[1] == 0.0


# --- estrelas profundas ---------------------------------------------------

def test_deep_star_catalog_loaded():
    from carina.catalogs.stars import StarCatalog
    from carina.config import package_data_dir

    cat = StarCatalog(package_data_dir())
    if cat.deep_xyz is None:
        pytest.skip("catálogo profundo não gerado")
    assert len(cat.deep_mag) > 500_000
    assert cat.deep_mag.max() <= 12.01
    assert cat.deep_mag.min() >= 8.4
    # ordenado por magnitude: o corte é um prefixo
    n10 = cat.deep_count_brighter_than(10.0)
    assert 0 < n10 < len(cat.deep_mag)
    assert cat.deep_mag[n10 - 1] <= 10.0


# --- caminho dos planetas -------------------------------------------------

def test_mars_opposition_2027(engine):
    from carina.core.planetpath import compute_path

    start = dt.datetime(2026, 8, 25, tzinfo=dt.timezone.utc)
    path = compute_path(engine, "Marte", start, days=365)
    opos = [e for e in path.events if e.kind == "oposicao"]
    assert len(opos) == 1
    # oposição canônica de Marte: 19–20 de fevereiro de 2027
    assert opos[0].when_utc.date() == dt.date(2027, 2, 20)
    assert opos[0].value > 170
    assert len(path.points) == 366
    assert len(path.marks) > 20


def test_venus_elongations(engine):
    from carina.core.planetpath import compute_path

    start = dt.datetime(2026, 8, 25, tzinfo=dt.timezone.utc)
    path = compute_path(engine, "Vênus", start, days=365)
    elong = [e for e in path.events if e.kind.startswith("elong")]
    assert elong, "Vênus deve ter ao menos uma elongação máxima no ano"
    # elongação máxima de Vênus fica entre 45° e 47°
    assert all(40 < e.value < 48 for e in elong)


# --- altitude anual -------------------------------------------------------

def test_yearly_altitude_orion(engine):
    from carina.ui.object_window import yearly_altitude

    ra, dec = math.radians(83.82), math.radians(-5.39)   # M42
    icrs = [math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra),
            math.sin(dec)]
    start = dt.datetime(2026, 8, 25, tzinfo=dt.timezone.utc)
    dates, alt_mid, alt_max = yearly_altitude(engine, icrs, start,
                                              step_days=30)
    assert len(dates) == len(alt_mid) == len(alt_max)
    assert all(a <= b + 0.5 for a, b in zip(alt_mid, alt_max))
    # do Rio, Órion culmina alto e o melhor momento é no verão (dez/jan)
    best = dates[max(range(len(alt_mid)), key=lambda i: alt_mid[i])]
    assert best.month in (11, 12, 1, 2)
    assert max(alt_max) > 60
