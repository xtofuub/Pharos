"""Recursive folder scanner."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from breachelens.errors import NotFoundError, BadRequestError

# Directories we always skip
SKIP_DIRS = {".git", "node_modules", "target", "venv", "__pycache__", ".venv"}


@dataclass
class ScannedFile:
    path: Path
    file_name: str
    extension: str
    size_bytes: int
    mtime: int


def scan_folder(root: Path, allowed_extensions: List[str]) -> List[ScannedFile]:
    """Recursively scan a source folder for files with allowed extensions."""
    if not root.exists():
        raise NotFoundError(f"source folder does not exist: {root}")
    if not root.is_dir():
        raise BadRequestError(f"not a directory: {root}")

    allowed = {e.strip().lower().lstrip(".") for e in allowed_extensions if e.strip()}
    out: List[ScannedFile] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden + noisy dirs in-place (mutates dirnames so os.walk skips them)
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]

        for name in filenames:
            if name.startswith("."):
                continue
            full = Path(dirpath) / name
            ext = full.suffix.lower().lstrip(".")
            if ext not in allowed:
                continue
            try:
                stat = full.stat()
            except OSError:
                continue
            out.append(
                ScannedFile(
                    path=full,
                    file_name=name,
                    extension=ext,
                    size_bytes=stat.st_size,
                    mtime=int(stat.st_mtime),
                )
            )

    out.sort(key=lambda f: f.path)
    return out
