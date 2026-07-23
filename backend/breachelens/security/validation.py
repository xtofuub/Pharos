"""Input validation: paths, queries, regex patterns."""
from __future__ import annotations

import os
import re
from pathlib import Path

from breachelens.errors import BadRequestError, NotFoundError, PathNotAllowedError, RegexRejectedError

CATASTROPHIC_PATTERNS = ["(a+)+", "(a*)*", "(.+)+", ".*.*.*.*.*.*"]


def clean_local_path(path: str) -> str:
    """Clean a path copied from Explorer, a terminal, or a quoted dialog."""
    cleaned = str(path or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    cleaned = os.path.expandvars(os.path.expanduser(cleaned))
    if not cleaned:
        raise BadRequestError("folder path is required")
    return cleaned


def validate_path(path: str) -> Path:
    cleaned = clean_local_path(path)
    p = Path(cleaned)
    if not p.is_absolute():
        raise PathNotAllowedError(f"path must be absolute: {cleaned}")
    try:
        canonical = p.resolve(strict=True)
    except FileNotFoundError:
        raise NotFoundError(f"path does not exist: {cleaned}")
    except OSError as exc:
        raise PathNotAllowedError(f"cannot resolve path {cleaned}: {exc}")
    return canonical


def validate_source_folder(path: str) -> Path:
    p = validate_path(path)
    if not p.is_dir():
        raise BadRequestError(f"not a directory: {p}")
    try:
        # Opening the directory catches common Windows ACL and disconnected-drive
        # problems earlier than the background indexer.
        with os.scandir(p) as entries:
            next(entries, None)
    except PermissionError as exc:
        raise PathNotAllowedError(f"folder is not readable: {p} ({exc})")
    except OSError as exc:
        raise PathNotAllowedError(f"cannot access folder: {p} ({exc})")
    return p


def sanitize_query(q: str) -> str:
    trimmed = q.strip()
    if not trimmed:
        raise BadRequestError("query must not be empty")
    if len(trimmed) > 1024:
        raise BadRequestError("query too long (max 1024 chars)")
    # Strip control characters (except tab)
    return "".join(ch for ch in trimmed if ord(ch) >= 32 or ch == "\t")


def validate_regex(pattern: str, max_length: int = 256) -> None:
    if len(pattern) > max_length:
        raise RegexRejectedError(f"pattern exceeds max length ({max_length} chars)")
    try:
        re.compile(pattern)
    except re.error as e:
        raise RegexRejectedError(f"invalid regex: {e}")
    for candidate in CATASTROPHIC_PATTERNS:
        if candidate in pattern:
            raise RegexRejectedError(f"catastrophic backtracking pattern detected: {candidate}")
