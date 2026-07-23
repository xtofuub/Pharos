"""Recursive folder scanner."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from breachelens.errors import NotFoundError, BadRequestError

SKIP_DIRS = {".git", "node_modules", "target", "venv", "__pycache__", ".venv"}


@dataclass
class ScannedFile:
    path: Path
    file_name: str
    extension: str
    size_bytes: int
    mtime: int


@dataclass
class ScanResult:
    files: List[ScannedFile] = field(default_factory=list)
    folders_visited: int = 0
    files_seen: int = 0
    files_ignored: int = 0
    errors: List[str] = field(default_factory=list)


def scan_folder_detailed(root: Path, allowed_extensions: List[str]) -> ScanResult:
    """Recursively scan a folder and retain useful diagnostics.

    Hidden folders are no longer skipped automatically because Windows datasets
    are often stored under hidden profile folders. Only known dependency/cache
    directories are excluded.
    """
    if not root.exists():
        raise NotFoundError(f"source folder does not exist: {root}")
    if not root.is_dir():
        raise BadRequestError(f"not a directory: {root}")

    allowed = {e.strip().lower().lstrip(".") for e in allowed_extensions if e.strip()}
    if not allowed:
        raise BadRequestError("at least one allowed file extension is required")

    result = ScanResult()

    def onerror(exc: OSError) -> None:
        filename = getattr(exc, "filename", None) or str(root)
        result.errors.append(f"cannot access {filename}: {exc.strerror or exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror, followlinks=False):
        result.folders_visited += 1
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for name in filenames:
            result.files_seen += 1
            full = Path(dirpath) / name
            ext = full.suffix.lower().lstrip(".")
            if ext not in allowed:
                result.files_ignored += 1
                continue
            try:
                if full.is_symlink() or not full.is_file():
                    result.files_ignored += 1
                    continue
                stat = full.stat()
            except OSError as exc:
                result.errors.append(f"cannot read {full}: {exc}")
                continue
            result.files.append(
                ScannedFile(
                    path=full,
                    file_name=name,
                    extension=ext,
                    size_bytes=stat.st_size,
                    mtime=stat.st_mtime_ns,
                )
            )

    result.files.sort(key=lambda f: str(f.path).lower())
    return result


def scan_folder(root: Path, allowed_extensions: List[str]) -> List[ScannedFile]:
    """Compatibility wrapper returning only matching files."""
    return scan_folder_detailed(root, allowed_extensions).files
