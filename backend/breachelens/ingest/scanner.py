"""Recursive folder scanner with diagnostics."""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from breachelens.errors import BadRequestError, NotFoundError

# Directories we always skip. Hidden folders are skipped separately.
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "venv",
    ".venv",
    "__pycache__",
}


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    file_name: str
    extension: str
    size_bytes: int
    mtime: int


@dataclass
class ScanResult:
    files: List[ScannedFile] = field(default_factory=list)
    skipped_directories: int = 0
    skipped_files: int = 0
    skipped_large_files: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)

    @property
    def extension_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.extension for item in self.files).items()))


def normalize_extensions(extensions: Iterable[str]) -> list[str]:
    """Normalize an extension iterable to unique lowercase values without dots."""
    return sorted({str(ext).strip().lower().lstrip(".") for ext in extensions if str(ext).strip()})


def scan_folder_detailed(
    root: Path,
    allowed_extensions: Iterable[str],
    *,
    max_file_size_bytes: int | None = None,
) -> ScanResult:
    """Recursively scan a folder and return files plus useful diagnostics.

    Permission errors and unreadable files are recorded instead of making the whole
    scan disappear. Symlinks are skipped so a source cannot recurse outside the
    selected folder or loop forever.
    """
    if not root.exists():
        raise NotFoundError(f"source folder does not exist: {root}")
    if not root.is_dir():
        raise BadRequestError(f"not a directory: {root}")

    allowed = set(normalize_extensions(allowed_extensions))
    if not allowed:
        raise BadRequestError("at least one allowed file extension is required")

    result = ScanResult()

    def on_walk_error(exc: OSError) -> None:
        result.skipped_directories += 1
        location = getattr(exc, "filename", None) or str(root)
        result.errors.append(f"Cannot read folder {location}: {exc.strerror or exc}")

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=on_walk_error, followlinks=False):
        kept_dirs: list[str] = []
        for dirname in dirnames:
            candidate = Path(dirpath) / dirname
            if dirname.startswith(".") or dirname.lower() in SKIP_DIRS:
                result.skipped_directories += 1
                continue
            try:
                if candidate.is_symlink():
                    result.skipped_directories += 1
                    continue
            except OSError as exc:
                result.skipped_directories += 1
                result.errors.append(f"Cannot inspect folder {candidate}: {exc}")
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for name in filenames:
            if name.startswith("."):
                result.skipped_files += 1
                continue

            full = Path(dirpath) / name
            ext = full.suffix.lower().lstrip(".")
            if ext not in allowed:
                continue

            try:
                if full.is_symlink() or not full.is_file():
                    result.skipped_files += 1
                    continue
                stat = full.stat()
            except OSError as exc:
                result.skipped_files += 1
                result.errors.append(f"Cannot read file metadata {full}: {exc}")
                continue

            if max_file_size_bytes is not None and stat.st_size > max_file_size_bytes:
                result.skipped_large_files += 1
                continue

            result.files.append(
                ScannedFile(
                    path=full,
                    file_name=name,
                    extension=ext,
                    size_bytes=stat.st_size,
                    # Nanosecond precision prevents missing rapid edits on Windows.
                    mtime=stat.st_mtime_ns,
                )
            )

    result.files.sort(key=lambda item: str(item.path).casefold())
    return result


def scan_folder(root: Path, allowed_extensions: List[str]) -> List[ScannedFile]:
    """Backwards-compatible scanner API returning only matched files."""
    return scan_folder_detailed(root, allowed_extensions).files
