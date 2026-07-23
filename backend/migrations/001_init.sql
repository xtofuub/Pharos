-- 001_init.sql -- initial BreachLens schema

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    totp_secret TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    display_name TEXT,
    storage_mode TEXT NOT NULL DEFAULT 'offset',
    allowed_extensions TEXT NOT NULL DEFAULT '.txt,.csv,.tsv,.log,.jsonl,.sql',
    status TEXT NOT NULL DEFAULT 'pending',
    files_count INTEGER NOT NULL DEFAULT 0,
    records_count INTEGER NOT NULL DEFAULT 0,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    last_indexed_at TEXT,
    authorized_by TEXT,
    authorized_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    line_count INTEGER NOT NULL DEFAULT 0,
    records_indexed INTEGER NOT NULL DEFAULT 0,
    mtime INTEGER NOT NULL DEFAULT 0,
    detected_format TEXT,
    last_indexed_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    UNIQUE(source_id, path)
);
CREATE INDEX IF NOT EXISTS idx_files_source ON files(source_id);
CREATE INDEX IF NOT EXISTS idx_files_ext ON files(extension);

CREATE TABLE IF NOT EXISTS index_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    files_total INTEGER NOT NULL DEFAULT 0,
    files_processed INTEGER NOT NULL DEFAULT 0,
    files_skipped INTEGER NOT NULL DEFAULT 0,
    records_indexed INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    throughput_lps REAL NOT NULL DEFAULT 0,
    throughput_mbs REAL NOT NULL DEFAULT 0,
    current_file TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON index_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON index_jobs(status);

CREATE TABLE IF NOT EXISTS index_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES index_jobs(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_errors_job ON index_errors(job_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    user TEXT NOT NULL,
    action TEXT NOT NULL,
    query_hash TEXT,
    query_type TEXT,
    filters_used TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    reveal_event INTEGER NOT NULL DEFAULT 0,
    source_id INTEGER,
    source_ip TEXT,
    prev_hash TEXT,
    row_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS service_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    domain_pattern TEXT NOT NULL,
    category TEXT,
    added_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(service_name, domain_pattern)
);
CREATE INDEX IF NOT EXISTS idx_service_rules_domain ON service_rules(domain_pattern);

CREATE TABLE IF NOT EXISTS endpoint_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_type TEXT NOT NULL,
    path_pattern TEXT NOT NULL,
    added_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(endpoint_type, path_pattern)
);

INSERT OR IGNORE INTO endpoint_rules (endpoint_type, path_pattern) VALUES
    ('login',        '(?i)/login'),
    ('login',        '(?i)/signin'),
    ('login',        '(?i)/auth'),
    ('login',        '(?i)/oauth'),
    ('login',        '(?i)/sso'),
    ('signup',       '(?i)/signup'),
    ('signup',       '(?i)/register'),
    ('account',      '(?i)/account'),
    ('admin',        '(?i)/admin'),
    ('admin',        '(?i)/wp-admin'),
    ('admin',        '(?i)/dashboard'),
    ('mail',         '(?i)/mail'),
    ('payment',      '(?i)/payment'),
    ('banking',      '(?i)/bank'),
    ('crypto',       '(?i)/wallet'),
    ('api',          '(?i)/api'),
    ('api',          '(?i)/v1'),
    ('api',          '(?i)/graphql'),
    ('password_reset','(?i)/reset'),
    ('cloud',        '(?i)/cloud');

CREATE TABLE IF NOT EXISTS reveal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    user TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    session_id TEXT NOT NULL,
    confirmation_token TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reveal_record ON reveal_events(record_id);
CREATE INDEX IF NOT EXISTS idx_reveal_user ON reveal_events(user);

-- FTS5 virtual table for full-text search on records.
-- We store structured fields as unindexed columns (to retrieve them) and
-- the searchable_text as an indexed column. Exact-match queries on email,
-- username, etc. are handled via the separate `records` table with b-tree indexes.
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
    searchable_text,
    source_id UNINDEXED,
    file_id UNINDEXED,
    file_path UNINDEXED,
    file_name UNINDEXED,
    extension UNINDEXED,
    line_number UNINDEXED,
    byte_offset UNINDEXED,
    byte_length UNINDEXED,
    record_format UNINDEXED,
    service_name,
    root_domain,
    host,
    subdomain,
    normalized_url,
    path,
    endpoint_type,
    email,
    email_domain,
    username,
    ip,
    phone,
    hash,
    detected_secret_type,
    record_hash UNINDEXED,
    account_hash UNINDEXED,
    url_hash UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

-- Structured records table for exact-match and filtered queries.
-- Mirrors the FTS5 rows but with proper b-tree indexes for fast filtering.
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fts_rowid INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    file_id INTEGER,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    byte_offset INTEGER NOT NULL,
    byte_length INTEGER NOT NULL,
    record_format TEXT NOT NULL,
    service_name TEXT,
    root_domain TEXT,
    host TEXT,
    subdomain TEXT,
    normalized_url TEXT,
    path TEXT,
    endpoint_type TEXT,
    email TEXT,
    email_domain TEXT,
    username TEXT,
    ip TEXT,
    phone TEXT,
    hash TEXT,
    detected_secret_type TEXT,
    searchable_text TEXT NOT NULL DEFAULT '',
    record_hash TEXT NOT NULL,
    account_hash TEXT,
    url_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source_id);
CREATE INDEX IF NOT EXISTS idx_records_email ON records(email);
CREATE INDEX IF NOT EXISTS idx_records_username ON records(username);
CREATE INDEX IF NOT EXISTS idx_records_root_domain ON records(root_domain);
CREATE INDEX IF NOT EXISTS idx_records_host ON records(host);
CREATE INDEX IF NOT EXISTS idx_records_service ON records(service_name);
CREATE INDEX IF NOT EXISTS idx_records_hash ON records(hash);
CREATE INDEX IF NOT EXISTS idx_records_ip ON records(ip);
CREATE INDEX IF NOT EXISTS idx_records_endpoint ON records(endpoint_type);
CREATE INDEX IF NOT EXISTS idx_records_record_hash ON records(record_hash);
CREATE INDEX IF NOT EXISTS idx_records_account_hash ON records(account_hash);
CREATE INDEX IF NOT EXISTS idx_records_url_hash ON records(url_hash);
