"""État persistant de l'agent (SQLite, aucun serveur à installer).

Sert à trois choses : ne jamais republier deux fois la même chose, garder
l'historique des performances pour la boucle d'optimisation, et suivre les
revenus.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from eve.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS pieces (
    id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    slot TEXT NOT NULL,
    pillar TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pieces_day ON pieces(day);
CREATE INDEX IF NOT EXISTS idx_pieces_status ON pieces(status);

CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    piece_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    post_id TEXT,
    url TEXT,
    ok INTEGER NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 0,
    detail TEXT,
    published_at TEXT NOT NULL,
    UNIQUE(piece_id, platform)
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    piece_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_piece ON metrics(piece_id);

CREATE TABLE IF NOT EXISTS revenue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    source TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else settings.paths.db
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------- pieces
    def save_piece(self, piece_id: str, day: str, slot: str, pillar: str,
                   payload: dict, status: str = "draft") -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO pieces (id, day, slot, pillar, status, payload, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     status=excluded.status, payload=excluded.payload, updated_at=excluded.updated_at""",
                (piece_id, day, slot, pillar, status, json.dumps(payload, ensure_ascii=False),
                 _now(), _now()),
            )

    def set_status(self, piece_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE pieces SET status=?, updated_at=? WHERE id=?",
                         (status, _now(), piece_id))

    def get_piece(self, piece_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM pieces WHERE id=?", (piece_id,)).fetchone()
        return dict(row) if row else None

    def pieces_by_status(self, status: str, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pieces WHERE status=? ORDER BY day, slot LIMIT ?",
                (status, limit)).fetchall()
        return [dict(r) for r in rows]

    def due_pieces(self, until_day: str, limit: int = 20) -> list[dict]:
        """Contenus validés dont la date est arrivée."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM pieces WHERE status IN ('approved','ready')
                   AND day <= ? ORDER BY day, slot LIMIT ?""",
                (until_day, limit)).fetchall()
        return [dict(r) for r in rows]

    def is_published(self, piece_id: str, platform: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM publications WHERE piece_id=? AND platform=? AND ok=1",
                (piece_id, platform)).fetchone()
        return row is not None

    # ------------------------------------------------------- publications
    def record_publication(self, piece_id: str, platform: str, ok: bool,
                           post_id: str = "", url: str = "", detail: str = "",
                           dry_run: bool = False) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO publications (piece_id, platform, post_id, url, ok, dry_run, detail, published_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(piece_id, platform) DO UPDATE SET
                     post_id=excluded.post_id, url=excluded.url, ok=excluded.ok,
                     dry_run=excluded.dry_run, detail=excluded.detail,
                     published_at=excluded.published_at""",
                (piece_id, platform, post_id, url, int(ok), int(dry_run), detail, _now()),
            )

    def publications(self, limit: int = 100, only_live: bool = False) -> list[dict]:
        query = "SELECT * FROM publications WHERE ok=1"
        if only_live:
            query += " AND dry_run=0"
        query += " ORDER BY published_at DESC LIMIT ?"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, (limit,)).fetchall()]

    # ------------------------------------------------------------ metrics
    def record_metrics(self, piece_id: str, platform: str, payload: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO metrics (piece_id, platform, collected_at, payload) VALUES (?,?,?,?)",
                (piece_id, platform, _now(), json.dumps(payload, ensure_ascii=False)))

    def latest_metrics(self, limit: int = 200) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT m.piece_id, m.platform, m.payload, p.pillar, p.day
                   FROM metrics m JOIN pieces p ON p.id = m.piece_id
                   ORDER BY m.collected_at DESC LIMIT ?""", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    # ------------------------------------------------------------ revenue
    def add_revenue(self, day: str, source: str, amount_usd: float, note: str = "") -> None:
        with self._conn() as conn:
            conn.execute("INSERT INTO revenue (day, source, amount_usd, note) VALUES (?,?,?,?)",
                         (day, source, amount_usd, note))

    def revenue_rows(self, since: str = "0000-00-00") -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM revenue WHERE day >= ? ORDER BY day", (since,)).fetchall()]

    # ----------------------------------------------------------------- kv
    def set_kv(self, key: str, value: object) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO kv (key, value, updated_at) VALUES (?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, json.dumps(value, ensure_ascii=False), _now()))

    def get_kv(self, key: str, default=None):
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def stats(self) -> dict:
        with self._conn() as conn:
            def one(q: str) -> int:
                return conn.execute(q).fetchone()[0]
            return {
                "pieces": one("SELECT COUNT(*) FROM pieces"),
                "approved": one("SELECT COUNT(*) FROM pieces WHERE status IN ('approved','ready')"),
                "published": one("SELECT COUNT(*) FROM publications WHERE ok=1 AND dry_run=0"),
                "dry_runs": one("SELECT COUNT(*) FROM publications WHERE dry_run=1"),
                "metrics_rows": one("SELECT COUNT(*) FROM metrics"),
                "revenue_usd": conn.execute(
                    "SELECT COALESCE(SUM(amount_usd),0) FROM revenue").fetchone()[0],
            }
