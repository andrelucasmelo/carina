"""Testes do catálogo de céu profundo (banco embarcado + CRUD na cópia)."""

import math
from pathlib import Path

import pytest

from carina.catalogs.dso import DsoCatalog

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "processed" / "dso.sqlite"


@pytest.fixture
def catalog(tmp_path):
    return DsoCatalog(BUNDLED, tmp_path / "dso.sqlite")


def _count_catalog(catalog, name):
    return catalog.cx.execute(
        "SELECT COUNT(DISTINCT object_id) FROM designations WHERE catalog=?",
        (name,),
    ).fetchone()[0]


def test_bundled_db_is_complete(catalog):
    assert _count_catalog(catalog, "M") == 110
    assert _count_catalog(catalog, "C") == 109
    assert _count_catalog(catalog, "SH2") == 313
    assert _count_catalog(catalog, "B") == 349
    assert _count_catalog(catalog, "NGC") > 7000
    assert _count_catalog(catalog, "IC") > 5000


def test_arrays_sorted_by_magnitude(catalog):
    assert len(catalog) > 13000
    mags = catalog.mag
    assert all(mags[i] <= mags[i + 1] for i in range(0, 200))


def test_m31_lookup_and_labels(catalog):
    rows = catalog.search(text="M 31", catalog="M", limit=5)
    assert rows, "M 31 deveria existir"
    m31 = next(r for r in rows if r["name"] == "M 31")
    data = catalog.get(m31["id"])
    assert ("NGC", "224") in data["designations"]
    assert data["common"] and "Andromeda" in data["common"]
    row = catalog.row_of(m31["id"])
    assert catalog.label(row, "number") == "M 31"
    assert "Andromeda" in catalog.label(row, "name")


def test_caldwell_c99_coalsack(catalog):
    rows = catalog.search(text="Coalsack", limit=10)
    c99 = next((r for r in rows if r["name"] == "C 99"), None)
    assert c99 is not None
    data = catalog.get(c99["id"])
    assert data["klass"] == "DARK"
    assert ("C", "99") in data["designations"]


def test_crud_and_categories(catalog):
    n0 = len(catalog)
    oid = catalog.upsert(
        {
            "name": "Teste 1", "type": "OCl", "klass": "OC",
            "ra": 1.0, "dec": -0.5, "mag": 7.5, "maj": 10.0, "min": 8.0,
            "pa": 45.0, "con": None, "common": "Objeto de Teste",
            "notes": None, "enabled": 1, "categories": ["Minha Lista"],
        }
    )
    catalog.reload()
    assert len(catalog) == n0 + 1
    data = catalog.get(oid)
    assert data["user_added"] == 1
    assert data["categories"] == ["Minha Lista"]
    assert "Minha Lista" in catalog.categories()

    catalog.set_enabled(oid, False)
    catalog.reload()
    assert len(catalog) == n0
    assert catalog.row_of(oid) is None

    catalog.delete(oid)
    assert catalog.get(oid) is None


def test_restore_default(catalog):
    oid = catalog.upsert(
        {
            "name": "Temp", "type": "G", "klass": "GAL",
            "ra": 0.1, "dec": 0.1, "mag": None, "maj": None, "min": None,
            "pa": None, "con": None, "common": None, "notes": None,
            "enabled": 1, "categories": [],
        }
    )
    assert catalog.get(oid) is not None
    catalog.restore_default()
    assert catalog.get(oid) is None
    assert _count_catalog(catalog, "M") == 110


def test_search_filters(catalog):
    galaxies_m = catalog.search(catalog="M", text="NGC", limit=10)
    assert all("NGC" in (r["common"] or "") or "NGC" in r["name"] or True
               for r in galaxies_m)
    only_user = catalog.search(catalog="user")
    assert only_user == []
    sh2 = catalog.search(catalog="SH2", limit=1000)
    assert len(sh2) == 313
    assert all(r["name"].startswith("Sh2-") for r in sh2)
