-- Pharos 0.3: reliable indexing, multi-entity records, and identity profiles.

-- Remove duplicate records left by older re-index runs before adding uniqueness.
CREATE TEMP TABLE IF NOT EXISTS duplicate_fts AS
SELECT fts_rowid FROM records
WHERE id NOT IN (
    SELECT MIN(id) FROM records
    GROUP BY source_id, file_path, line_number, record_hash
);
DELETE FROM records_fts WHERE rowid IN (SELECT fts_rowid FROM duplicate_fts);
DELETE FROM records
WHERE id NOT IN (
    SELECT MIN(id) FROM records
    GROUP BY source_id, file_path, line_number, record_hash
);
DROP TABLE IF EXISTS duplicate_fts;

CREATE UNIQUE INDEX IF NOT EXISTS uq_records_source_file_line_hash
ON records(source_id, file_path, line_number, record_hash);

CREATE TABLE IF NOT EXISTS record_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    service_name TEXT,
    root_domain TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(record_id, entity_type, normalized_value)
);
CREATE INDEX IF NOT EXISTS idx_record_entities_record ON record_entities(record_id);
CREATE INDEX IF NOT EXISTS idx_record_entities_type_value ON record_entities(entity_type, normalized_value);
CREATE INDEX IF NOT EXISTS idx_record_entities_value ON record_entities(normalized_value);

CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_key TEXT NOT NULL UNIQUE,
    primary_email TEXT NOT NULL,
    display_name TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    risk_score INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT,
    last_seen_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_identities_email ON identities(primary_email);
CREATE INDEX IF NOT EXISTS idx_identities_risk ON identities(risk_score DESC);

CREATE TABLE IF NOT EXISTS identity_records (
    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    PRIMARY KEY(identity_id, record_id)
);
CREATE INDEX IF NOT EXISTS idx_identity_records_record ON identity_records(record_id);

CREATE TABLE IF NOT EXISTS identity_entities (
    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT,
    last_seen_at TEXT,
    PRIMARY KEY(identity_id, entity_type, normalized_value)
);
CREATE INDEX IF NOT EXISTS idx_identity_entities_lookup
ON identity_entities(entity_type, normalized_value);

CREATE TABLE IF NOT EXISTS app_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
