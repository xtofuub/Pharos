"""SQL migrations runner."""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import aiosqlite

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def _load_migrations() -> List[Tuple[int, str]]:
    """Return list of (id, sql) pairs sorted by id."""
    out: List[Tuple[int, str]] = []
    if not MIGRATIONS_DIR.exists():
        return out
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            mid = int(p.stem.split("_")[0])
        except ValueError:
            continue
        out.append((mid, p.read_text(encoding="utf-8")))
    return out


async def run(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await conn.commit()

    cur = await conn.execute("SELECT id FROM schema_migrations ORDER BY id")
    applied = {row[0] for row in await cur.fetchall()}

    for mid, sql in _load_migrations():
        if mid in applied:
            continue
        await conn.executescript(sql)
        await conn.execute("INSERT INTO schema_migrations (id) VALUES (?)", (mid,))
        await conn.commit()
