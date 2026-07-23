"""Privacy-preserving audit logging."""
from __future__ import annotations

import json
from typing import List, Optional

from breachelens.db import Database
from breachelens.entities.dedupe import query_hash


class AuditLogger:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def log_search(
        self,
        user: str,
        query: str,
        query_type: str,
        filters_used: Optional[List[str]],
        result_count: int,
        source_ip: Optional[str] = None,
    ) -> None:
        qhash = query_hash(query)
        filters_json = json.dumps(filters_used) if filters_used else None
        await self.db.execute(
            """
            INSERT INTO audit_logs (user, action, query_hash, query_type, filters_used,
                                     result_count, reveal_event, source_ip)
            VALUES (?, 'search.execute', ?, ?, ?, ?, 0, ?)
            """,
            (user, qhash, query_type, filters_json, result_count, source_ip),
        )

    async def log_reveal(
        self,
        user: str,
        record_id: str,
        source_file: str,
        line_number: int,
        query_hash_str: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO audit_logs (user, action, query_hash, result_count, reveal_event, source_ip)
            VALUES (?, 'result.reveal', ?, 1, 1, ?)
            """,
            (user, query_hash_str, source_ip),
        )
        await self.db.execute(
            """
            INSERT INTO reveal_events (record_id, source_file, line_number, user, session_id, confirmation_token)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (record_id, source_file, line_number, user, "session", "confirmed"),
        )

    async def log_index_event(
        self,
        user: str,
        action: str,
        source_id: Optional[int] = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO audit_logs (user, action, result_count, reveal_event, source_id)
            VALUES (?, ?, 0, 0, ?)
            """,
            (user, action, source_id),
        )


async def list_audit_entries(db: Database, limit: int = 100) -> List[dict]:
    rows = await db.fetchall(
        """
        SELECT id, timestamp, user, action, query_hash, query_type, filters_used,
               result_count, reveal_event, source_id, source_ip
        FROM audit_logs ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    )
    out = []
    for r in rows:
        d = dict(r)
        d["reveal_event"] = bool(d.get("reveal_event", 0))
        out.append(d)
    return out
