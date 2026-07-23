"""Pharos backend -- FastAPI bootstrap."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from breachelens import api
from breachelens.config import load_config
from breachelens.db import Database
from breachelens.entities import default_service_mappings, populate_service_cache
from breachelens.errors import AppError, app_error_handler, unhandled_exception_handler
from breachelens.security.auth import hash_password
from breachelens.state import AppState

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("breachelens")


async def _seed_defaults(state: AppState) -> None:
    """Seed default admin user + service rules on first run."""
    admin_count = await state.db.fetchval(
        "SELECT COUNT(*) FROM users WHERE username = 'admin'"
    )
    if not admin_count:
        phc = hash_password("breachelens")
        await state.db.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password) VALUES (?, ?, 'admin', 1)",
            ("admin", phc),
        )
        log.info("created default admin user (password: breachelens -- change immediately)")

    rules_count = await state.db.fetchval("SELECT COUNT(*) FROM service_rules")
    if not rules_count:
        for service, domain in default_service_mappings():
            await state.db.execute(
                "INSERT OR IGNORE INTO service_rules (service_name, domain_pattern, added_by) VALUES (?, ?, 'system')",
                (service, domain),
            )
        log.info("seeded default service classification rules")

    rows = await state.db.fetchall(
        "SELECT service_name, domain_pattern FROM service_rules"
    )
    populate_service_cache([(r["domain_pattern"], r["service_name"]) for r in rows])
    log.info("service classifier cache populated (%d rules)", len(rows))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    config = load_config()
    log.info(
        "starting Pharos backend bind=%s:%d",
        config.server.bind_addr,
        config.server.port,
    )

    config.storage.data_dir.mkdir(parents=True, exist_ok=True)
    config.storage.index_dir.mkdir(parents=True, exist_ok=True)
    config.storage.db_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(config.storage.db_path)
    await db.connect()
    await db.run_migrations()

    state = AppState(config=config, db=db)
    app.state.app_state = state
    await _seed_defaults(state)

    yield

    await db.close()
    log.info("Pharos backend stopped")


def _render_frontend() -> HTMLResponse:
    """Serve the dashboard with the small desktop enhancement layer injected."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("BreachLens", "Pharos")
    script_tag = '<script src="/static/pharos-enhancements.js"></script>'
    if script_tag not in html:
        html = html.replace("</body>", f"{script_tag}\n</body>")
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title="Pharos",
        description="Local-first breach intelligence search and entity extraction engine",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8443", "http://localhost:8443"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(api.auth_router)
    app.include_router(api.health_router)
    app.include_router(api.sources_router)
    app.include_router(api.indexing_router)
    app.include_router(api.search_router)
    app.include_router(api.results_router)
    app.include_router(api.aggregations_router)
    app.include_router(api.audit_router)
    app.include_router(api.settings_router)
    app.include_router(api.stats_router)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def index():
            return _render_frontend()

        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            if path.startswith("api/") or path.startswith("auth/"):
                raise HTTPException(status_code=404)
            return _render_frontend()

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    return app


app = create_app()


def main() -> None:
    """Run the server with uvicorn."""
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
