"""Diário de observação (v0.15 T8)."""

import datetime as dt

from carina.core.userdata import UserData

WHEN = dt.datetime(2026, 10, 3, 1, 30, tzinfo=dt.timezone.utc)


def test_dialog_values_round_trip(tmp_path):
    from carina.ui.journal_dialog import ObservationDialog

    dlg = ObservationDialog("M 42", WHEN, "Rio", ["Dobson 8\"", "Olho nu"], bortle=6)
    dlg.seeing.setCurrentIndex(4)
    dlg.transparency.setCurrentIndex(3)
    dlg.rating.setCurrentIndex(5)
    dlg.note.setPlainText("Trapézio com 4 estrelas")
    v = dlg.values()
    assert v["when_utc"] == WHEN                 # hora local ↔ UTC sem perda
    assert v["location"] == "Rio" and v["instrument"] == "Dobson 8\""
    assert (v["bortle"], v["seeing"], v["transparency"], v["rating"]) == (6, 4, 3, 5)
    ud = UserData(tmp_path / "c.sqlite")
    when = v.pop("when_utc")
    oid = ud.add_observation("dso", "M 42", "M 42", when, **v)
    saved = ud.observations("dso", "M 42")[0]
    edit = ObservationDialog("M 42", WHEN, data=saved)
    assert edit.note.toPlainText() == "Trapézio com 4 estrelas"
    assert edit.seeing.currentIndex() == 4
    edit.when.setDateTime(edit.when.dateTime().addSecs(3600))
    ud.update_observation(oid, **edit.values())
    assert ud.observations()[0]["when_utc"] == WHEN + dt.timedelta(hours=1)
    ud.close()


def test_journal_window_filters_and_survives_reopen(tmp_path):
    from carina.ui.journal_dialog import JournalWindow

    path = tmp_path / "c.sqlite"
    ud = UserData(path)
    ud.add_observation("dso", "M 42", "M 42", WHEN, location="Rio", note="nítida")
    ud.add_observation("dso", "M 31", "M 31", WHEN - dt.timedelta(days=3),
                       location="Sítio")
    ud.close()
    again = UserData(path)                       # "observado" sobrevive ao reabrir
    win = JournalWindow(again)
    assert win.table.rowCount() == 2
    assert "2 registros" in win.summary.text() and "2 noites" in win.summary.text()
    win.search.setText("sítio")
    assert win.table.rowCount() == 1 and win.table.item(0, 2).text() == "M 31"
    got = []
    win.gotoRequested.connect(lambda k, i: got.append((k, i)))
    win.table.selectRow(0)
    win._goto()
    assert got == [("dso", "M 31")]
    win.close()
    again.close()
