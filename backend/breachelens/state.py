"""Shared application state passed to every FastAPI handler."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from breachelens.config import Config
from breachelens.db import Database


@dataclass
class AppState:
    config: Config
    db: Database
    # Current indexing job (set/cleared by ingest.index_job).
    current_job_id: Optional[int] = None
