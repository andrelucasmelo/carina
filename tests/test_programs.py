"""Programas de observação e certificado (v0.22 T1)."""

import datetime as dt

import pytest

UTC = dt.timezone.utc


def test_program_counts():
    from carina.core import programs as P

    counts = {k: len(P.get(k).items) for k in P.PROGRAMS}
    assert counts == {"messier": 110, "caldwell": 109, "herschel400": 400, "lunar100": 100,
                      "binoculo": 36, "planetas-ano": 7}
    m = P.get("messier")
    assert [it.ident for it in m.items[:3]] == ["M 1", "M 2", "M 3"]
    assert m.items[30].label.startswith("M 31 — ")          # nome popular traduzido
    assert P.get("caldwell").items[0].name == "C 1 (NGC 188)"
    h = P.get("herschel400")
    assert h.items[0].name.startswith("NGC 40") and h.items[-1].name.startswith("NGC 7814")


def test_progress_counts_only_program_items(tmp_path):
    from carina.core import programs as P
    from carina.core.userdata import UserData

    ud = UserData(tmp_path / "u.sqlite")
    m = P.get("messier")
    ud.add_observation("dso", "M 42", "M 42")
    ud.add_observation("dso", "M 42", "M 42")                  # repetido conta uma vez
    ud.add_observation("dso", "NGC 7000", "NGC 7000")          # fora do Messier
    ud.add_observation("star", "HIP 26311", "Alnilam")
    obs = P.observed_for(m, ud)
    assert m.progress(obs) == (1, 110)
    assert m.next_item(obs).ident == "M 1"


def test_planets_year_program(tmp_path):
    from carina.core import programs as P
    from carina.core.userdata import UserData

    ud = UserData(tmp_path / "u.sqlite")
    prog = P.get("planetas-ano")
    ud.add_observation("body", "Júpiter", "Júpiter", dt.datetime(2025, 6, 1, tzinfo=UTC))
    ud.add_observation("body", "Saturno", "Saturno", dt.datetime(2026, 3, 1, tzinfo=UTC))
    assert prog.progress(P.observed_for(prog, ud, 2026)) == (1, 7)
    assert prog.progress(P.observed_for(prog, ud, 2025)) == (1, 7)
    for i, name in enumerate(P.PLANETS):
        ud.add_observation("body", name, name, dt.datetime(2026, 4, 1 + i, 15, tzinfo=UTC))
    assert prog.progress(P.observed_for(prog, ud, 2026)) == (7, 7)
    assert P.completion_date(prog, ud, 2026) == dt.date(2026, 4, 7)


def test_certificate_pdf(tmp_path, qt_app):
    from carina.core.certificate import make_certificate

    out = make_certificate(tmp_path / "c.pdf", "Messier", 110, "Fulana de Tal",
                           dt.date(2026, 10, 6), "Rio de Janeiro", "Charles Messier")
    data = out.read_bytes()
    assert data[:5] == b"%PDF-" and len(data) > 3000


def test_programs_window(qt_app, tmp_path, monkeypatch):
    from carina.ui.mainwindow import MainWindow
    from carina.ui.programs_window import ProgramsWindow

    win = MainWindow()
    win.skip_state_save = True
    ud = win.userdata
    ud.add_observation("body", "Marte", "Marte")
    pw = ProgramsWindow(win)
    assert pw.list.count() == 6
    k = [p.key for p in pw.programs].index("planetas-ano")
    pw.list.setCurrentRow(k)
    assert "1 de 7" in pw.status.text() and not pw.btn_cert.isEnabled()
    pw.filter.setCurrentIndex(2)                               # feitos
    assert pw.items.topLevelItemCount() == 1
    pw.filter.setCurrentIndex(1)                               # faltam
    assert pw.items.topLevelItemCount() == 6
    pw.list.setCurrentRow([p.key for p in pw.programs].index("messier"))
    pw._todo_list()
    lid = ud.list_id("Faltam: Messier")
    assert lid is not None and len(ud.items(lid)) >= 100
    pw.close()
    win.close()
