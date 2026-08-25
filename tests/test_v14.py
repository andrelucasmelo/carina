"""Testes da v0.13.1: marcadores de hora no rastreamento (B-020),
exportação quadrada e opções de fonte/legenda."""

import datetime as dt
import math
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
def m42():
    """Vetor ICRS de M 42, usado como objeto de teste."""
    import tempfile

    from carina.catalogs.dso import DsoCatalog

    tmp = Path(tempfile.mkdtemp()) / "dso.sqlite"
    dso = DsoCatalog(DATA / "dso.sqlite", tmp)
    row = dso.cx.execute(
        "SELECT id, ra, dec FROM objects WHERE name = 'M 42'"
    ).fetchone()
    cd = math.cos(row["dec"])
    return int(row["id"]), [
        cd * math.cos(row["ra"]), cd * math.sin(row["ra"]), math.sin(row["dec"])
    ]


# --- B-020: marcadores de hora ------------------------------------------

@pytest.mark.parametrize("date", [
    "2026-04-25",   # pôr do sol às 17:31 — o caso que falhava
    "2026-08-25", "2026-01-10", "2026-11-03", "2026-06-15",
])
def test_track_samples_land_on_round_minutes(engine, m42, date):
    """A grade precisa cair em minutos redondos, senão não há marcadores.

    Regressão do B-020: a amostragem era ancorada no INSTANTE do pôr do
    sol, então um ocaso às 17:31 gerava 17:41, 17:51, 18:01… e nenhum
    ponto caía em múltiplo de 30 min — o gráfico ficava sem marcador
    nenhum. Agora a grade é ancorada na hora local cheia.
    """
    from carina.core.localtime import to_local
    from carina.core.tracking import compute_track

    obj_id, icrs = m42
    ref = dt.datetime.fromisoformat(f"{date}T23:00").replace(
        tzinfo=dt.timezone.utc
    )
    result = compute_track(engine, ("dso", obj_id), "M 42", icrs, ref)
    if not result.points:
        pytest.skip("objeto não sobe nesta data")

    minutes = [
        to_local(p.when_utc).hour * 60 + to_local(p.when_utc).minute
        for p in result.points
    ]
    assert [m for m in minutes if m % 30 == 0], (
        f"{date}: nenhum ponto em meia hora cheia — o gráfico ficaria sem "
        f"marcadores (primeiros: {minutes[:6]})"
    )
    assert [m for m in minutes if m % 60 == 0], f"{date}: nenhuma hora cheia"


def test_track_keeps_exact_night_limits(engine, m42):
    """Alinhar a grade não pode encurtar a noite: extremos preservados."""
    from carina.core.tracking import compute_track

    obj_id, icrs = m42
    ref = dt.datetime(2026, 4, 25, 23, 0, tzinfo=dt.timezone.utc)
    result = compute_track(engine, ("dso", obj_id), "M 42", icrs, ref)
    night = result.night
    assert night.sunset is not None
    # o primeiro ponto calculado é o pôr do sol exato (não arredondado)
    first = min(p.when_utc for p in result.points)
    assert first >= night.sunset
    assert (first - night.sunset) < dt.timedelta(minutes=11)


def test_track_samples_are_ordered_and_unique(engine, m42):
    from carina.core.tracking import compute_track

    obj_id, icrs = m42
    ref = dt.datetime(2026, 4, 25, 23, 0, tzinfo=dt.timezone.utc)
    times = [p.when_utc for p in
             compute_track(engine, ("dso", obj_id), "M 42", icrs, ref).points]
    assert times == sorted(times)
    assert len(times) == len(set(times)), "sem instantes repetidos"


# --- opções de fonte e legenda ------------------------------------------

def test_font_scale_multiplies_sizes():
    from carina.ui.track_window import TrackSettings

    s = TrackSettings()
    assert s.font_size(10) == 10.0
    s.font_scale = 1.5
    assert s.font_size(10) == 15.0
    s.font_scale = 0.2                      # nunca some de vez
    assert s.font_size(10) >= 4.0


def test_legend_room_depends_on_position():
    """Cada posição reserva espaço no lado certo (ou nenhum, se oculta)."""
    from carina.ui.track_window import TrackCanvas, TrackSettings

    class _Fake:
        _legend_room = TrackCanvas._legend_room

        def __init__(self, settings):
            self.settings = settings

    s = TrackSettings()
    assert _Fake(s)._legend_room() == {}          # bottom cabe na margem

    s.legend_position = "left"
    assert "left" in _Fake(s)._legend_room()
    s.legend_position = "right"
    assert "right" in _Fake(s)._legend_room()
    s.legend_position = "top"
    assert "top" in _Fake(s)._legend_room()

    s.show_legend = False
    assert _Fake(s)._legend_room() == {}, "oculta não reserva espaço"

    # fonte maior pede mais espaço
    s.show_legend = True
    s.legend_position = "left"
    small = _Fake(s)._legend_room()["left"]
    s.font_scale = 2.0
    assert _Fake(s)._legend_room()["left"] > small


def test_legend_items_follow_color_options():
    from carina.ui.track_window import TrackCanvas, TrackSettings

    class _Fake:
        _legend_items = TrackCanvas._legend_items

        def __init__(self, settings):
            self.settings = settings

    s = TrackSettings()
    full = len(_Fake(s)._legend_items())
    s.use_alt_colors = False
    fewer = len(_Fake(s)._legend_items())
    assert fewer == full - 3
    s.use_moon_color = False
    assert len(_Fake(s)._legend_items()) == fewer - 1


def test_track_export_is_square(engine, m42):
    """A carta é redonda: a imagem exportada sai quadrada."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        pytest.skip("sem aplicação Qt de widgets")
    from carina.core.tracking import compute_track
    from carina.ui.track_window import TrackCanvas, TrackSettings

    obj_id, icrs = m42
    ref = dt.datetime(2026, 4, 25, 23, 0, tzinfo=dt.timezone.utc)
    result = compute_track(engine, ("dso", obj_id), "M 42", icrs, ref)

    canvas = TrackCanvas(result, TrackSettings(), "Teste")
    canvas.resize(1000, 700)
    side = float(max(canvas.width(), canvas.height()))
    pix = QPixmap(int(side), int(side))
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    canvas.render_to(painter, QRectF(0.0, 0.0, side, side))
    painter.end()

    assert pix.width() == pix.height() == int(side)
    # o desenho tem de ocupar a área: a borda inferior não pode ficar vazia
    band = pix.toImage()
    painted = sum(
        1 for x in range(0, int(side), 7)
        if band.pixelColor(x, int(side * 0.92)).lightness() > 40
    )
    assert painted > 0, "a faixa inferior do quadrado deveria ter conteúdo"


# --- B-021: altitude máxima da noite -------------------------------------

@pytest.fixture(scope="module")
def m42_vec(m42):
    import numpy as np

    return np.asarray(m42[1], dtype=np.float64)


def test_max_altitude_matches_transit_exactly(engine, m42_vec):
    """A máxima da noite tem de bater com uma varredura fina.

    Regressão do B-021: a máxima era amostrada de hora em hora a partir
    do pôr do sol. Como o trânsito desliza ~4 min/dia, quase nunca caía
    numa amostra — o erro variava erraticamente até ~1,5°, criando
    quedas no meio de uma rampa que deveria ser suave.
    """
    import math

    from carina.core.twilight import night_info
    from carina.ui.object_window import yearly_altitude

    def alt_at(when):
        m = engine.horizontal_matrix(engine.ts.from_datetime(when))
        v = m42_vec @ m.T
        return math.degrees(math.asin(max(-1.0, min(1.0, float(v[2])))))

    start = dt.datetime(2026, 1, 5, 12, 0, tzinfo=dt.timezone.utc)
    dates, _mid, alt_max = yearly_altitude(engine, m42_vec, start,
                                           step_days=30)
    day = start
    for value in alt_max:
        info = night_info(engine, day)
        if info.sunset and info.sunrise:
            total = int((info.sunrise - info.sunset).total_seconds())
            fine = max(
                alt_at(info.sunset + dt.timedelta(seconds=s))
                for s in range(0, total + 1, 30)
            )
            fine = max(fine, alt_at(info.sunrise))
            assert abs(fine - value) < 0.05, (
                f"{day:%d/%m}: máxima {value:.3f}° destoa da varredura "
                f"fina {fine:.3f}°"
            )
        day += dt.timedelta(days=30)


def test_max_altitude_curve_is_smooth(engine, m42_vec):
    """Sem saltos bruscos: a curva anual varia devagar entre amostras."""
    from carina.ui.object_window import yearly_altitude

    start = dt.datetime(2026, 1, 5, 12, 0, tzinfo=dt.timezone.utc)
    _dates, _mid, alt_max = yearly_altitude(engine, m42_vec, start)
    jumps = [abs(b - a) for a, b in zip(alt_max, alt_max[1:])]
    # 10 dias mudam o horário do trânsito em ~40 min: a máxima pode cair
    # bastante quando ele sai da noite, mas nunca dar um salto absurdo
    assert max(jumps) < 12.0, f"salto de {max(jumps):.1f}° entre amostras"


def test_max_altitude_never_below_midnight_altitude(engine, m42_vec):
    """A máxima da noite não pode ser menor que a altitude do meio dela."""
    from carina.ui.object_window import yearly_altitude

    start = dt.datetime(2026, 1, 5, 12, 0, tzinfo=dt.timezone.utc)
    _dates, mid, alt_max = yearly_altitude(engine, m42_vec, start)
    for m, mx in zip(mid, alt_max):
        assert mx >= m - 0.05, f"máxima {mx:.2f}° < meio da noite {m:.2f}°"


def test_transit_time_is_near_maximum(engine, m42_vec):
    """O instante calculado do trânsito é mesmo onde a altitude é máxima."""
    import math

    from carina.ui.object_window import _transit_time

    ra_hours = (math.degrees(math.atan2(m42_vec[1], m42_vec[0])) / 15.0) % 24.0
    near = dt.datetime(2026, 1, 15, 3, 0, tzinfo=dt.timezone.utc)
    transit = _transit_time(engine, ra_hours, near)
    assert abs((transit - near).total_seconds()) < 12 * 3600

    def alt_at(when):
        m = engine.horizontal_matrix(engine.ts.from_datetime(when))
        v = m42_vec @ m.T
        return math.degrees(math.asin(max(-1.0, min(1.0, float(v[2])))))

    peak = alt_at(transit)
    for offset in (-40, -10, 10, 40):
        assert alt_at(transit + dt.timedelta(minutes=offset)) <= peak + 1e-6


# --- B-022: imagem duplicada ---------------------------------------------

def test_info_html_can_omit_embedded_image(engine, m42):
    """Quem já mostra a imagem grande pede a ficha sem a miniatura."""
    import tempfile

    from carina.catalogs import skygeometry
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.ui.infopanel import build_info_html

    obj_id, _icrs = m42
    tmp = Path(tempfile.mkdtemp()) / "dso.sqlite"
    dso = DsoCatalog(DATA / "dso.sqlite", tmp)
    stars = StarCatalog(DATA)
    const = {c["id"]: c for c in skygeometry.load_constellation_info(DATA)}
    selection = ("dso", obj_id)

    with_img = build_info_html(selection, engine, stars, const, dso)
    without = build_info_html(selection, engine, stars, const, dso,
                              include_image=False)
    assert "<img" in with_img, "o painel lateral mantém a miniatura"
    assert "<img" not in without, "a ficha da janela de detalhes não"
    # o resto do conteúdo continua lá
    assert "M 42" in without and "Magnitude" in without


# --- ícone do aplicativo -------------------------------------------------

def test_app_icon_path_tolerates_absence(tmp_path, monkeypatch):
    """Sem ícone gerado, o aplicativo segue com o do sistema.

    O ``.ico`` é produzido por ``scripts/build_icon.py`` a partir de
    ``assets/`` e não é versionado — quem clona o repositório roda o
    programa antes de gerá-lo, e isso não pode quebrar a inicialização.
    """
    from carina import config

    monkeypatch.setattr(config, "package_data_dir", lambda: tmp_path)
    assert config.app_icon_path() is None

    (tmp_path / "icon.png").write_bytes(b"x")
    assert config.app_icon_path().name == "icon.png"

    # o .ico tem precedência: é o formato que o Windows usa
    (tmp_path / "icon.ico").write_bytes(b"x")
    assert config.app_icon_path().name == "icon.ico"
