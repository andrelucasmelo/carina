"""Planejamento: seleção dos "Melhores Objetos" sem estrelas/novas nem
nomes repetidos (achado D3 da revisão de 2026-10)."""

import shutil
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


@pytest.fixture(scope="module")
def dso(tmp_path_factory):
    bundled = DATA / "dso.sqlite"
    if not bundled.exists():
        pytest.skip("banco embarcado ausente")
    from carina.catalogs.dso import DsoCatalog

    user = tmp_path_factory.mktemp("dso") / "dso.sqlite"
    shutil.copy2(bundled, user)
    cat = DsoCatalog(bundled, user)
    yield cat
    cat.cx.close()


def test_best_rows_exclude_stars_and_duplicates(dso):
    from carina.core.observing import _NOT_SHOWPIECES, _best_rows

    rows = _best_rows(dso)
    assert 30 <= len(rows) <= 60
    names = {r["name"] for r, _label in rows}
    assert not names & {"NGC 1990", "IC 1318", "NGC 7114", "IC 4816"}
    assert all(r["type"] not in _NOT_SHOWPIECES for r, _l in rows)
    labels = [label.lower() for _r, label in rows]
    assert len(labels) == len(set(labels)), "nome comum repetido no roteiro"
    assert "nebulosa da lagoa" in labels and "grande nebulosa de órion" in labels
