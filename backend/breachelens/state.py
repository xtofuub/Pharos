"""Shared application state passed to every FastAPI handler."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from breachelens.config import Config
from breachelens.db import Database
from breachelens.security.auth import SessionStore


@dataclass
class AppState:
    config: Config
    db: Database
    sessions: SessionStore = field(default_factory=SessionStore)
    # Current indexing job (set/cleared by ingest.index_job)
    # We store the job ID + source_id here so the status endpoint can read it
    # without touching the DB.
    current_job_id: Optional[int] = None
