"""Input validation for local paths, queries, and regular expressions."""
from __future__ import annotations

import os
import re
from pathlib import Path

from breachelens.errors import BadRequestError, NotFoundError, PathNotAllowedError, RegexRejectedError

CATASTROPHIC_PATTERNS = ["(a+)+", "(a*)*", "(.+)+", ".*.*.*.*.*.*"]


def normalize_user_path(path: str) -> str:
    value = path.strip().strip('"').strip("'")
    if not value:
        raise BadRequestError("folder path is required")
    if "fakepath" in value.lower():
        raise BadRequestError("the browser supplied a fake path; use the Browse button or paste the full folder path")
    value = os.path.expandvars(os.path.expanduser(value))
    # Windows users frequently paste forward-slash paths or paths with surrounding whitespace.
    if os.name == "nt":
        value = value.replace("/", "\\")
    return value


def validate_path(path: str) -> Path:
    value = normalize_user_path(path)
    p = Path(value)
    if not p.is_absolute():
        raise PathNotAllowedError(f"path must be absolute: {value}")
    try:
        canonical = p.resolve(strict=True)
    except FileNotFoundError:
        raise NotFoundError(f"path does not exist: {value}")
    except OSError as exc:
        raise PathNotAllowedError(f"cannot access path: {exc}")
    return canonical


def validate_source_folder(path: str) -> Path:
    p = validate_path(path)
    if not p.is_dir():
        raise BadRequestError(f"not a directory: {path}")
    if not os.access(p, os.R_OK):
        raise PathNotAllowedError(f"folder is not readable: {p}")
    return p


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


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
    except re.error as exc:
        raise RegexRejectedError(f"invalid regex: {exc}")
    for candidate in CATASTROPHIC_PATTERNS:
        if candidate in pattern:
            raise RegexRejectedError(f"catastrophic backtracking pattern detected: {candidate}")
