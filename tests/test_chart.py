"""Gerador de carta (v0.16 T3): especificação, moldura, atlas, perfis e a
carta de aceite (Órion A4 escura em PDF)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from carina.render.chart_frame import (
    CONTENT_LAYERS, ChartInfo, ChartSpec, compose_page, layout, map_render_size,
    nice_degrees,
)
from carina.render.options import RenderOptions

ROOT = Path(__file__).resolve().parent.parent


def test_spec_to_render_options():
    base = RenderOptions(layers={"stars": True, "atmosphere": True, "moon_zone": True,
                                 "grid_eq": False, "ground": True}, bortle=7, mag_cap=5.0)
    spec = ChartSpec(theme="dark", star_mag=8.0, name_mag=3.0, dso_preset="Tudo")
    spec.layers["grid_eq"] = True
    spec.layers["ground"] = False
    opts = spec.render_options(base)
    assert opts.layers["atmosphere"] is False and opts.layers["moon_zone"] is False
    assert opts.layers["grid_eq"] is True and opts.layers["below_horizon"] is True
    assert opts.layers["star_names"] and opts.layers["dso_names"]
    assert opts.bortle == 1 and opts.mag_fixed == 8.0 and opts.label_mag_cap == 3.0
    assert opts.theme == "dark" and opts.chart_mode is False
    assert ChartSpec(theme="light").render_options(base).chart_mode is True


def test_spec_json_round_trip_and_paper():
    spec = ChartSpec(title="Órion", paper="A3", landscape=False, rotation_deg=30)
    spec.layers["const_bounds"] = True
    back = ChartSpec.from_json(spec.to_json())
    assert back == spec
    assert back.page_mm() == (297.0, 420.0)
    w, h = ChartSpec(paper="A4", dpi=200).page_px()
    assert (w, h) == (2339, 1654)
    # chaves desconhecidas são ignoradas; camadas novas ganham o padrão
    partial = ChartSpec.from_json('{"title": "x", "foo": 1, "layers": {"stars": false}}')
    assert partial.title == "x" and partial.layers["stars"] is False
    assert set(partial.layers) == {k for k, _l, _d in CONTENT_LAYERS}


def test_layout_and_rotation_size():
    spec = ChartSpec()
    lay = layout(spec, 2339, 1654)
    mx, my, mw, mh = lay["map"]
    lx = lay["legend"][0]
    assert mx + mw < lx and my > lay["title"][1]
    w0, h0 = map_render_size(spec, 2339, 1654, 2.0)
    spec.rotation_deg = 30
    w1, h1 = map_render_size(spec, 2339, 1654, 2.0)
    assert w1 == h1 and w1 > max(w0, h0)
    assert nice_degrees(20.0, 150) == 10 and nice_degrees(200.0, 150) == 1


def test_compose_page_draws_frame(qt_app):
    from PySide6.QtGui import QColor, QImage

    spec = ChartSpec(theme="dark", title="Teste")
    W, H = spec.page_px(100)
    lw, lh = map_render_size(spec, W, H, 1.0)
    img = QImage(lw, lh, QImage.Format_RGB32)
    img.fill(QColor(30, 30, 60))
    page = compose_page(img, spec, ChartInfo(location="Rio", px_per_deg=12.0), (W, H))
    assert (page.width(), page.height()) == (W, H)
    lay = layout(spec, W, H)
    lx, ly, lw2, lh2 = (int(v) for v in lay["legend"])
    lit = sum(1 for x in range(lx, lx + lw2, 3) for y in range(ly, ly + lh2 // 2, 3)
              if page.pixelColor(x, y).lightness() > 120)
    assert lit > 20                                   # a legenda foi desenhada
    assert page.pixelColor(2, 2).lightness() < 30     # fundo escuro do tema
    plain = ChartSpec(show_legend=False, show_title=False, show_footer=False)
    assert layout(plain, W, H)["map"][2] > lay["map"][2]


def test_profile_round_trip(tmp_path):
    from carina.core.userdata import UserData

    ud = UserData(tmp_path / "c.sqlite")
    spec = ChartSpec(theme="red", star_mag=7.5)
    import json

    ud.save_profile("chart", "Campo vermelho", json.loads(spec.to_json()))
    back = ChartSpec.from_json(ud.profile("chart", "Campo vermelho"))
    assert back.theme == "red" and back.star_mag == 7.5
    ud.close()


def test_atlas_jobs_from_plan_and_constellations(qt_app):
    import datetime as dt

    from carina.core.observing import PlanSettings, build_marathon
    from carina.ui.chart_dialog import atlas_jobs
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    when = dt.datetime(2026, 10, 3, 1, tzinfo=dt.timezone.utc)
    plan = build_marathon(win.engine, win.dso_catalog, win.star_catalog, "GC", when, {},
                          settings=PlanSettings(max_objects=4))

    class FakePlanWindow:
        pass

    fake = FakePlanWindow()
    fake.plan = plan
    win._track_windows.append(fake)
    jobs = atlas_jobs(win, ChartSpec(fov_deg=15.0), "plan")
    assert len(jobs) == len(plan.entries) == 4
    assert all(s.framing == "object" and s.target.startswith("dso:") for s, _w in jobs)
    assert jobs[0][1] == plan.entries[0].when_utc
    win.engine.time.set_fixed(when)
    consts = atlas_jobs(win, ChartSpec(), "constellations")
    assert consts and all(s.framing == "constellation" for s, _w in consts)
    win.close()


@pytest.mark.skipif(os.environ.get("CARINA_SKIP_GUI") == "1", reason="sem GUI")
def test_acceptance_orion_dark_pdf(tmp_path):
    """Aceite da v0.16: A4 de Órion em tema escuro, com legenda e escala, em PDF."""
    out = tmp_path / "orion.pdf"
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
    env.pop("QT_QPA_PLATFORM", None)
    proc = subprocess.run(
        [sys.executable, "-m", "carina", "--screenshot", str(tmp_path / "t.png"),
         "--size", "640x480", "--at", "2026-12-20T03:00:00Z", "--select", "M 42",
         "--chart-pdf", str(out), "--chart-const", "Ori", "--chart-theme", "dark"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=240)
    assert proc.returncode == 0, proc.stderr[-2000:]
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    doc.load(str(out))
    assert doc.pageCount() == 1
    size = doc.pagePointSize(0)
    assert abs(size.width() / 72 * 25.4 - 297) < 2 and abs(size.height() / 72 * 25.4 - 210) < 2
    page = doc.render(0, QSize(1169, 827))
    assert page.pixelColor(20, 20).lightness() < 40          # tema escuro
    from PySide6.QtGui import QImage

    png = QImage(str(out)[:-4] + ".png")
    lay = layout(ChartSpec(), png.width(), png.height())
    lx, ly, lw, lh = (int(v) for v in lay["legend"])
    lit = sum(1 for x in range(lx, lx + lw, 4) for y in range(ly, ly + lh, 4)
              if png.pixelColor(x, y).lightness() > 120)
    assert lit > 30                                           # legenda presente
