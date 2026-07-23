"""SQLite database layer using aiosqlite."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import aiosqlite
import regex as safe_regex

from breachelens.errors import DatabaseError

from . import migrations


class Database:
    """Async wrapper around a single aiosqlite connection (serialized writes)."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        if self._conn is not None:
            return
        # Ensure parent dir exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")

        def _regexp(pattern: str, value: str | None) -> int:
            if value is None:
                return 0
            try:
                return 1 if safe_regex.search(pattern, value, timeout=0.025) else 0
            except (TimeoutError, safe_regex.error):
                return 0

        await self._conn.create_function("REGEXP", 2, _regexp)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise DatabaseError("database not connected")
        return self._conn

    async def run_migrations(self) -> None:
        async with self._lock:
            await migrations.run(self.conn)

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Cursor:
        async with self._lock:
            cur = await self.conn.execute(sql, params)
            await self.conn.commit()
            return cur

    async def executemany(self, sql: str, params_seq: Iterable[Sequence[Any]]) -> None:
        async with self._lock:
            await self.conn.executemany(sql, list(params_seq))
            await self.conn.commit()

    async def execute_batch(self, sql: str, params_list: List[Tuple[Any, ...]]) -> None:
        """Execute many INSERTs in a single transaction (atomic)."""
        async with self._lock:
            cur = await self.conn.cursor()
            await cur.executemany(sql, params_list)
            await self.conn.commit()

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[aiosqlite.Row]:
        async with self._lock:
            cur = await self.conn.execute(sql, params)
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[aiosqlite.Row]:
        async with self._lock:
            cur = await self.conn.execute(sql, params)
            return await cur.fetchall()

    async def fetchval(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = await self.fetchone(sql, params)
        if row is None:
            return None
        return row[0]
