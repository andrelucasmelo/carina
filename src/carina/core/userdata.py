"""Banco do usuário ``carina.sqlite``: listas, diário, horizontes e perfis.

Tudo o que o usuário cria e quer de volta na próxima abertura mora aqui,
num único arquivo SQLite na pasta de dados do usuário (decisão 7 da
revisão de 2026-10, ADR-042):

``lists`` / ``list_items``
    Listas nomeadas de alvos ("Minha lista", "Galáxias do outono"…).
``observations``
    O diário: quando, o que, condições (Bortle, seeing, transparência),
    instrumento, nota e avaliação.
``horizons`` / ``horizon_points``
    Perfis do horizonte do quintal; um deles fica ativo.
``profiles``
    Configurações salvas por tipo (``kind``) e nome, em JSON — perfis de
    carta, locais salvos, setups de astrofoto nas próximas versões.

Os objetos são guardados por uma **identidade estável** (``kind`` +
``ident``) e não pelos índices internos, que mudam entre versões dos
catálogos: céu profundo pelo nome ("M 42"), estrelas pelo número HIP
("HIP 27989"), corpos pelo nome ("Júpiter").

O arquivo só é criado na primeira **escrita**: abrir o aplicativo e só
consultar não deixa rastro no disco. A versão do esquema fica em
``meta.version`` e as migrações são aditivas, como as do ``dso.sqlite``.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = {
    1: """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS list_items (
    id INTEGER PRIMARY KEY,
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    ident TEXT NOT NULL,
    name TEXT NOT NULL,
    ra REAL, dec REAL,
    position INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    UNIQUE (list_id, kind, ident)
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    ident TEXT NOT NULL,
    name TEXT NOT NULL,
    when_utc TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    instrument TEXT NOT NULL DEFAULT '',
    bortle INTEGER,
    seeing INTEGER,
    transparency INTEGER,
    rating INTEGER,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_obs_ident ON observations(kind, ident);
CREATE TABLE IF NOT EXISTS horizons (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    location TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS horizon_points (
    horizon_id INTEGER NOT NULL REFERENCES horizons(id) ON DELETE CASCADE,
    az REAL NOT NULL,
    alt REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (kind, name)
);
""",
}

DEFAULT_LIST = "Minha lista"
OBS_FIELDS = ("location", "instrument", "bortle", "seeing", "transparency",
              "rating", "note")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def default_path() -> Path:
    from ..config import user_data_path

    return user_data_path() / "carina.sqlite"


class UserData:
    """Acesso ao ``carina.sqlite``. Leituras não criam o arquivo."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_path()
        self._cx: sqlite3.Connection | None = None
        if self.path.exists():
            self._open()

    # -- conexão e esquema ---------------------------------------------
    @property
    def exists(self) -> bool:
        return self._cx is not None

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cx = sqlite3.connect(self.path)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys = ON")
        self._cx = cx
        self._migrate()
        return cx

    def _migrate(self) -> None:
        cx = self._cx
        cx.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = cx.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        current = int(row[0]) if row else 0
        for version in range(current + 1, SCHEMA_VERSION + 1):
            cx.executescript(_SCHEMA[version])
            cx.execute("INSERT OR REPLACE INTO meta VALUES ('version', ?)",
                       (str(version),))
        cx.commit()

    def version(self) -> int:
        if self._cx is None:
            return 0
        row = self._cx.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        return int(row[0]) if row else 0

    def _w(self) -> sqlite3.Connection:
        """Conexão para escrita (cria o arquivo na primeira vez)."""
        return self._cx if self._cx is not None else self._open()

    def _q(self, sql: str, params=()) -> list[sqlite3.Row]:
        if self._cx is None:
            return []
        return self._cx.execute(sql, params).fetchall()

    def close(self) -> None:
        if self._cx is not None:
            self._cx.close()
            self._cx = None

    # -- listas ----------------------------------------------------------
    def lists(self) -> list[dict]:
        """Listas com a contagem de itens, em ordem alfabética."""
        return [dict(r) for r in self._q(
            "SELECT l.id, l.name, l.notes, COUNT(i.id) AS count FROM lists l"
            " LEFT JOIN list_items i ON i.list_id = l.id"
            " GROUP BY l.id ORDER BY l.name COLLATE NOCASE")]

    def list_id(self, name: str) -> int | None:
        rows = self._q("SELECT id FROM lists WHERE name = ?", (name,))
        return int(rows[0]["id"]) if rows else None

    def create_list(self, name: str, notes: str = "") -> int:
        name = name.strip()
        if not name:
            raise ValueError("nome de lista vazio")
        cx = self._w()
        cur = cx.execute("INSERT INTO lists (name, notes, created_at) VALUES (?,?,?)",
                         (name, notes, _now()))
        cx.commit()
        return int(cur.lastrowid)

    def ensure_list(self, name: str = DEFAULT_LIST) -> int:
        existing = self.list_id(name)
        return existing if existing is not None else self.create_list(name)

    def rename_list(self, list_id: int, name: str) -> None:
        cx = self._w()
        cx.execute("UPDATE lists SET name = ? WHERE id = ?", (name.strip(), list_id))
        cx.commit()

    def delete_list(self, list_id: int) -> None:
        cx = self._w()
        cx.execute("DELETE FROM lists WHERE id = ?", (list_id,))
        cx.commit()

    def items(self, list_id: int) -> list[dict]:
        return [dict(r) for r in self._q(
            "SELECT * FROM list_items WHERE list_id = ? ORDER BY position, id",
            (list_id,))]

    def add_item(self, list_id: int, kind: str, ident: str, name: str,
                 ra: float | None = None, dec: float | None = None,
                 note: str = "") -> int | None:
        """Acrescenta ao fim da lista; ``None`` se o objeto já estava nela."""
        cx = self._w()
        pos = cx.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM list_items"
                         " WHERE list_id = ?", (list_id,)).fetchone()[0]
        cur = cx.execute(
            "INSERT OR IGNORE INTO list_items (list_id, kind, ident, name, ra, dec,"
            " position, note, added_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (list_id, kind, ident, name, ra, dec, pos, note, _now()))
        cx.commit()
        return int(cur.lastrowid) if cur.rowcount else None

    def remove_item(self, item_id: int) -> None:
        cx = self._w()
        cx.execute("DELETE FROM list_items WHERE id = ?", (item_id,))
        cx.commit()

    def move_item(self, item_id: int, new_index: int) -> None:
        """Move o item para a posição ``new_index`` (0 = topo) da lista."""
        cx = self._w()
        row = cx.execute("SELECT list_id FROM list_items WHERE id = ?",
                         (item_id,)).fetchone()
        if row is None:
            return
        ids = [r[0] for r in cx.execute(
            "SELECT id FROM list_items WHERE list_id = ? ORDER BY position, id",
            (row[0],))]
        ids.remove(item_id)
        ids.insert(max(0, min(len(ids), new_index)), item_id)
        cx.executemany("UPDATE list_items SET position = ? WHERE id = ?",
                       [(i, iid) for i, iid in enumerate(ids)])
        cx.commit()

    def set_item_note(self, item_id: int, note: str) -> None:
        cx = self._w()
        cx.execute("UPDATE list_items SET note = ? WHERE id = ?", (note, item_id))
        cx.commit()

    def lists_containing(self, kind: str, ident: str) -> list[str]:
        return [r["name"] for r in self._q(
            "SELECT l.name FROM lists l JOIN list_items i ON i.list_id = l.id"
            " WHERE i.kind = ? AND i.ident = ? ORDER BY l.name", (kind, ident))]

    # -- diário ------------------------------------------------------------
    def add_observation(self, kind: str, ident: str, name: str,
                        when_utc: dt.datetime | None = None, **fields) -> int:
        when = (when_utc or dt.datetime.now(dt.timezone.utc))
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        data = {k: fields.get(k) for k in OBS_FIELDS}
        for k in ("location", "instrument", "note"):
            data[k] = data[k] or ""
        cx = self._w()
        cur = cx.execute(
            "INSERT INTO observations (kind, ident, name, when_utc, location,"
            " instrument, bortle, seeing, transparency, rating, note)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (kind, ident, name, when.astimezone(dt.timezone.utc).isoformat(
                timespec="seconds"), *[data[k] for k in OBS_FIELDS]))
        cx.commit()
        return int(cur.lastrowid)

    def update_observation(self, obs_id: int, **fields) -> None:
        keys = [k for k in fields if k in OBS_FIELDS]
        if not keys:
            return
        cx = self._w()
        cx.execute(f"UPDATE observations SET {', '.join(k + ' = ?' for k in keys)}"
                   " WHERE id = ?", [fields[k] for k in keys] + [obs_id])
        cx.commit()

    def delete_observation(self, obs_id: int) -> None:
        cx = self._w()
        cx.execute("DELETE FROM observations WHERE id = ?", (obs_id,))
        cx.commit()

    def observations(self, kind: str | None = None,
                     ident: str | None = None) -> list[dict]:
        """Registros do diário, mais recentes primeiro (filtro opcional)."""
        if kind is not None and ident is not None:
            rows = self._q("SELECT * FROM observations WHERE kind = ? AND ident = ?"
                           " ORDER BY when_utc DESC", (kind, ident))
        else:
            rows = self._q("SELECT * FROM observations ORDER BY when_utc DESC")
        out = []
        for r in rows:
            d = dict(r)
            d["when_utc"] = dt.datetime.fromisoformat(d["when_utc"])
            out.append(d)
        return out

    def observed_idents(self) -> set[tuple[str, str]]:
        return {(r["kind"], r["ident"]) for r in self._q(
            "SELECT DISTINCT kind, ident FROM observations")}

    def observations_csv(self) -> str:
        """Diário inteiro em CSV (separador ';', hora local do observador)."""
        from .localtime import to_local

        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\n")
        w.writerow(["data", "hora", "objeto", "tipo", "local", "instrumento",
                    "bortle", "seeing", "transparencia", "avaliacao", "nota"])
        for o in reversed(self.observations()):
            loc = to_local(o["when_utc"])
            w.writerow([loc.strftime("%Y-%m-%d"), loc.strftime("%H:%M"), o["name"],
                        o["kind"], o["location"], o["instrument"],
                        o["bortle"] or "", o["seeing"] or "", o["transparency"] or "",
                        o["rating"] or "", o["note"]])
        return buf.getvalue()

    # -- horizontes --------------------------------------------------------
    def horizons(self) -> list[dict]:
        return [dict(r) for r in self._q(
            "SELECT h.id, h.name, h.location, h.active, COUNT(p.az) AS points"
            " FROM horizons h LEFT JOIN horizon_points p ON p.horizon_id = h.id"
            " GROUP BY h.id ORDER BY h.name COLLATE NOCASE")]

    def save_horizon(self, profile, location: str = "", active: bool = True) -> int:
        """Grava (ou substitui) o perfil pelo nome; opcionalmente o ativa."""
        cx = self._w()
        row = cx.execute("SELECT id FROM horizons WHERE name = ?",
                         (profile.name,)).fetchone()
        if row is None:
            hid = int(cx.execute("INSERT INTO horizons (name, location) VALUES (?,?)",
                                 (profile.name, location)).lastrowid)
        else:
            hid = int(row[0])
            cx.execute("UPDATE horizons SET location = ? WHERE id = ?", (location, hid))
            cx.execute("DELETE FROM horizon_points WHERE horizon_id = ?", (hid,))
        cx.executemany("INSERT INTO horizon_points VALUES (?,?,?)",
                       [(hid, az, alt) for az, alt in profile.points])
        if active:
            cx.execute("UPDATE horizons SET active = (id = ?)", (hid,))
        cx.commit()
        return hid

    def horizon(self, name: str):
        from .horizon import HorizonProfile

        rows = self._q("SELECT id FROM horizons WHERE name = ?", (name,))
        if not rows:
            return None
        pts = self._q("SELECT az, alt FROM horizon_points WHERE horizon_id = ?"
                      " ORDER BY az", (rows[0]["id"],))
        return HorizonProfile([(r["az"], r["alt"]) for r in pts], name)

    def active_horizon(self):
        """Perfil ativo, ou ``None`` (horizonte plano)."""
        rows = self._q("SELECT name FROM horizons WHERE active = 1")
        return self.horizon(rows[0]["name"]) if rows else None

    def set_active_horizon(self, name: str | None) -> None:
        cx = self._w()
        cx.execute("UPDATE horizons SET active = (name = ?)", (name or "",))
        cx.commit()

    def delete_horizon(self, name: str) -> None:
        cx = self._w()
        cx.execute("DELETE FROM horizons WHERE name = ?", (name,))
        cx.commit()

    # -- perfis genéricos --------------------------------------------------
    def save_profile(self, kind: str, name: str, data) -> None:
        cx = self._w()
        cx.execute("INSERT INTO profiles (kind, name, data, updated_at) VALUES (?,?,?,?)"
                   " ON CONFLICT(kind, name) DO UPDATE SET data = excluded.data,"
                   " updated_at = excluded.updated_at",
                   (kind, name, json.dumps(data, ensure_ascii=False), _now()))
        cx.commit()

    def profile(self, kind: str, name: str):
        rows = self._q("SELECT data FROM profiles WHERE kind = ? AND name = ?",
                       (kind, name))
        return json.loads(rows[0]["data"]) if rows else None

    def profiles(self, kind: str) -> list[str]:
        return [r["name"] for r in self._q(
            "SELECT name FROM profiles WHERE kind = ? ORDER BY name COLLATE NOCASE",
            (kind,))]

    def delete_profile(self, kind: str, name: str) -> None:
        cx = self._w()
        cx.execute("DELETE FROM profiles WHERE kind = ? AND name = ?", (kind, name))
        cx.commit()


_INSTANCE: UserData | None = None


def get() -> UserData:
    """Instância única do aplicativo (os testes criam as suas)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = UserData()
    return _INSTANCE


def set_instance(data: UserData | None) -> None:
    """Troca a instância global (testes e modo ``--screenshot``)."""
    global _INSTANCE
    _INSTANCE = data
