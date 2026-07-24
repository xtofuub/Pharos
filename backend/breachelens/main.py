"""Pharos backend -- FastAPI bootstrap."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from breachelens import api
from breachelens.config import load_config
from breachelens.db import Database
from breachelens.entities import default_service_mappings, populate_service_cache
from breachelens.errors import AppError, app_error_handler, unhandled_exception_handler
from breachelens.state import AppState

STATIC_DIR = Path(__file__).resolve().parent / "static"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("breachelens")


async def _seed_defaults(state: AppState) -> None:
    rules_count = await state.db.fetchval("SELECT COUNT(*) FROM service_rules")
    if not rules_count:
        for service, domain in default_service_mappings():
            await state.db.execute(
                "INSERT OR IGNORE INTO service_rules(service_name,domain_pattern,added_by) VALUES (?,?,'system')",
                (service, domain),
            )
    rows = await state.db.fetchall("SELECT service_name,domain_pattern FROM service_rules")
    populate_service_cache([(r["domain_pattern"], r["service_name"]) for r in rows])


async def _recover_interrupted_jobs(db: Database) -> None:
    """Clear stale 'running' state left by a crash, forced close, or old executable."""
    interrupted = await db.fetchval("SELECT COUNT(*) FROM index_jobs WHERE status='running'")
    if interrupted:
        await db.execute(
            """
            UPDATE index_jobs
            SET status='interrupted', finished_at=datetime('now'),
                error_message=COALESCE(NULLIF(error_message, ''), 'Pharos stopped before this job completed')
            WHERE status='running'
            """
        )
        await db.execute("UPDATE sources SET status='pending' WHERE status='indexing'")
        log.warning("marked %d abandoned indexing job(s) as interrupted", interrupted)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    log.info("starting Pharos backend bind=%s:%d", config.server.bind_addr, config.server.port)
    config.storage.data_dir.mkdir(parents=True, exist_ok=True)
    config.storage.index_dir.mkdir(parents=True, exist_ok=True)
    config.storage.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(config.storage.db_path)
    await db.connect()
    await db.run_migrations()
    await _recover_interrupted_jobs(db)
    state = AppState(config=config, db=db)
    app.state.app_state = state
    await _seed_defaults(state)
    yield
    await db.close()
    log.info("Pharos backend stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pharos",
        description="Local-first breach intelligence search and identity extraction engine",
        version="0.3.2",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8443", "http://localhost:8443"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Content-Type"],
    )
    for router in (
        api.health_router,
        api.sources_router,
        api.indexing_router,
        api.search_router,
        api.results_router,
        api.aggregations_router,
        api.audit_router,
        api.settings_router,
        api.stats_router,
        api.profiles_router,
        api.maintenance_router,
    ):
        app.include_router(router)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def index():
            return FileResponse(str(STATIC_DIR / "index.html"))

        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404)
            return FileResponse(str(STATIC_DIR / "index.html"))
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    return app


app = create_app()


def main() -> None:
    config = load_config()
    uvicorn.run(
        "breachelens.main:app",
        host=config.server.bind_addr,
        port=config.server.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
