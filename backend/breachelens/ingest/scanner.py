"""Recursive and permission-aware folder scanner."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from breachelens.errors import BadRequestError, NotFoundError

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
    directories_visited: int = 0
    files_seen: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)


def scan_folder_detailed(root: Path, allowed_extensions: List[str]) -> ScanResult:
    if not root.exists():
        raise NotFoundError(f"source folder does not exist: {root}")
    if not root.is_dir():
        raise BadRequestError(f"not a directory: {root}")

    allowed = {e.strip().lower().lstrip(".") for e in allowed_extensions if e.strip()}
    result = ScanResult()

    def onerror(exc: OSError) -> None:
        result.errors.append(f"{getattr(exc, 'filename', root)}: {exc.strerror or exc}")

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=onerror, followlinks=False):
        result.directories_visited += 1
        # Hidden directories may contain relevant user data, so only skip known noisy/build folders.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            result.files_seen += 1
            full = Path(dirpath) / name
            ext = full.suffix.lower().lstrip(".")
            if allowed and ext not in allowed:
                continue
            try:
                if full.is_symlink() or not full.is_file():
                    continue
                stat = full.stat()
            except OSError as exc:
                result.errors.append(f"{full}: {exc}")
                continue
            result.files.append(
                ScannedFile(
                    path=full,
                    file_name=name,
                    extension=ext,
                    size_bytes=stat.st_size,
                    mtime=int(stat.st_mtime),
                )
            )

    result.files.sort(key=lambda item: str(item.path).casefold())
    return result


def scan_folder(root: Path, allowed_extensions: List[str]) -> List[ScannedFile]:
    return scan_folder_detailed(root, allowed_extensions).files
