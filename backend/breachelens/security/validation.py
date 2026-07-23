"""Input validation: paths, queries, regex patterns."""
from __future__ import annotations

import os
import re
from pathlib import Path

from breachelens.errors import PathNotAllowedError, BadRequestError, RegexRejectedError, NotFoundError

CATASTROPHIC_PATTERNS = ["(a+)+", "(a*)*", "(.+)+", ".*.*.*.*.*.*"]


def normalize_user_path(path: str) -> str:
    """Normalize paths pasted from Windows Explorer or a terminal.

    Accepts surrounding quotes, environment variables such as ``%USERPROFILE%``,
    forward slashes on Windows, and ``~``. Browser file inputs often return a
    useless ``C:\\fakepath`` value, so reject that with a useful explanation.
    """
    value = (path or "").strip().strip('"').strip("'").strip()
    if not value:
        raise BadRequestError("folder path must not be empty")
    if "fakepath" in value.lower():
        raise BadRequestError(
            "the browser did not provide the real folder path; use Browse folder or paste the path from File Explorer"
        )
    value = os.path.expandvars(os.path.expanduser(value))
    return value


def validate_path(path: str) -> Path:
    normalized = normalize_user_path(path)
    p = Path(normalized)
    if not p.is_absolute():
        raise PathNotAllowedError(f"path must be absolute: {normalized}")
    try:
        canonical = p.resolve(strict=True)
    except FileNotFoundError:
        raise NotFoundError(f"path does not exist: {normalized}")
    except OSError as exc:
        raise PathNotAllowedError(f"cannot access path: {normalized} ({exc})") from exc
    return canonical


def validate_source_folder(path: str) -> Path:
    p = validate_path(path)
    if not p.is_dir():
        raise BadRequestError(f"not a directory: {p}")
    if not os.access(p, os.R_OK):
        raise PathNotAllowedError(f"folder is not readable: {p}")
    return p


def sanitize_query(q: str) -> str:
    trimmed = q.strip()
    if not trimmed:
        raise BadRequestError("query must not be empty")
    if len(trimmed) > 1024:
        raise BadRequestError("query too long (max 1024 chars)")
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
