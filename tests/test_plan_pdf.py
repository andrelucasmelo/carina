"""PDF v2 do roteiro (v0.15 T13): páginas, tema escuro, CSV e texto."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EPHEM = ROOT / "data" / "ephemeris"
DATA = ROOT / "data" / "processed"
NIGHT = dt.datetime(2026, 10, 3, 1, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def plan_and_stars(tmp_path_factory):
    if not (EPHEM / "de440s.bsp").exists() or not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs import skygeometry
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine
    from carina.core.observing import PlanSettings, build_marathon

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    tmp = tmp_path_factory.mktemp("pdf")
    shutil.copy2(DATA / "dso.sqlite", tmp / "dso.sqlite")
    dso = DsoCatalog(DATA / "dso.sqlite", tmp / "dso.sqlite")
    stars = StarCatalog(DATA)
    plan = build_marathon(e, dso, stars, "GC", NIGHT, {},
                          settings=PlanSettings(max_objects=6))
    plan.location = "Rio de Janeiro"
    yield plan, stars, skygeometry.load_constellation_lines(DATA)
    dso.cx.close()


def _render(path, page):
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    doc.load(str(path))
    return doc.pageCount(), doc.render(page, QSize(310, 438))


def test_pdf_pages_and_themes(plan_and_stars, tmp_path):
    from carina.ui.plan_pdf import write_plan_pdf

    plan, stars, lines = plan_and_stars
    light = tmp_path / "claro.pdf"
    dark = tmp_path / "escuro.pdf"
    assert write_plan_pdf(str(light), plan, stars, lines)
    assert write_plan_pdf(str(dark), plan, stars, lines, theme="dark")
    n_light, img_light = _render(light, 1)
    n_dark, img_dark = _render(dark, 1)
    assert n_light >= 3 and n_light == n_dark          # capa + checklist + cartões
    corner_light = img_light.pixelColor(4, 4)
    corner_dark = img_dark.pixelColor(4, 4)
    assert corner_light.alpha() == 0 or corner_light.lightness() > 200   # papel
    assert corner_dark.alpha() == 255 and corner_dark.lightness() < 40
    _n, red = _render(tmp_path / "x.pdf", 0) if write_plan_pdf(
        str(tmp_path / "x.pdf"), plan, stars, lines, theme="red") else (0, None)
    c = red.pixelColor(4, 4)
    assert c.red() < 30 and c.green() < 30 and c.blue() < 30


def test_overview_chart_numbers_targets(plan_and_stars):
    from carina.ui.finderchart import render_overview_chart

    plan, stars, lines = plan_and_stars
    img = render_overview_chart(plan, stars, lines, size_px=600, theme="light")
    assert img.width() == 600
    # há pixels vermelhos (marcas dos alvos) no tema claro
    reds = sum(1 for x in range(0, 600, 3) for y in range(0, 600, 3)
               if img.pixelColor(x, y).red() > 150 and img.pixelColor(x, y).green() < 90)
    assert reds > 10


def test_csv_and_text(plan_and_stars):
    from carina.ui.plan_pdf import CSV_COLUMNS, plan_to_csv, plan_to_text

    plan, _s, _l = plan_and_stars
    lines = plan_to_csv(plan).strip().splitlines()
    assert lines[0].split(";") == CSV_COLUMNS
    assert len(lines) == len(plan.entries) + 1
    first = lines[1].split(";")
    assert first[0] == "1" and first[2] == plan.entries[0].designation
    assert "," in first[5] or first[5] == ""            # vírgula decimal
    text = plan_to_text(plan)
    assert plan.title in text and plan.entries[0].label in text
