"""CSV/TSV cell-level entity extraction."""
from __future__ import annotations

from breachelens.entities.detectors import ExtractedEntities, extract as extract_entities
from breachelens.ingest.format_detection import RecordFormat


def extract_entities(line: str, format: RecordFormat) -> ExtractedEntities:
    """Extract entities from each cell of a CSV/TSV line."""
    delimiter = "\t" if format == RecordFormat.TSV else ","
    cells = line.split(delimiter)
    out = ExtractedEntities()
    for cell in cells:
        cell = cell.strip().strip('"')
        if not cell:
            continue
        sub = extract_entities(cell)
        _merge(out, sub)
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
