"""Deduplication hashes + query hashing for audit log."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class DedupeHashes:
    record_hash: str
    account_hash: Optional[str]
    url_hash: Optional[str]
    service_account_hash: Optional[str]


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_hashes(
    raw_line: str,
    service_name: Optional[str],
    email: Optional[str],
    username: Optional[str],
    normalized_url: Optional[str],
) -> DedupeHashes:
    """Compute dedupe hashes for a parsed record."""
    record_hash = _sha256(raw_line)

    account = email or username
    svc = service_name or ""
    account_hash = (
        _sha256(f"{svc}|{account.lower()}") if account else None
    )

    url_hash = _sha256(normalized_url) if normalized_url else None

    service_account_hash = (
        _sha256(f"{svc.lower()}|{account.lower()}") if account else None
    )

    return DedupeHashes(
        record_hash=record_hash,
        account_hash=account_hash,
        url_hash=url_hash,
        service_account_hash=service_account_hash,
    )


def query_hash(query: str) -> str:
    """Privacy-preserving query hash for the audit log."""
    normalized = query.strip().lower()
    h = _sha256(normalized)
    return f"q_{h[:16]}"
