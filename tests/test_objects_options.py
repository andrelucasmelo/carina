"""ObjectRef (referência unificada) e RenderOptions (fotografia do estado
de exibição) — fundações da v0.14 (T13)."""

import shutil
from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


@pytest.fixture(scope="module")
def catalogs(tmp_path_factory):
    if not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog

    user = tmp_path_factory.mktemp("dso") / "dso.sqlite"
    shutil.copy2(DATA / "dso.sqlite", user)
    dso = DsoCatalog(DATA / "dso.sqlite", user)
    yield StarCatalog(DATA), dso
    dso.cx.close()


def test_objectref_resolves_dso_star_and_body(catalogs):
    from carina.core.objects import ObjectRef

    stars, dso = catalogs
    m42 = dso.cx.execute("SELECT id FROM objects WHERE name = 'M 42'").fetchone()["id"]
    ref = ObjectRef.resolve(("dso", m42), stars, dso)
    assert ref.name.startswith("M 42 — ") and ref.is_fixed
    assert abs(np.linalg.norm(ref.icrs) - 1.0) < 1e-9
    assert ref.data["name"] == "M 42"

    idx = int(np.argmin(stars.mag))          # Sírius
    ref = ObjectRef.resolve(("star", idx), stars, dso)
    assert ref.name and ref.is_fixed and ref.data is None

    ref = ObjectRef.resolve(("body", "Lua"), stars, dso)
    assert ref.name == "Lua" and not ref.is_fixed and ref.image_path() is None
    assert ObjectRef.resolve(("dso", 99_999_999), stars, dso) is None
    assert ObjectRef.resolve(None, stars, dso) is None


def test_render_options_round_trip():
    from carina.render.options import RenderOptions

    opts = RenderOptions(layers={"stars": True, "ground": False}, chart_mode=True,
                         bortle=5, mag_cap=7.5, const_label_mode="pt",
                         dso_filter='{"only_mc": true}')
    again = RenderOptions.from_json(opts.to_json())
    assert again == opts
    assert RenderOptions.from_json("lixo") == RenderOptions()
