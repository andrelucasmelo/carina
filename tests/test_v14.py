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
