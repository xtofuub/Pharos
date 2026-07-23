"""Stealer-log style parser: extract entities from labeled `URL:` / `Username:` / `Password:` lines."""
from __future__ import annotations

import re

from breachelens.entities.detectors import (
    DetectedSecret,
    ExtractedEntities,
    extract as extract_generic,
)
from breachelens.entities.url_normalizer import normalize as normalize_url
from breachelens.security.masking import mask_value

RE_LABELED = re.compile(
    r"^\s*(URL|Host|Login|Username|User|Email|Password|Passwd|Pass|Pwd|Token|Cookie|Session|IP)\s*[:=]\s*(.+?)\s*$",
    re.IGNORECASE,
)


def extract_entities(line: str) -> ExtractedEntities:
    out = ExtractedEntities()
    m = RE_LABELED.match(line)
    if m:
        label = m.group(1).lower()
        value = m.group(2).strip()
        if label in ("url", "host"):
            normalized = normalize_url(value)
            if normalized is not None:
                out.urls.append(normalized)
        elif label == "email":
            out.emails.append(value.lower())
            if "@" in value:
                out.email_domains.append(value.split("@", 1)[1])
        elif label in ("username", "user", "login"):
            out.usernames.append(value)
        elif label in ("password", "passwd", "pass", "pwd"):
            out.possible_passwords.append(value)
        elif label in ("token", "cookie", "session"):
            out.secrets.append(
                DetectedSecret(
                    kind=label,
                    masked=mask_value(value, 4),
                    length=len(value),
                )
            )

    # Also run generic detectors (catches hashes, IPs, etc.)
    generic = extract_generic(line)
    # Dedupe URLs by normalized form
    for url in generic.urls:
        if not any(u.normalized == url.normalized for u in out.urls):
            out.urls.append(url)
    out.emails.extend(generic.emails)
    out.email_domains.extend(generic.email_domains)
    out.usernames.extend(generic.usernames)
    out.phones.extend(generic.phones)
    out.ipv4s.extend(generic.ipv4s)
    out.ipv6s.extend(generic.ipv6s)
    out.hashes.extend(generic.hashes)
    out.secrets.extend(generic.secrets)
    out.possible_passwords.extend(generic.possible_passwords)
    return out
