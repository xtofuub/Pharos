import asyncio
from pathlib import Path

import pytest

from breachelens.config import Config, IndexingConfig, StorageConfig
from breachelens.db import Database
from breachelens.ingest.index_job import get_current_job, start_indexing
from breachelens.state import AppState


async def wait_for_job(timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while get_current_job() is not None:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("indexing job did not finish")
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_reindex_replaces_changed_rows_and_preserves_unchanged_totals(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / "records.txt"
    source_file.write_text("first@example.com:one\nsecond@example.com:two\n", encoding="utf-8")

    storage_dir = tmp_path / "state"
    config = Config(
        storage=StorageConfig(
            data_dir=storage_dir,
            index_dir=storage_dir / "index",
            db_path=storage_dir / "pharos.db",
        ),
        indexing=IndexingConfig(batch_size=1, skip_unchanged=True),
    )
    db = Database(config.storage.db_path)
    await db.connect()
    await db.run_migrations()
    state = AppState(config=config, db=db)

    try:
        cursor = await db.execute(
            """
            INSERT INTO sources (path, display_name, storage_mode, allowed_extensions, status)
            VALUES (?, 'test', 'offset', '.txt', 'pending')
            """,
            (str(source_dir.resolve()),),
        )
        source_id = int(cursor.lastrowid)

        await start_indexing(state, source_id)
        await wait_for_job()
        first = await db.fetchone(
            "SELECT files_count, records_count, status FROM sources WHERE id = ?",
            (source_id,),
        )
        assert dict(first) == {"files_count": 1, "records_count": 2, "status": "indexed"}
        assert await db.fetchval("SELECT COUNT(*) FROM records WHERE source_id = ?", (source_id,)) == 2

        # A changed file must replace old rows rather than append duplicates.
        source_file.write_text("third@example.com:three\nfourth@example.com:four\n", encoding="utf-8")
        await start_indexing(state, source_id)
        await wait_for_job()
        assert await db.fetchval("SELECT COUNT(*) FROM records WHERE source_id = ?", (source_id,)) == 2

        # An unchanged scan must retain the source totals.
        await start_indexing(state, source_id)
        await wait_for_job()
        unchanged = await db.fetchone(
            "SELECT files_count, records_count, status FROM sources WHERE id = ?",
            (source_id,),
        )
        assert dict(unchanged) == {"files_count": 1, "records_count": 2, "status": "indexed"}
    finally:
        await db.close()
