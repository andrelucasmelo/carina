"""B-023: a cópia do usuário do banco de céu profundo acompanha o embarcado.

Cenário: o usuário copiou o banco na versão 1, editou um objeto, criou um
objeto próprio (que ocupa o id que o embarcado novo dará a um objeto novo)
e uma categoria. O embarcado sobe para a versão 2 com dois objetos novos,
uma designação nova num objeto antigo e um nome comum que faltava. Ao
abrir, tudo isso chega à cópia sem perder nada do usuário.
"""

import shutil
import sqlite3

import pytest

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE objects (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
    klass TEXT NOT NULL, ra REAL NOT NULL, dec REAL NOT NULL, mag REAL,
    maj REAL, min REAL, pa REAL, con TEXT, common TEXT,
    enabled INTEGER NOT NULL DEFAULT 1, user_added INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE TABLE designations (
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    catalog TEXT NOT NULL, ident TEXT NOT NULL,
    PRIMARY KEY (object_id, catalog, ident)
);
CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE object_categories (
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (object_id, category_id)
);
"""

OLD = [  # (id, name, klass, mag, common, designations)
    (1, "M 42", "NEB", 4.0, "Great Orion Nebula", [("M", "42"), ("NGC", "1976")]),
    (2, "NGC 7000", "NEB", 4.0, None, [("NGC", "7000")]),
    (3, "Mel 25", "OC", 0.5, "Hyades", [("Mel", "25")]),
]
NEW_EXTRA = [
    (4, "LDN 1", "DARK", None, None, [("LDN", "1")]),
    (5, "Cr 399", "OC", 3.6, "Coathanger", [("Cr", "399")]),
]


def _make_db(path, rows, version, extra_desig=(), fill_common=False):
    cx = sqlite3.connect(path)
    cx.executescript(SCHEMA)
    for oid, name, klass, mag, common, desigs in rows:
        if fill_common and name == "NGC 7000":
            common = "North America Nebula"
        cx.execute(
            "INSERT INTO objects (id, name, type, klass, ra, dec, mag, common)"
            " VALUES (?, ?, 'Neb', ?, 1.0, 0.5, ?, ?)",
            (oid, name, klass, mag, common),
        )
        for cat, ident in desigs:
            cx.execute("INSERT INTO designations VALUES (?, ?, ?)",
                       (oid, cat, ident))
    for oid, cat, ident in extra_desig:
        cx.execute("INSERT INTO designations VALUES (?, ?, ?)", (oid, cat, ident))
    cx.execute("INSERT INTO categories (name) VALUES ('Favoritos')")
    if version is not None:
        cx.execute("INSERT INTO meta VALUES ('data_version', ?)", (str(version),))
    cx.commit()
    cx.close()


@pytest.fixture
def dbs(tmp_path):
    old_bundled = tmp_path / "bundled_v1.sqlite"
    _make_db(old_bundled, OLD, version=None)          # anterior ao versionamento
    user = tmp_path / "user" / "dso.sqlite"
    user.parent.mkdir()
    shutil.copy2(old_bundled, user)
    # edições do usuário na cópia
    cx = sqlite3.connect(user)
    cx.execute("UPDATE objects SET enabled = 0, notes = 'minha nota' WHERE id = 2")
    cx.execute(
        "INSERT INTO objects (id, name, type, klass, ra, dec, mag, user_added)"
        " VALUES (4, 'Meu alvo', 'Other', 'OTHER', 2.0, -0.3, 9.0, 1)"
    )
    cx.execute("INSERT INTO categories (name) VALUES ('Verão')")
    cx.execute("INSERT INTO object_categories SELECT 1, id FROM categories"
               " WHERE name = 'Verão'")
    cx.commit()
    cx.close()
    new_bundled = tmp_path / "bundled_v2.sqlite"
    _make_db(new_bundled, OLD + NEW_EXTRA, version=2,
             extra_desig=[(2, "C", "20"), (3, "Cr", "50")], fill_common=True)
    return new_bundled, user


def test_merge_adds_without_losing_user_edits(dbs):
    from carina.catalogs.dso import DsoCatalog, read_data_version

    new_bundled, user = dbs
    cat = DsoCatalog(new_bundled, user, visible_catalogs=set())
    rep = cat.migration_report
    assert rep is not None and rep["from"] == 1 and rep["to"] == 2
    assert rep["objects"] == 2                  # LDN 1 e Cr 399
    assert rep["designations"] == 4             # 2 dos novos + C 20 + Cr 50
    assert rep["backup"].exists()
    assert read_data_version(user) == 2

    cx = cat.cx
    # edições preservadas
    row = cx.execute("SELECT enabled, notes FROM objects WHERE name = 'NGC 7000'").fetchone()
    assert (row["enabled"], row["notes"]) == (0, "minha nota")
    # objeto do usuário no id 4 sobrevive; o novo "LDN 1" ganhou outro id
    assert cx.execute("SELECT name FROM objects WHERE id = 4").fetchone()["name"] == "Meu alvo"
    ldn = cx.execute("SELECT id FROM objects WHERE name = 'LDN 1'").fetchone()
    assert ldn is not None and ldn["id"] != 4
    assert cx.execute(
        "SELECT COUNT(*) FROM designations WHERE catalog = 'LDN'"
    ).fetchone()[0] == 1
    # designação nova em objeto antigo e nome comum preenchido
    assert cx.execute(
        "SELECT COUNT(*) FROM designations WHERE object_id = 2 AND catalog = 'C'"
    ).fetchone()[0] == 1
    assert cx.execute(
        "SELECT common FROM objects WHERE name = 'NGC 7000'"
    ).fetchone()["common"] == "North America Nebula"
    # categoria do usuário intacta
    assert cx.execute(
        "SELECT COUNT(*) FROM categories WHERE name = 'Verão'"
    ).fetchone()[0] == 1
    cat.cx.close()


def test_second_open_is_a_no_op(dbs):
    from carina.catalogs.dso import DsoCatalog

    new_bundled, user = dbs
    first = DsoCatalog(new_bundled, user, visible_catalogs=set())
    first.cx.close()
    again = DsoCatalog(new_bundled, user, visible_catalogs=set())
    assert again.migration_report is None
    assert len(list(user.parent.glob("*.bak*"))) == 1
    again.cx.close()


def test_bundled_database_is_versioned():
    """O banco embarcado do repositório declara a versão 2 (catálogos extras)."""
    from pathlib import Path

    from carina.catalogs.dso import read_data_version

    db = Path(__file__).resolve().parent.parent / "data" / "processed" / "dso.sqlite"
    if not db.exists():
        pytest.skip("banco embarcado ausente")
    assert read_data_version(db) >= 2


def test_magnitude_fixes_respect_user_edits(tmp_path):
    """B-024: versão 3 corrige magnitudes onde o usuário não editou."""
    from carina.catalogs.dso import DsoCatalog

    rows = [(1, "NGC 253", "GAL", 11.11, None, [("NGC", "253")]),
            (2, "NGC 4945", "GAL", 11.86, None, [("NGC", "4945")])]
    user = tmp_path / "u" / "dso.sqlite"
    user.parent.mkdir()
    _make_db(user, rows, version=2)
    cx = sqlite3.connect(user)
    cx.execute("UPDATE objects SET mag = 8.0 WHERE name = 'NGC 4945'")  # edição
    cx.commit()
    cx.close()
    bundled = tmp_path / "b.sqlite"
    fixed = [(1, "NGC 253", "GAL", 7.14, None, [("NGC", "253")]),
             (2, "NGC 4945", "GAL", 8.48, None, [("NGC", "4945")])]
    _make_db(bundled, fixed, version=3)
    cx = sqlite3.connect(bundled)
    cx.execute("CREATE TABLE mag_fixes (name TEXT PRIMARY KEY, old REAL, new REAL)")
    cx.executemany("INSERT INTO mag_fixes VALUES (?,?,?)",
                   [("NGC 253", 11.11, 7.14), ("NGC 4945", 11.86, 8.48)])
    cx.commit()
    cx.close()

    cat = DsoCatalog(bundled, user, visible_catalogs=set())
    assert cat.migration_report["magnitudes"] == 1
    mags = dict(cat.cx.execute("SELECT name, mag FROM objects").fetchall())
    assert mags["NGC 253"] == 7.14
    assert mags["NGC 4945"] == 8.0            # edição do usuário preservada
    cat.cx.close()


def test_bundled_ngc253_magnitude():
    from pathlib import Path

    db = Path(__file__).resolve().parent.parent / "data" / "processed" / "dso.sqlite"
    if not db.exists():
        pytest.skip("banco embarcado ausente")
    cx = sqlite3.connect(db)
    mag = cx.execute("SELECT mag FROM objects WHERE name = 'NGC 253'").fetchone()[0]
    cx.close()
    assert 6.5 < mag < 8.0
