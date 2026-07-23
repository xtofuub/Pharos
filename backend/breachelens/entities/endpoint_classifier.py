"""Endpoint classification: classify URL paths by purpose (login, admin, api, etc.)."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# (endpoint_type, regex pattern) -- evaluated in order, first match wins
DEFAULT_RULES: List[Tuple[str, str]] = [
    ("login", r"(?i)/login"),
    ("login", r"(?i)/signin"),
    ("login", r"(?i)/auth"),
    ("login", r"(?i)/oauth"),
    ("login", r"(?i)/sso"),
    ("signup", r"(?i)/signup"),
    ("signup", r"(?i)/register"),
    ("signup", r"(?i)/join"),
    ("account", r"(?i)/account"),
    ("account", r"(?i)/profile"),
    ("account", r"(?i)/settings"),
    ("admin", r"(?i)/admin"),
    ("admin", r"(?i)/wp-admin"),
    ("admin", r"(?i)/dashboard"),
    ("admin", r"(?i)/manage"),
    ("mail", r"(?i)/mail"),
    ("mail", r"(?i)/inbox"),
    ("mail", r"(?i)/email"),
    ("payment", r"(?i)/payment"),
    ("payment", r"(?i)/checkout"),
    ("payment", r"(?i)/billing"),
    ("banking", r"(?i)/bank"),
    ("banking", r"(?i)/transfer"),
    ("crypto", r"(?i)/wallet"),
    ("crypto", r"(?i)/exchange"),
    ("crypto", r"(?i)/trade"),
    ("developer", r"(?i)/developer"),
    ("developer", r"(?i)/docs"),
    ("api", r"(?i)/api"),
    ("api", r"(?i)/v\d"),
    ("api", r"(?i)/graphql"),
    ("password_reset", r"(?i)/reset"),
    ("password_reset", r"(?i)/forgot"),
    ("password_reset", r"(?i)/recover"),
    ("cloud", r"(?i)/cloud"),
    ("cloud", r"(?i)/drive"),
    ("cloud", r"(?i)/storage"),
]

_COMPILED: List[Tuple[str, re.Pattern]] = []
_CUSTOM: List[Tuple[str, re.Pattern]] = []


def _ensure_compiled() -> None:
    global _COMPILED
    if _COMPILED:
        return
    _COMPILED = [(t, re.compile(p)) for t, p in DEFAULT_RULES]


def populate_custom_rules(rules: List[Tuple[str, str]]) -> None:
    """Load operator-defined endpoint rules from the DB."""
    global _CUSTOM
    _CUSTOM = []
    for endpoint_type, pattern in rules:
        try:
            _CUSTOM.append((endpoint_type, re.compile(pattern)))
        except re.error:
            continue


def classify_endpoint(path: str) -> str:
    """Classify a URL path into an endpoint type. Returns 'unknown' if no rule matches."""
    if not path or path == "/":
        return "unknown"
    _ensure_compiled()
    # Custom rules take precedence (operator overrides)
    for endpoint_type, regex in _CUSTOM:
        if regex.search(path):
            return endpoint_type
    for endpoint_type, regex in _COMPILED:
        if regex.search(path):
            return endpoint_type
    return "unknown"


def endpoint_type_counts(paths: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in paths:
        t = classify_endpoint(p)
        counts[t] = counts.get(t, 0) + 1
    return counts
