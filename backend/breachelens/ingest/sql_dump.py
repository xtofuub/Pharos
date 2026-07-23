"""SQL dump parser: extract entities from INSERT INTO statements."""
from __future__ import annotations

import re

from breachelens.entities.detectors import ExtractedEntities, extract as extract_entities

RE_INSERT = re.compile(
    r"INSERT\s+INTO\s+\S+(?:\s*\([^)]*\))?\s+VALUES\s*\((.*?)\)\s*;?",
    re.IGNORECASE | re.DOTALL,
)


def extract_entities(line: str) -> ExtractedEntities:
    out = ExtractedEntities()
    matched_anything = False
    for m in RE_INSERT.finditer(line):
        values_str = m.group(1)
        for value in _split_sql_values(values_str):
            v = value.strip().strip("'").strip('"')
            if not v:
                continue
            sub = extract_entities(v)
            _merge(out, sub)
            matched_anything = True

    if not matched_anything:
        return extract_entities(line)
    return out


def _split_sql_values(s: str) -> list[str]:
    """Naive SQL value splitter that respects single-quoted strings."""
    out: list[str] = []
    current: list[str] = []
    in_string = False
    prev = ""
    for ch in s:
        if ch == "'" and prev != "\\":
            in_string = not in_string
            current.append(ch)
        elif ch == "," and not in_string:
            out.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        prev = ch
    if current:
        last = "".join(current).strip()
        if last:
            out.append(last)
    return out


def _merge(into: ExtractedEntities, frm: ExtractedEntities) -> None:
    into.urls.extend(frm.urls)
    into.emails.extend(frm.emails)
    into.email_domains.extend(frm.email_domains)
    into.usernames.extend(frm.usernames)
    into.phones.extend(frm.phones)
    into.ipv4s.extend(frm.ipv4s)
    into.ipv6s.extend(frm.ipv6s)
    into.hashes.extend(frm.hashes)
    into.secrets.extend(frm.secrets)
    into.possible_passwords.extend(frm.possible_passwords)
