"""Entity detectors: extract emails, URLs, usernames, hashes, IPs, secrets from a line."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class NormalizedUrl:
    original: str
    normalized: str
    scheme: str
    host: str
    root_domain: str
    subdomain: Optional[str]
    path: str
    path_family: str
    endpoint_type: str
    service_name: Optional[str]
    query_param_names: List[str] = field(default_factory=list)


@dataclass
class DetectedHash:
    value: str
    algorithm: str  # md5 | sha1 | sha256 | generic


@dataclass
class DetectedSecret:
    kind: str  # api_key | token | jwt | credit_card | session | cookie
    masked: str
    length: int


@dataclass
class ExtractedEntities:
    urls: List[NormalizedUrl] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    email_domains: List[str] = field(default_factory=list)
    usernames: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    ipv4s: List[str] = field(default_factory=list)
    ipv6s: List[str] = field(default_factory=list)
    hashes: List[DetectedHash] = field(default_factory=list)
    secrets: List[DetectedSecret] = field(default_factory=list)
    possible_passwords: List[str] = field(default_factory=list)

    def merge_into_searchable_text(self, text: str) -> str:
        parts = [text]
        for u in self.urls:
            parts.append(u.normalized)
        parts.extend(self.emails)
        parts.extend(self.usernames)
        for h in self.hashes:
            parts.append(h.value)
        return " ".join(parts)


# Pre-compiled regexes (module-level for reuse)
RE_EMAIL = re.compile(r"\b([a-z0-9._%+\-]{1,64})@([a-z0-9.\-]+\.[a-z]{2,})\b", re.IGNORECASE)
RE_URL = re.compile(r"\bhttps?://[a-z0-9.\-]+(?::\d+)?(?:/[^\s<>',;]*)?", re.IGNORECASE)
RE_USERNAME_LABEL = re.compile(
    r"(?:^|\s|[,;|])(?:username|user|login|account|uid)\s*[:=]\s*([a-z0-9._@\-]{2,64})",
    re.IGNORECASE,
)
RE_PHONE = re.compile(r"\+?\d{1,3}?[ .\-]?\(?\d{1,4}?\)?[ .\-]?\d{3,4}[ .\-]?\d{3,4}\b")
RE_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
RE_IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")
RE_MD5 = re.compile(r"\b[a-fA-F0-9]{32}\b")
RE_SHA1 = re.compile(r"\b[a-fA-F0-9]{40}\b")
RE_SHA256 = re.compile(r"\b[a-fA-F0-9]{64}\b")
RE_GENERIC_HASH = re.compile(r"\b[a-fA-F0-9]{16,128}\b")
RE_PASSWORD_LABEL = re.compile(
    r"(?:^|\s|[,;|])(?:password|passwd|pass|pwd)\s*[:=]\s*(\S{1,256})",
    re.IGNORECASE,
)
RE_BEARER_TOKEN = re.compile(
    r"\b(?:bearer|token|api[_-]?key|secret)\s*[:=]\s*([a-z0-9_\-.]{20,256})",
    re.IGNORECASE,
)
RE_JWT = re.compile(r"\beyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\b")
RE_CREDIT_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def extract(line: str) -> ExtractedEntities:
    """Extract all entities from a single line of text."""
    out = ExtractedEntities()

    # URLs first (so we can exclude URL substrings from email/hash detection)
    url_spans: List[tuple[int, int]] = []
    for m in RE_URL.finditer(line):
        raw = m.group(0).rstrip(".,;)]")
        normalized = _normalize_url(raw)
        if normalized is not None:
            url_spans.append((m.start(), m.end()))
            out.urls.append(normalized)

    # Emails
    for m in RE_EMAIL.finditer(line):
        if _intersects_any(m.start(), m.end(), url_spans):
            continue
        email = m.group(0).lower()
        out.emails.append(email)
        if "@" in email:
            out.email_domains.append(email.split("@", 1)[1])

    # Usernames (labeled only)
    for m in RE_USERNAME_LABEL.finditer(line):
        val = m.group(1)
        if val and val.lower() not in {e.split("@")[0] for e in out.emails}:
            out.usernames.append(val)

    # Phones
    for m in RE_PHONE.finditer(line):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 15:
            out.phones.append(m.group(0).strip())

    # IPs
    for m in RE_IPV4.finditer(line):
        parts = [int(p) for p in m.group(0).split(".") if p.isdigit()]
        if len(parts) == 4 and all(0 <= p <= 255 for p in parts):
            out.ipv4s.append(m.group(0))
    for m in RE_IPV6.finditer(line):
        v = m.group(0)
        if ":" in v and len(v) >= 5:
            out.ipv6s.append(v)

    # Hashes (most specific first, dedupe overlaps)
    hash_spans: List[tuple[int, int]] = []
    for algo, regex in [("md5", RE_MD5), ("sha1", RE_SHA1), ("sha256", RE_SHA256)]:
        for m in regex.finditer(line):
            if _intersects_any(m.start(), m.end(), url_spans) or _intersects_any(
                m.start(), m.end(), hash_spans
            ):
                continue
            out.hashes.append(DetectedHash(value=m.group(0).lower(), algorithm=algo))
            hash_spans.append((m.start(), m.end()))
    for m in RE_GENERIC_HASH.finditer(line):
        if _intersects_any(m.start(), m.end(), url_spans) or _intersects_any(
            m.start(), m.end(), hash_spans
        ):
            continue
        if 16 <= len(m.group(0)) <= 128:
            out.hashes.append(DetectedHash(value=m.group(0).lower(), algorithm="generic"))
            hash_spans.append((m.start(), m.end()))

    # Passwords (labeled)
    for m in RE_PASSWORD_LABEL.finditer(line):
        out.possible_passwords.append(m.group(1))

    # Secrets
    for m in RE_BEARER_TOKEN.finditer(line):
        v = m.group(1)
        out.secrets.append(
            DetectedSecret(kind="token", masked=_mask_value(v, 2), length=len(v))
        )
    for m in RE_JWT.finditer(line):
        v = m.group(0)
        out.secrets.append(
            DetectedSecret(kind="jwt", masked=_mask_value(v, 8), length=len(v))
        )
    for m in RE_CREDIT_CARD.finditer(line):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            out.secrets.append(
                DetectedSecret(
                    kind="credit_card",
                    masked=_mask_value(digits, 4),
                    length=len(digits),
                )
            )

    return out


def _intersects_any(start: int, end: int, spans: List[tuple[int, int]]) -> bool:
    return any(start < e and end > s for s, e in spans)


def _luhn_valid(digits: str) -> bool:
    total = 0
    double = False
    for ch in reversed(digits):
        d = int(ch)
        if double:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        double = not double
    return total % 10 == 0


def _mask_value(value: str, visible: int) -> str:
    """Mask a value, keeping `visible` chars at start and end."""
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "•" * max(4, len(value))
    head = value[:visible]
    tail = value[-visible:]
    masked_len = min(20, max(6, len(value) - visible * 2))
    return f"{head}{'•' * masked_len}{tail}"


def _normalize_url(raw: str) -> Optional[NormalizedUrl]:
    """Defer to url_normalizer to avoid circular import."""
    from breachelens.entities.url_normalizer import normalize

    return normalize(raw)
