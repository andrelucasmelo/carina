"""Busca v2 (v0.15 T6): Bayer, constelações, designações e ordem."""

import shutil
from pathlib import Path

import pytest

from carina.core.search import fold, parse_bayer

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


@pytest.mark.parametrize("query,expected", [
    ("alpha ori", ("Alp", "", "Ori")),
    ("α Ori", ("Alp", "", "Ori")),
    ("alf Ori", ("Alp", "", "Ori")),
    ("alfa órion", ("Alp", "", "Ori")),
    ("alpha orionis", ("Alp", "", "Ori")),
    ("beta1 sco", ("Bet", "1", "Sco")),
    ("α1 Cen", ("Alp", "1", "Cen")),
    ("gama do cruzeiro", ("Gam", "", "Cru")),
    ("épsilon canis majoris", ("Eps", "", "CMa")),
])
def test_parse_bayer(query, expected):
    assert parse_bayer(query) == expected


@pytest.mark.parametrize("query", ["andromeda", "m 42", "sirius", "alpha", "xyz ori"])
def test_parse_bayer_rejects(query):
    assert parse_bayer(query) is None


def test_fold():
    assert fold("Órion ") == "orion" and fold("Épsilon") == "epsilon"


@pytest.fixture(scope="module")
def cats(tmp_path_factory):
    if not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog

    tmp = tmp_path_factory.mktemp("search")
    shutil.copy2(DATA / "dso.sqlite", tmp / "dso.sqlite")
    d = DsoCatalog(DATA / "dso.sqlite", tmp / "dso.sqlite")
    yield StarCatalog(DATA), d
    d.cx.close()


def _first(cats, query):
    from carina.core.search import search

    res = search(query, *cats)
    assert res, query
    return res[0]


def test_results_order(cats):
    stars, _dso = cats
    r = _first(cats, "alpha ori")
    assert r.kind == "star" and stars.proper.get(r.key) == "Betelgeuse"
    assert _first(cats, "alpha cen").label.endswith("Rigil Kentaurus")
    c = _first(cats, "órion")
    assert (c.kind, c.key) == ("const", "Ori")
    assert _first(cats, "ori").kind == "const"
    assert (_first(cats, "cruzeiro").kind, _first(cats, "cruzeiro").key) == ("const", "Cru")
    m = _first(cats, "m42")
    assert m.kind == "dso" and m.label.startswith("M 42")
    assert _first(cats, "lagoa").label.startswith("M 8")
    assert _first(cats, "jup").kind == "body"
    assert _first(cats, "sirius").kind == "star"
    # designação exata antes das que só começam igual (M 4 antes de M 42)
    from carina.core.search import search

    labels = [r.label for r in search("m4", *cats)]
    assert labels[0].split(" —")[0] == "M 4"
    assert search("a", *cats) == []


def test_dialog_ctrl_enter_and_constellation(cats):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from carina.ui.search_dialog import SearchDialog

    stars, dso = cats
    dlg = SearchDialog(stars, dso)
    added, gone = [], []
    dlg.addToListRequested.connect(added.append)
    dlg.goto_requested.connect(gone.append)
    dlg.edit.setText("alpha ori")
    ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
    assert dlg.eventFilter(dlg.edit, ev) is True
    assert added and added[0][0] == "star" and not gone
    dlg.edit.setText("cruzeiro")
    dlg._go_first()
    assert gone == [("const", "Cru")]
