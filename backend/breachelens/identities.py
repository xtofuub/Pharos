"""Identity profile clustering built from repeated normalized email addresses."""
from __future__ import annotations

import hashlib

from breachelens.db import Database


def canonicalize_email(email: str) -> str:
    """Normalize an email for identity grouping without over-merging unrelated people."""
    value = email.strip().lower()
    if "@" not in value:
        return value
    local, domain = value.rsplit("@", 1)
    domain = domain.strip().rstrip(".")
    if domain == "googlemail.com":
        domain = "gmail.com"
    if domain == "gmail.com":
        local = local.split("+", 1)[0].replace(".", "")
    return f"{local}@{domain}"


def identity_key(email: str) -> str:
    return hashlib.sha256(canonicalize_email(email).encode("utf-8")).hexdigest()


async def rebuild_identities(db: Database) -> None:
    """Rebuild derived identity tables from current indexed entities."""
    async with db._lock:
        conn = db.conn
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await conn.execute("DELETE FROM identity_entities")
            await conn.execute("DELETE FROM identity_records")
            await conn.execute("DELETE FROM identities")

            cur = await conn.execute(
                """
                SELECT DISTINCT value
                FROM record_entities
                WHERE entity_type = 'email' AND normalized_value <> ''
                ORDER BY normalized_value
                """
            )
            emails = [row[0] for row in await cur.fetchall()]

            canonical_to_variants: dict[str, set[str]] = {}
            for email in emails:
                canonical_to_variants.setdefault(canonicalize_email(email), set()).add(email)

            for canonical, variants in canonical_to_variants.items():
                key = identity_key(canonical)
                primary = sorted(variants, key=lambda x: (len(x), x))[0]
                cur = await conn.execute(
                    """
                    INSERT INTO identities(identity_key, primary_email, display_name)
                    VALUES (?, ?, ?)
                    """,
                    (key, primary, primary.split("@", 1)[0]),
                )
                identity_id = cur.lastrowid

                placeholders = ",".join("?" for _ in variants)
                variant_values = [v.lower() for v in variants]
                await conn.execute(
                    f"""
                    INSERT OR IGNORE INTO identity_records(identity_id, record_id)
                    SELECT ?, record_id
                    FROM record_entities
                    WHERE entity_type = 'email'
                      AND lower(value) IN ({placeholders})
                    """,
                    [identity_id, *variant_values],
                )

                await conn.execute(
                    """
                    INSERT INTO identity_entities(
                        identity_id, entity_type, value, normalized_value,
                        occurrence_count, first_seen_at, last_seen_at
                    )
                    SELECT ?, re.entity_type, MIN(re.value), re.normalized_value,
                           COUNT(*), MIN(r.created_at), MAX(r.created_at)
                    FROM identity_records ir
                    JOIN record_entities re ON re.record_id = ir.record_id
                    JOIN records r ON r.id = ir.record_id
                    WHERE ir.identity_id = ?
                    GROUP BY re.entity_type, re.normalized_value
                    """,
                    (identity_id, identity_id),
                )

                await conn.execute(
                    """
                    UPDATE identities
                    SET record_count = (
                            SELECT COUNT(*) FROM identity_records WHERE identity_id = ?
                        ),
                        source_count = (
                            SELECT COUNT(DISTINCT r.source_id)
                            FROM identity_records ir
                            JOIN records r ON r.id = ir.record_id
                            WHERE ir.identity_id = ?
                        ),
                        first_seen_at = (
                            SELECT MIN(r.created_at)
                            FROM identity_records ir
                            JOIN records r ON r.id = ir.record_id
                            WHERE ir.identity_id = ?
                        ),
                        last_seen_at = (
                            SELECT MAX(r.created_at)
                            FROM identity_records ir
                            JOIN records r ON r.id = ir.record_id
                            WHERE ir.identity_id = ?
                        ),
                        risk_score = MIN(100,
                            10
                            + 5 * (SELECT COUNT(*) FROM identity_records WHERE identity_id = ?)
                            + 8 * (SELECT COUNT(*) FROM identity_entities WHERE identity_id = ? AND entity_type = 'secret_type')
                            + 4 * (SELECT COUNT(*) FROM identity_entities WHERE identity_id = ? AND entity_type IN ('phone','ip','hash'))
                            + 3 * (SELECT COUNT(*) FROM identity_entities WHERE identity_id = ? AND entity_type = 'service')
                        ),
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        identity_id,
                        identity_id,
                        identity_id,
                        identity_id,
                        identity_id,
                        identity_id,
                        identity_id,
                        identity_id,
                        identity_id,
                    ),
                )

            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


async def list_profiles(
    db: Database,
    query: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    offset = (page - 1) * page_size
    q = query.strip().lower()
    params: list[object] = []
    where = "1=1"
    if q:
        where = """
        (
            lower(i.primary_email) LIKE ?
            OR lower(COALESCE(i.display_name, '')) LIKE ?
            OR EXISTS (
                SELECT 1 FROM identity_entities ie
                WHERE ie.identity_id = i.id
                  AND lower(ie.value) LIKE ?
            )
        )
        """
        like = f"%{q}%"
        params = [like, like, like]

    total = await db.fetchval(f"SELECT COUNT(*) FROM identities i WHERE {where}", params) or 0
    rows = await db.fetchall(
        f"""
        SELECT i.*,
               (SELECT COUNT(*) FROM identity_entities ie WHERE ie.identity_id=i.id AND ie.entity_type='email') AS email_count,
               (SELECT COUNT(*) FROM identity_entities ie WHERE ie.identity_id=i.id AND ie.entity_type='username') AS username_count,
               (SELECT COUNT(*) FROM identity_entities ie WHERE ie.identity_id=i.id AND ie.entity_type='service') AS service_count
        FROM identities i
        WHERE {where}
        ORDER BY i.risk_score DESC, i.record_count DESC, i.primary_email ASC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    )
    return {
        "profiles": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_profile(db: Database, profile_id: int) -> dict | None:
    row = await db.fetchone("SELECT * FROM identities WHERE id = ?", (profile_id,))
    if row is None:
        return None
    entities = await db.fetchall(
        """
        SELECT entity_type, value, normalized_value, occurrence_count, first_seen_at, last_seen_at
        FROM identity_entities
        WHERE identity_id = ?
        ORDER BY entity_type, occurrence_count DESC, value
        """,
        (profile_id,),
    )
    records = await db.fetchall(
        """
        SELECT r.id, r.file_name, r.file_path, r.line_number, r.record_format,
               r.service_name, r.root_domain, r.email, r.username, r.created_at,
               substr(r.searchable_text, 1, 240) AS preview
        FROM identity_records ir
        JOIN records r ON r.id = ir.record_id
        WHERE ir.identity_id = ?
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT 200
        """,
        (profile_id,),
    )
    grouped: dict[str, list[dict]] = {}
    for entity in entities:
        item = dict(entity)
        grouped.setdefault(item["entity_type"], []).append(item)
    result = dict(row)
    result["entities"] = grouped
    result["records"] = [dict(r) for r in records]
    return result
