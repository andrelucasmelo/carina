"""Banco do usuário carina.sqlite (v0.15 T3)."""

import datetime as dt
import shutil
import sqlite3
from pathlib import Path

import pytest

from carina.core.horizon import HorizonProfile
from carina.core.userdata import SCHEMA_VERSION, UserData

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"


def test_file_created_only_on_first_write(tmp_path):
    path = tmp_path / "carina.sqlite"
    ud = UserData(path)
    assert ud.lists() == [] and ud.observations() == [] and ud.active_horizon() is None
    assert not path.exists()
    ud.ensure_list()
    assert path.exists() and ud.version() == SCHEMA_VERSION
    ud.close()


def test_lists_crud_and_order(tmp_path):
    ud = UserData(tmp_path / "c.sqlite")
    lid = ud.ensure_list()
    assert ud.ensure_list() == lid                 # idempotente
    a = ud.add_item(lid, "dso", "M 42", "M 42 — Órion", 1.46, -0.09)
    b = ud.add_item(lid, "star", "HIP 32349", "Sírius")
    c = ud.add_item(lid, "body", "Júpiter", "Júpiter")
    assert ud.add_item(lid, "dso", "M 42", "de novo") is None   # sem duplicata
    assert [i["ident"] for i in ud.items(lid)] == ["M 42", "HIP 32349", "Júpiter"]
    ud.move_item(c, 0)
    assert [i["id"] for i in ud.items(lid)] == [c, a, b]
    ud.remove_item(a)
    assert [i["id"] for i in ud.items(lid)] == [c, b]
    other = ud.create_list("Galáxias")
    ud.add_item(other, "star", "HIP 32349", "Sírius")
    assert ud.lists_containing("star", "HIP 32349") == ["Galáxias", "Minha lista"]
    assert {l["name"]: l["count"] for l in ud.lists()} == {"Galáxias": 1, "Minha lista": 2}
    ud.rename_list(other, "Inverno")
    ud.delete_list(lid)
    assert [l["name"] for l in ud.lists()] == ["Inverno"]
    with pytest.raises(sqlite3.IntegrityError):
        ud.create_list("Inverno")
    ud.close()


def test_journal_and_csv(tmp_path):
    ud = UserData(tmp_path / "c.sqlite")
    when = dt.datetime(2026, 10, 3, 1, 30, tzinfo=dt.timezone.utc)
    oid = ud.add_observation("dso", "M 42", "M 42", when, bortle=5, seeing=4,
                             instrument="Dobson 8\"", note="trapézio nítido")
    ud.add_observation("dso", "M 31", "M 31", when - dt.timedelta(days=1))
    rows = ud.observations("dso", "M 42")
    assert len(rows) == 1 and rows[0]["when_utc"] == when and rows[0]["seeing"] == 4
    assert ud.observed_idents() == {("dso", "M 42"), ("dso", "M 31")}
    ud.update_observation(oid, note="trapézio com E e F", rating=5)
    assert ud.observations("dso", "M 42")[0]["rating"] == 5
    csv_text = ud.observations_csv()
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("data;hora;objeto")
    assert lines[1].split(";")[2] == "M 31"          # ordem cronológica
    assert "trapézio com E e F" in lines[2]
    ud.delete_observation(oid)
    assert len(ud.observations()) == 1
    ud.close()


def test_horizons_and_profiles_survive_reopen(tmp_path):
    path = tmp_path / "c.sqlite"
    ud = UserData(path)
    ud.save_horizon(HorizonProfile([(0, 5), (180, 30)], "Quintal"), "Rio")
    ud.save_horizon(HorizonProfile([(90, 10)], "Sítio"), active=False)
    ud.save_profile("chart", "A4 escuro", {"theme": "dark", "mag": 6.5})
    ud.close()
    again = UserData(path)
    active = again.active_horizon()
    assert active.name == "Quintal" and active.points == [(0.0, 5.0), (180.0, 30.0)]
    assert [h["name"] for h in again.horizons()] == ["Quintal", "Sítio"]
    again.set_active_horizon("Sítio")
    assert again.active_horizon().name == "Sítio"
    again.set_active_horizon(None)
    assert again.active_horizon() is None
    assert again.profile("chart", "A4 escuro") == {"theme": "dark", "mag": 6.5}
    again.save_profile("chart", "A4 escuro", {"theme": "red"})
    assert again.profiles("chart") == ["A4 escuro"]
    assert again.profile("chart", "A4 escuro")["theme"] == "red"
    again.close()


def test_migration_from_future_proof_old_file(tmp_path):
    """Um arquivo sem meta.version recebe o esquema completo sem perder nada."""
    path = tmp_path / "c.sqlite"
    cx = sqlite3.connect(path)
    cx.execute("CREATE TABLE extra (x INTEGER)")
    cx.execute("INSERT INTO extra VALUES (7)")
    cx.commit()
    cx.close()
    ud = UserData(path)
    assert ud.version() == SCHEMA_VERSION
    assert ud._cx.execute("SELECT x FROM extra").fetchone()[0] == 7
    ud.close()


def test_object_identity_round_trip(tmp_path):
    if not (DATA / "dso.sqlite").exists():
        pytest.skip("dados ausentes")
    from carina.catalogs.dso import DsoCatalog
    from carina.catalogs.stars import StarCatalog
    from carina.core.objects import ObjectRef

    user = tmp_path / "dso.sqlite"
    shutil.copy2(DATA / "dso.sqlite", user)
    dso = DsoCatalog(DATA / "dso.sqlite", user)
    stars = StarCatalog(DATA)
    sirius = next(i for i, n in stars.proper.items() if n in ("Sirius", "Sírius"))
    ref = ObjectRef.resolve(("star", sirius), stars, dso)
    assert ref.ident == "HIP 32349"
    back = ObjectRef.from_ident("star", ref.ident, stars, dso)
    assert back.key == sirius
    oid = dso.cx.execute("SELECT id FROM objects WHERE name = 'M 42'").fetchone()[0]
    m42 = ObjectRef.resolve(("dso", oid), stars, dso)
    assert m42.ident == "M 42"
    assert ObjectRef.from_ident("dso", "M 42", stars, dso).key == oid
    assert ObjectRef.from_ident("dso", "não existe", stars, dso) is None
    assert ObjectRef.from_ident("body", "Júpiter", stars, dso).ident == "Júpiter"
    ra, dec = m42.ra_dec
    assert abs(ra - m42.data["ra"]) < 1e-9 and abs(dec - m42.data["dec"]) < 1e-9
    dso.cx.close()
