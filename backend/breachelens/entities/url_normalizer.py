"""URL normalization: split a URL into host, root domain, subdomain, path, endpoint type, service."""
from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse, parse_qs

from breachelens.entities.detectors import NormalizedUrl
from breachelens.entities.endpoint_classifier import classify_endpoint
from breachelens.entities.service_classifier import classify_service

# Known multi-part public suffixes (tiny PSL subset for MVP)
KNOWN_SUFFIXES = {
    "co.uk", "co.jp", "com.au", "com.br", "com.cn", "com.mx", "com.tr",
    "org.uk", "ac.uk", "gov.uk", "co.kr", "com.hk", "com.sg",
}

RE_QUERY_STRIP = re.compile(
    r"\b(token|access_token|refresh_token|jwt|session|sid|code|state|nonce|"
    r"password|passwd|pwd|secret|api_key|apikey|auth)=([^&]+)",
    re.IGNORECASE,
)


def normalize(raw: str) -> Optional[NormalizedUrl]:
    """Normalize a URL string. Returns None if parsing fails or the host is loopback."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except Exception:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https", "ftp"):
        return None

    host = (parsed.hostname or "").lower()
    if not host:
        return None
    # Skip loopback / private ranges
    if host in ("localhost",) or host.startswith(("127.", "192.168.", "10.")):
        return None

    root_domain, subdomain = split_domain(host)
    port = parsed.port
    path = parsed.path.rstrip("/") or ""
    path_family = derive_path_family(path)
    endpoint_type = classify_endpoint(path)
    service_name = classify_service(root_domain)
    query_param_names = list(parse_qs(parsed.query).keys())

    # Build normalized URL: scheme + host (+port) + path (no query, no fragment)
    normalized = f"{scheme}://{host}"
    if port:
        normalized += f":{port}"
    if path and path != "/":
        normalized += path

    return NormalizedUrl(
        original=raw,
        normalized=normalized,
        scheme=scheme,
        host=host,
        root_domain=root_domain,
        subdomain=subdomain,
        path=path,
        path_family=path_family,
        endpoint_type=endpoint_type,
        service_name=service_name,
        query_param_names=query_param_names,
    )


def split_domain(host: str) -> tuple[str, Optional[str]]:
    """Split host into (root_domain, subdomain)."""
    parts = host.split(".")
    if len(parts) <= 2:
        return host, None
    last_two = ".".join(parts[-2:])
    if last_two in KNOWN_SUFFIXES and len(parts) >= 3:
        root = ".".join(parts[-3:])
        sub = ".".join(parts[:-3]) if len(parts) > 3 else None
        return root, sub
    root = ".".join(parts[-2:])
    sub = ".".join(parts[:-2]) if len(parts) > 2 else None
    return root, sub


def derive_path_family(path: str) -> str:
    """Derive a 'path family' from the first 1-2 segments."""
    if not path or path == "/":
        return ""
    segments = [s for s in path.strip("/").split("/") if s]
    if not segments:
        return ""
    if segments[0] == "api" and len(segments) >= 2:
        return "/" + "/".join(segments[:2])
    return "/" + segments[0]


def safe_query_string(query: Optional[str]) -> Optional[str]:
    """Strip sensitive values from a query string (returns param names only)."""
    if not query:
        return None
    cleaned = RE_QUERY_STRIP.sub(r"\1=***", query)
    return cleaned
