"""Testes da v0.12: maratonas expandidas, cidades/fuso, filtro de
magnitude como teto e acervo de equipamentos."""

import datetime as dt
import json
import math
import tempfile
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"
DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


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


# --- base de cidades ------------------------------------------------------

def test_cities_database():
    """A base embarcada precisa ter as cotas pedidas e campos completos."""
    cities = json.loads((DATA / "cities.json").read_text(encoding="utf-8"))
    assert len(cities) >= 700
    names = {c["n"] for c in cities}
    for expected in ("Tokyo", "Rio de Janeiro", "Beijing", "Paris",
                     "New York City", "Manaus"):
        assert expected in names, f"{expected} deveria estar na base"
    for c in cities[:50]:
        assert -90 <= c["lat"] <= 90 and -180 <= c["lon"] <= 180
        assert c["tz"] and "/" in c["tz"]      # nome IANA (Area/Cidade)
        assert c["c"], "país vazio"
    # cotas regionais (sem duplicar): pelo menos 100 de cada
    from collections import Counter

    por_pais = Counter(c["cc"] for c in cities)
    assert por_pais["BR"] >= 100
    assert por_pais["US"] >= 100
    assert por_pais["CN"] >= 100


def test_cities_timezones_resolve():
    """Todos os fusos da base devem existir na tzdata embarcada."""
    from zoneinfo import ZoneInfo

    cities = json.loads((DATA / "cities.json").read_text(encoding="utf-8"))
    for c in cities:
        ZoneInfo(c["tz"])  # lança se o fuso não existir


# --- hora local do observador --------------------------------------------

def test_localtime_follows_observer():
    from carina.core.localtime import (
        from_local_naive, set_timezone, timezone_name, to_local,
    )

    try:
        set_timezone("Asia/Tokyo")
        assert timezone_name() == "Asia/Tokyo"
        noon_utc = dt.datetime(2026, 8, 24, 12, 0, tzinfo=dt.timezone.utc)
        assert to_local(noon_utc).hour == 21          # UTC+9
        naive = dt.datetime(2026, 8, 24, 21, 0)
        assert from_local_naive(naive).astimezone(
            dt.timezone.utc
        ).hour == 12
    finally:
        set_timezone("America/Sao_Paulo")


def test_engine_sets_timezone(engine):
    from carina.config import ObserverLocation
    from carina.core.localtime import set_timezone, timezone_name

    try:
        engine.set_location(ObserverLocation(
            name="Tóquio", latitude=35.68, longitude=139.69,
            timezone="Asia/Tokyo",
        ))
        assert timezone_name() == "Asia/Tokyo"
    finally:
        engine.set_location(ObserverLocation())
        set_timezone("America/Sao_Paulo")


# --- filtro de magnitude como teto ---------------------------------------

def test_mag_cap_is_ceiling_not_forcing():
    """cap 8: campo aberto segue o automático (<8); fechado para em 8."""
    import math as m

    from carina.ui.skywidget import SkyWidget

    class Fake:
        bortle = 1
        mag_cap = 8.0
        BORTLE_NELM = SkyWidget.BORTLE_NELM

        class camera:
            fov = m.radians(100.0)

    f = Fake()
    wide = SkyWidget._mag_limit(f)
    auto_wide = min(13.5, 6.8 + 5.0 * m.log10(90.0 / 100.0))
    assert wide == pytest.approx(auto_wide), "campo aberto: manda o auto"
    assert wide < 8.0

    f.camera.fov = m.radians(2.0)
    assert SkyWidget._mag_limit(f) == pytest.approx(8.0), "teto em 8"

    f.mag_cap = None
    f.camera.fov = m.radians(1.0)
    assert SkyWidget._mag_limit(f) > 12.0  # auto sem teto vai além


# --- cone de visada dos pré-filtros (B-019) -------------------------------

@pytest.mark.parametrize("fov_deg", [100.0, 60.0, 20.0, 5.0, 1.0, 0.3])
@pytest.mark.parametrize("size", [(1250, 820), (2560, 1080), (900, 1200),
                                  (3840, 1080)])
def test_view_cone_covers_screen_corners(fov_deg, size):
    """O cone dos pré-filtros precisa alcançar o CANTO da tela.

    Regressão do B-019: estimar o raio a partir do campo de visão
    (que é o vertical) recortava o céu num círculo inscrito e deixava
    os cantos sem estrelas — muito visível em telas panorâmicas.
    """
    import numpy as np

    from carina.core.projection import Camera

    cam = Camera(fov=math.radians(fov_deg))
    cam.set_viewport(*size)
    cone = cam.max_view_angle(64.0)

    # ângulo real dos quatro cantos, pela inversa da projeção
    for px, py in ((0.0, 0.0), (size[0], 0.0), (0.0, size[1]), size):
        v = cam.unproject(float(px), float(py))
        real = math.acos(max(-1.0, min(1.0, float(np.dot(v, cam._basis[2])))))
        assert cone >= min(real, math.radians(120.0)) - 1e-9, (
            f"cone {math.degrees(cone):.1f}° não cobre o canto "
            f"a {math.degrees(real):.1f}° (fov {fov_deg}°, tela {size})"
        )


def test_view_cone_still_filters_when_zoomed_in():
    """O cone precisa continuar ESTREITO em zoom — é o que dá o ganho."""
    from carina.core.projection import Camera

    cam = Camera(fov=math.radians(2.0))
    cam.set_viewport(1600, 900)
    assert math.degrees(cam.max_view_angle(64.0)) < 6.0


# --- maratonas expandidas -------------------------------------------------

def _build(engine, catalogs, kind, minutes=4):
    from carina.core.observing import build_marathon

    dso, stars, const = catalogs
    start = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    return build_marathon(engine, dso, stars, kind, start, const,
                          minutes_per_object=minutes)


@pytest.mark.parametrize("kind,expected_class", [
    ("OC", {"OC"}), ("GC", {"GC"}), ("NEB", {"NEB", "PN"}),
    ("DARK", {"DARK"}),
])
def test_thematic_marathons(engine, catalogs, kind, expected_class):
    plan = _build(engine, catalogs, kind)
    assert len(plan.entries) >= 20
    assert {e.klass for e in plan.entries} <= expected_class


def test_best_of_night_includes_planets_and_spans_night(engine, catalogs):
    plan = _build(engine, catalogs, "BEST")
    assert plan.title == "Melhores Objetos da Noite"
    klasses = {e.klass for e in plan.entries}
    assert "PLANET" in klasses, "algum planeta visível deveria entrar"
    # roteiro de noite inteira: o último alvo cai na segunda metade
    mid = plan.night_start + (plan.night_end - plan.night_start) / 2
    assert plan.entries[-1].when_utc > mid
    # instruções específicas de planeta presentes
    planet = next(e for e in plan.entries if e.klass == "PLANET")
    assert planet.what_to_see and len(planet.what_to_see) > 30


def test_minutes_per_object_controls_pacing(engine, catalogs):
    """Com 10 min por objeto o roteiro termina bem mais tarde que com 3."""
    fast = _build(engine, catalogs, "M", minutes=3)
    slow = _build(engine, catalogs, "M", minutes=10)
    assert fast.minutes_per_object == 3
    assert slow.minutes_per_object == 10
    assert slow.entries[-1].when_utc > fast.entries[-1].when_utc


def test_marathon_guides_feed_finder_charts(engine, catalogs):
    """As estrelas-guia devem existir e casar com o texto de star-hopping."""
    plan = _build(engine, catalogs, "M")
    with_guides = [e for e in plan.entries if e.guides]
    assert len(with_guides) > len(plan.entries) * 0.8
    e = with_guides[0]
    g = e.guides[0]
    assert set(g) >= {"name", "ra", "dec", "mag", "sep"}
    assert g["name"].split()[0] in e.how_to_find


# --- camadas com efeitos ligados -----------------------------------------

class _FakeSky:
    """Só o suficiente para exercitar SkyWidget.set_layer sem OpenGL."""

    from carina.ui.skywidget import DEFAULT_LAYERS, SkyWidget

    _GROUND_PAIR = SkyWidget._GROUND_PAIR
    set_layer = SkyWidget.set_layer

    def __init__(self):
        self.layers = dict(self.DEFAULT_LAYERS)
        self.updated = 0

    def update(self):
        self.updated += 1


def test_ground_and_below_horizon_are_one_choice():
    """Solo e "ver abaixo do horizonte" são opostos exatos: um controle."""
    sky = _FakeSky()
    sky.set_layer("ground", True)
    assert sky.layers["ground"] and not sky.layers["below_horizon"]

    sky.set_layer("ground", False)
    assert not sky.layers["ground"] and sky.layers["below_horizon"]

    # mexer pelo outro lado (menu antigo, linha de comando) é coerente
    sky.set_layer("below_horizon", False)
    assert sky.layers["ground"] and not sky.layers["below_horizon"]
    sky.set_layer("below_horizon", True)
    assert not sky.layers["ground"] and sky.layers["below_horizon"]


def test_dso_toggle_carries_images():
    """Desligar o céu profundo leva junto as imagens do levantamento."""
    sky = _FakeSky()
    sky.set_layer("dso", True)
    sky.set_layer("dso_images", True)

    sky.set_layer("dso", False)
    assert not sky.layers["dso_images"], "imagens deveriam sumir junto"

    sky.set_layer("dso", True)
    assert sky.layers["dso_images"], "e voltar ao religar o céu profundo"


def test_dso_toggle_remembers_images_were_off():
    """Se as imagens já estavam desligadas, não devem ligar sozinhas."""
    sky = _FakeSky()
    sky.set_layer("dso", True)
    sky.set_layer("dso_images", False)

    sky.set_layer("dso", False)
    sky.set_layer("dso", True)
    assert not sky.layers["dso_images"]


def test_sidebar_has_single_ground_button():
    """A barra lateral não deve mais ter o botão separado do horizonte."""
    from carina.ui.toolbar import SideToolBar

    keys = [k for k, _tip, _icon in SideToolBar.LAYER_BUTTONS]
    assert "ground" in keys
    assert "below_horizon" not in keys


def test_menu_has_no_separate_below_horizon_entry():
    from carina.ui.mainwindow import _LAYER_ACTIONS

    keys = [k for k, _t, _s, _d in _LAYER_ACTIONS]
    assert "ground" in keys
    assert "below_horizon" not in keys


# --- acervo de equipamentos ----------------------------------------------

def test_equipment_defaults_include_smart_telescopes():
    from carina.catalogs.equipment import DEFAULT_DATA

    tele = {t["name"] for t in DEFAULT_DATA["telescopes"]}
    assert any("Seestar S50" in n for n in tele)
    assert any("Seestar S30 Pro" in n for n in tele)
    cams = {c["name"] for c in DEFAULT_DATA["cameras"]}
    assert any("IMX462" in n for n in cams)
    acc = {a["name"] for a in DEFAULT_DATA["accessories"]}
    assert any("Rotacionador" in n for n in acc)


def test_equipment_migration_merges_new_defaults():
    from carina.catalogs.equipment import DATA_VERSION, EquipmentStore

    tmp = Path(tempfile.mkdtemp()) / "equipamentos.json"
    tmp.write_text(json.dumps({
        "telescopes": [
            {"name": "Meu tubo", "aperture_mm": 100, "focal_mm": 900}
        ],
        "cameras": [], "eyepieces": [], "accessories": [], "mounts": [],
    }), encoding="utf-8")
    store = EquipmentStore(tmp)
    names = [t.name for t in store.items("telescopes")]
    assert "Meu tubo" in names                     # o do usuário sobrevive
    assert any("Seestar" in n for n in names)      # os novos chegam
    assert json.loads(tmp.read_text("utf-8"))["version"] == DATA_VERSION
    # segunda carga não duplica
    again = EquipmentStore(tmp)
    assert len(again.items("telescopes")) == len(names)


def test_seestar_s50_field_matches_spec():
    """O campo do S50 divulgado pelo fabricante é ~1,29° × 0,73°."""
    from carina.catalogs.equipment import (
        Camera, Telescope, compute_camera_fov,
    )

    shape = compute_camera_fov(
        Telescope("Seestar S50", 50, 250),
        Camera("IMX462", 5.57, 3.13, 2.9, 1920, 1080),
    )
    assert math.degrees(shape.width) == pytest.approx(1.28, abs=0.05)
    assert math.degrees(shape.height) == pytest.approx(0.72, abs=0.04)
