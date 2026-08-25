"""Catálogo de céu profundo: leitura para renderização + CRUD (item 6).

O banco embarcado (data/processed/dso.sqlite) é copiado para o diretório do
usuário no primeiro uso; todas as edições (incluir/editar/remover/habilitar,
categorias) acontecem na cópia do usuário e sobrevivem a atualizações do app.
"Restaurar padrão" recopia o banco embarcado.
"""

from __future__ import annotations

import math
import shutil
import sqlite3
from pathlib import Path

import numpy as np

# Ordem de preferência da designação principal
CATALOG_ORDER = ["M", "NGC", "IC", "C", "SH2", "B", "Mel"]

# Catálogos acrescentados depois: entram DESABILITADOS por padrão
EXTRA_CATALOGS = ["LDN", "Cr", "VdB", "Abell"]
ALL_CATALOGS = CATALOG_ORDER + EXTRA_CATALOGS

CATALOG_LABELS = {
    "M": "Messier", "NGC": "NGC", "IC": "IC", "C": "Caldwell",
    "SH2": "Sharpless (SH2)", "B": "Barnard", "Mel": "Melotte",
    "LDN": "Lynds Dark Nebulae (LDN)", "Cr": "Collinder (Cr)",
    "VdB": "van den Bergh (vdB)", "Abell": "Abell",
}

KLASS_CODES = {"GAL": 0, "OC": 1, "GC": 2, "NEB": 3, "PN": 4, "DARK": 5, "OTHER": 6}

TYPE_PT = {
    "G": "Galáxia", "GPair": "Par de galáxias", "GTrpl": "Trio de galáxias",
    "GGroup": "Grupo de galáxias", "OCl": "Aglomerado aberto",
    "GCl": "Aglomerado globular", "PN": "Nebulosa planetária",
    "HII": "Região HII", "EmN": "Nebulosa de emissão",
    "RfN": "Nebulosa de reflexão", "SNR": "Remanescente de supernova",
    "Cl+N": "Aglomerado com nebulosa", "Neb": "Nebulosa",
    "DrkN": "Nebulosa escura", "**": "Estrela dupla", "*": "Estrela",
    "*Ass": "Associação estelar", "OpC": "Aglomerado aberto",
    "GlC": "Aglomerado globular", "As*": "Associação estelar",
    "Cl*": "Aglomerado estelar", "Other": "Outro",
}


def type_label(code: str) -> str:
    """Código de tipo do banco ('Gx', 'OpC'…) → rótulo em português."""
    return TYPE_PT.get(code, code or "Objeto")


class DsoCatalog:
    """Catálogo de céu profundo sobre SQLite, com CRUD e arrays de render.

    O banco EMBARCADO é copiado para a pasta do usuário na primeira
    execução; todas as edições (objetos próprios, habilitar/desabilitar,
    categorias) acontecem na cópia — uma reinstalação nunca destrói dados
    do usuário. Depois de qualquer mutação chama-se :meth:`reload`, que
    reconstrói os arrays NumPy ordenados por magnitude usados pelo
    renderizador (a ordenação permite cortes de brilho por fatiamento).
    """

    def __init__(self, bundled_db: Path, user_db: Path,
                 visible_catalogs: set[str] | None = None) -> None:
        self.bundled_db = bundled_db
        self.user_db = user_db
        # filtro de exibição por catálogo inteiro; os catálogos acrescentados
        # depois (LDN, Cr, VdB, Abell) nascem desligados
        self.visible_catalogs: set[str] = (
            set(CATALOG_ORDER) if visible_catalogs is None
            else set(visible_catalogs)
        )
        if not user_db.exists():
            user_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled_db, user_db)
        self.cx = sqlite3.connect(str(user_db))
        self.cx.row_factory = sqlite3.Row
        self.cx.execute("PRAGMA foreign_keys = ON")
        self.featured_names: set[str] = set()
        self.reload()

    def set_featured_names(self, names: set[str]) -> None:
        """Objetos com imagem destacada (manifesto) — recalcula a máscara."""
        self.featured_names = set(names)
        self.is_featured = np.array(
            [n in self.featured_names for n in self.names], dtype=bool
        )

    def set_catalog_visible(self, catalog: str, visible: bool) -> None:
        """Liga/desliga um catálogo INTEIRO (tela de configuração)."""
        if visible:
            self.visible_catalogs.add(catalog)
        else:
            self.visible_catalogs.discard(catalog)
        self.reload()

    # ------------------------------------------------------------------
    # Arrays para renderização (somente objetos habilitados)
    # ------------------------------------------------------------------
    def reload(self) -> None:
        """Reconstrói os arrays de renderização a partir do banco.

        Só entram objetos habilitados cujos catálogos estão visíveis (um
        objeto criado pelo usuário, ou sem designação, aparece sempre).
        A ordem é por magnitude crescente — é isso que permite ao
        renderizador manter "os N mais brilhantes" com um simples corte.
        """
        sql = (
            "SELECT id, name, klass, ra, dec, mag, maj, min, pa, common"
            " FROM objects o WHERE enabled = 1"
        )
        params: list = []
        if self.visible_catalogs != set(ALL_CATALOGS):
            marks = ",".join("?" * len(self.visible_catalogs)) or "''"
            # visível se: adicionado pelo usuário, sem designação alguma, ou
            # com ao menos uma designação de catálogo habilitado
            sql += (
                " AND (o.user_added = 1"
                " OR NOT EXISTS(SELECT 1 FROM designations d"
                "               WHERE d.object_id = o.id)"
                f" OR EXISTS(SELECT 1 FROM designations d"
                f"           WHERE d.object_id = o.id"
                f"           AND d.catalog IN ({marks})))"
            )
            params = sorted(self.visible_catalogs)
        sql += " ORDER BY CASE WHEN mag IS NULL THEN 99 ELSE mag END"
        rows = self.cx.execute(sql, params).fetchall()
        n = len(rows)
        self.ids = np.empty(n, dtype=np.int64)
        self.xyz = np.empty((n, 3), dtype=np.float32)
        self.mag = np.full(n, 99.0, dtype=np.float32)
        self.maj = np.zeros(n, dtype=np.float32)   # arcmin
        self.minor = np.zeros(n, dtype=np.float32)
        self.pa = np.zeros(n, dtype=np.float32)    # graus
        self.klass = np.empty(n, dtype=np.int8)
        self.names: list[str] = []
        self.commons: list[str | None] = []
        for i, r in enumerate(rows):
            self.ids[i] = r["id"]
            cd = math.cos(r["dec"])
            self.xyz[i] = (
                cd * math.cos(r["ra"]), cd * math.sin(r["ra"]), math.sin(r["dec"])
            )
            if r["mag"] is not None:
                self.mag[i] = r["mag"]
            self.maj[i] = r["maj"] or 0.0
            self.minor[i] = r["min"] or r["maj"] or 0.0
            self.pa[i] = r["pa"] or 0.0
            self.klass[i] = KLASS_CODES.get(r["klass"], 6)
            self.names.append(r["name"])
            self.commons.append(r["common"])
        self._id_to_row = {int(oid): i for i, oid in enumerate(self.ids)}
        # Messier/Caldwell: sempre rotulados, em negrito (pedido do usuário)
        mc_ids = {
            int(r[0]) for r in self.cx.execute(
                "SELECT DISTINCT object_id FROM designations"
                " WHERE catalog IN ('M', 'C')"
            )
        }
        self.is_mc = np.array(
            [int(oid) in mc_ids for oid in self.ids], dtype=bool
        )
        self.is_featured = np.array(
            [n in self.featured_names for n in self.names], dtype=bool
        )
        # designação Caldwell (objetos C costumam ter nome principal NGC/IC)
        cald = {
            int(r[0]): f"C {r[1]}" for r in self.cx.execute(
                "SELECT object_id, ident FROM designations WHERE catalog = 'C'"
            )
        }
        self.caldwell_names = [cald.get(int(oid)) for oid in self.ids]

    def __len__(self) -> int:
        return len(self.ids)

    def row_of(self, object_id: int) -> int | None:
        """Posição do objeto nos arrays de render (None se filtrado)."""
        return self._id_to_row.get(int(object_id))

    def label(self, i: int, mode: str = "number",
              prefer_caldwell: bool = True) -> str:
        """Rótulo do objeto no mapa.

        mode 'number': designação de catálogo; 'name': nome comum.
        ``prefer_caldwell`` faz os objetos Caldwell aparecerem como "C 14" em
        vez do NGC/IC correspondente (configurável no menu Exibir).
        """
        if mode == "name" and self.commons[i]:
            return self.commons[i].split(",")[0].strip()
        if prefer_caldwell and not self.names[i].startswith("M "):
            cald = self.caldwell_names[i]
            if cald:
                return cald
        return self.names[i]

    # ------------------------------------------------------------------
    # Consulta / CRUD
    # ------------------------------------------------------------------
    def get(self, object_id: int) -> dict | None:
        """Ficha completa de um objeto: campos + designações + categorias."""
        row = self.cx.execute(
            "SELECT * FROM objects WHERE id = ?", (object_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["designations"] = [
            (r["catalog"], r["ident"]) for r in self.cx.execute(
                "SELECT catalog, ident FROM designations WHERE object_id = ?"
                " ORDER BY catalog", (object_id,)
            )
        ]
        data["categories"] = [
            r["name"] for r in self.cx.execute(
                "SELECT c.name FROM categories c"
                " JOIN object_categories oc ON oc.category_id = c.id"
                " WHERE oc.object_id = ? ORDER BY c.name", (object_id,)
            )
        ]
        return data

    def search(self, text: str = "", catalog: str = "", category: str = "",
               only_enabled: bool = False, limit: int = 500) -> list[dict]:
        """Busca administrativa (gerenciador de DSOs e diálogo de busca).

        Filtros combináveis: substring no nome/nome próprio, catálogo
        ('user' = criados pelo usuário), categoria e habilitação. Sempre
        ordenada por magnitude para os melhores virem primeiro.
        """
        sql = (
            "SELECT DISTINCT o.id, o.name, o.type, o.mag, o.maj, o.con,"
            " o.common, o.enabled, o.user_added FROM objects o"
        )
        wheres, params = [], []
        if catalog == "user":
            wheres.append("o.user_added = 1")
        elif catalog:
            sql += " JOIN designations d ON d.object_id = o.id"
            wheres.append("d.catalog = ?")
            params.append(catalog)
        if category:
            sql += (
                " JOIN object_categories oc ON oc.object_id = o.id"
                " JOIN categories c ON c.id = oc.category_id"
            )
            wheres.append("c.name = ?")
            params.append(category)
        if text:
            wheres.append("(o.name LIKE ? OR o.common LIKE ?)")
            params += [f"%{text}%", f"%{text}%"]
        if only_enabled:
            wheres.append("o.enabled = 1")
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY CASE WHEN o.mag IS NULL THEN 99 ELSE o.mag END LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.cx.execute(sql, params)]

    def count(self, **kw) -> int:
        """Total de objetos que casam com os filtros de :meth:`search`."""
        return len(self.search(limit=10 ** 9, **kw))

    def set_enabled(self, object_id: int, enabled: bool) -> None:
        """Habilita/desabilita um objeto (chame :meth:`reload` depois)."""
        self.cx.execute(
            "UPDATE objects SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, object_id),
        )
        self.cx.commit()

    def upsert(self, data: dict, object_id: int | None = None) -> int:
        """Cria (marcando ``user_added``) ou atualiza um objeto do usuário."""
        fields = (
            "name", "type", "klass", "ra", "dec", "mag", "maj", "min", "pa",
            "con", "common", "enabled", "notes",
        )
        values = [data.get(f) for f in fields]
        if object_id is None:
            cur = self.cx.execute(
                f"INSERT INTO objects ({', '.join(fields)}, user_added)"
                f" VALUES ({', '.join('?' * len(fields))}, 1)", values,
            )
            object_id = cur.lastrowid
        else:
            sets = ", ".join(f"{f} = ?" for f in fields)
            self.cx.execute(
                f"UPDATE objects SET {sets} WHERE id = ?", values + [object_id]
            )
        self.set_categories(object_id, data.get("categories", []))
        self.cx.commit()
        return object_id

    def delete(self, object_id: int) -> None:
        """Remove um objeto; as designações caem via chave estrangeira."""
        self.cx.execute("DELETE FROM objects WHERE id = ?", (object_id,))
        self.cx.commit()

    # ------------------------------------------------------------------
    # Categorias (item 6)
    # ------------------------------------------------------------------
    def categories(self) -> list[str]:
        """Todas as categorias existentes, em ordem alfabética."""
        return [
            r["name"] for r in self.cx.execute(
                "SELECT name FROM categories ORDER BY name"
            )
        ]

    def add_category(self, name: str) -> None:
        """Garante a existência de uma categoria (idempotente)."""
        self.cx.execute(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)", (name.strip(),)
        )
        self.cx.commit()

    def remove_category(self, name: str) -> None:
        """Apaga a categoria e seus vínculos (os objetos permanecem)."""
        self.cx.execute("DELETE FROM categories WHERE name = ?", (name,))
        self.cx.commit()

    def set_categories(self, object_id: int, names: list[str]) -> None:
        """Substitui o conjunto de categorias de um objeto pelo dado."""
        self.cx.execute(
            "DELETE FROM object_categories WHERE object_id = ?", (object_id,)
        )
        for name in names:
            self.add_category(name)
            self.cx.execute(
                "INSERT OR IGNORE INTO object_categories"
                " SELECT ?, id FROM categories WHERE name = ?",
                (object_id, name),
            )
        self.cx.commit()

    # ------------------------------------------------------------------
    def restore_default(self) -> None:
        """Descarta a cópia do usuário e recomeça do banco embarcado."""
        self.cx.close()
        shutil.copy2(self.bundled_db, self.user_db)
        self.cx = sqlite3.connect(str(self.user_db))
        self.cx.row_factory = sqlite3.Row
        self.cx.execute("PRAGMA foreign_keys = ON")
        self.reload()
