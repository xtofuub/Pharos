"""Input validation: paths, queries, regex patterns."""
from __future__ import annotations

import re
from pathlib import Path

from breachelens.errors import PathNotAllowedError, BadRequestError, RegexRejectedError, NotFoundError

CATASTROPHIC_PATTERNS = ["(a+)+", "(a*)*", "(.+)+", ".*.*.*.*.*.*"]


def validate_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        raise PathNotAllowedError(f"path must be absolute: {path}")
    try:
        canonical = p.resolve(strict=True)
    except FileNotFoundError:
        raise NotFoundError(f"path does not exist: {path}")
    return canonical


def validate_source_folder(path: str) -> Path:
    p = validate_path(path)
    if not p.is_dir():
        raise BadRequestError(f"not a directory: {path}")
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
    for c in CATASTROPHIC_PATTERNS:
        if c in pattern:
            raise RegexRejectedError(f"catastrophic backtracking pattern detected: {c}")
