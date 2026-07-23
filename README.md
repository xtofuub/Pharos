# Pharos

> Local-first breach intelligence search and entity extraction engine.

Self-hosted, local-only. No cloud. No telemetry. Search huge files for emails,
URLs, usernames, hashes, IPs, and credentials — with automatic entity extraction,
URL normalization, and service classification.

**For authorized security analysis only. All test data is synthetic.**

---

## Download the Windows executable

GitHub Actions builds `BreachLens.exe` automatically on pushes to `main` or
`master`, on pull requests, and when run manually from the **Actions** tab.

To download a normal build:

1. Open the repository's **Actions** tab.
2. Open the latest successful **Build Windows EXE** run.
3. Download the `BreachLens-Windows-...` artifact.

To publish the executable on the repository's **Releases** page, push a version
tag such as `v0.1.0`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The tagged workflow creates a GitHub Release and attaches `BreachLens.exe`.

---

## Quick start (one command)

### Windows

1. Install [Python 3.11+](https://python.org/downloads/) (check "Add to PATH")
2. Double-click `run.bat` — or open Command Prompt and run:
   ```
   cd breachelens\backend
   python run.py
   ```

### macOS / Linux

```bash
cd breachelens/backend
python3 run.py
```

That's it. The script will:
- Install dependencies automatically (first run only)
- Start the server on `http://127.0.0.1:8443`
- Open your browser to the dashboard

**Default login:** `admin` / `breachelens`

---

## What it does

BreachLens processes very large `.txt`, `.csv`, `.tsv`, `.log`, `.jsonl`, and `.sql`
files containing database dumps, combo lists, credentials, stealer logs, URLs,
emails, and hashes.

For every line, it automatically:
- **Extracts entities:** emails, usernames, URLs, IPs (v4/v6), hashes (MD5/SHA1/SHA256),
  phone numbers, credit cards (Luhn-validated), labeled passwords/tokens
- **Normalizes URLs:** splits into host, root domain, subdomain, path, endpoint type
- **Classifies services:** maps `accounts.google.com` → `Google`, `login.microsoftonline.com` → `Microsoft`, etc. (56+ known services)
- **Classifies endpoints:** `/login` → login, `/admin` → admin, `/api/v1` → api, etc.
- **Masks sensitive values** by default — passwords, tokens, credit cards are never shown without explicit reveal
- **Audit-logs everything** with query hashes only (never raw queries or raw record values)

---

## Using the dashboard

### 1. Add a source folder
Go to **Sources** → click **Add source folder** → enter the absolute path to a folder
you're authorized to process. Confirm authorization.

### 2. Start indexing
Click **Reindex** on the source, or go to **Indexing** → the job runs in the background.
Watch live progress: files processed, records indexed, throughput (lines/sec, MB/sec).

### 3. Search
Go to **Search** (or press **Ctrl+K** / **⌘K**). Search by email, domain, username, IP,
hash, URL, or free text. Results are masked by default. Click the 👁 eye icon to reveal
a specific record (confirmation required, audit-logged).

### 4. Audit trail
Go to **Audit** to see every search and reveal event. Only query hashes are stored —
never the raw query text.

---

## API

All endpoints are on `http://127.0.0.1:8443`. Auth via `Authorization: Bearer <token>`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Login (username + password) |
| POST | `/auth/logout` | Revoke session |
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Aggregate stats |
| GET | `/api/sources` | List source folders |
| POST | `/api/sources` | Add a source folder |
| DELETE | `/api/sources/:id` | Remove a source folder |
| POST | `/api/index/start/:source_id` | Start indexing |
| POST | `/api/index/cancel` | Cancel running job |
| GET | `/api/index/status` | Live job snapshot |
| GET | `/api/index/jobs` | Job history |
| POST | `/api/search` | Search the index |
| POST | `/api/results/:id/reveal` | Reveal a record (audit-logged) |
| GET | `/api/aggregations/services` | Group by service |
| GET | `/api/aggregations/domains` | Group by root domain |
| GET | `/api/audit` | Audit log (query hashes only) |
| GET | `/api/settings` | Read config |

### Example: search via curl

```bash
# Login
TOKEN=$(curl -s -X POST http://127.0.0.1:8443/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"breachelens"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Search
curl -s -X POST http://127.0.0.1:8443/api/search \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"fake.user@gmail.com","mode":"smart"}'
```

---

## Configuration

Environment variables (prefix `BREACHLENS__`, nested with `__`):

```bash
BREACHLENS__SERVER__BIND_ADDR=127.0.0.1    # NEVER use 0.0.0.0 unless you understand the risk
BREACHLENS__SERVER__PORT=8443
BREACHLENS__STORAGE__DEFAULT_MODE=offset    # offset | full
BREACHLENS__INDEXING__BATCH_SIZE=4096
BREACHLENS__SEARCH__MAX_RESULTS_PER_QUERY=1000
BREACHLENS__REGEX_SAFETY__MAX_PATTERN_LENGTH=256
BREACHLENS__AUTH__ALLOW_REVEAL=true         # disable to forbid reveals entirely
```

---

## Architecture

- **Backend:** Python 3.11+ / FastAPI / Uvicorn
- **Database:** SQLite (aiosqlite async) — metadata + structured records
- **Search:** SQLite FTS5 (built-in full-text search) + b-tree indexes for exact-match
- **Frontend:** Single-file HTML (vanilla JS, no build step, served by FastAPI)
- **Auth:** Argon2id (passlib) + in-memory sessions
- **Deployment:** Local-only, default bind `127.0.0.1`

### Project structure

```
backend/
├── run.py                  # ← Run this (auto-installs deps, opens browser)
├── run.bat                 # Windows double-click launcher
├── run.sh                  # macOS/Linux launcher
├── pyproject.toml
├── migrations/             # SQLite schema
├── data/test_sources/      # Synthetic test data
├── breachelens/
│   ├── main.py             # FastAPI bootstrap + static file serving
│   ├── config.py
│   ├── state.py
│   ├── static/index.html   # Single-file frontend (all 7 pages)
│   ├── api/                # HTTP endpoints
│   ├── db/                 # SQLite layer
│   ├── index/              # FTS5 query builder
│   ├── ingest/             # Streaming parser + format detection
│   ├── entities/           # Detectors, URL normalizer, classifiers
│   └── security/           # Masking, auth, audit, validation
└── tests/                  # 36 pytest tests
```

---

## Security model

- **Local-only by default.** Server binds to `127.0.0.1`.
- **Argon2id password hashing.** No plaintext passwords stored.
- **Sessions** are 48-char random tokens, in-memory only.
- **Path allowlisting.** Reveal endpoints refuse to read files outside indexed sources.
- **No shell execution.** No subprocess, no eval.
- **No telemetry.** No outbound HTTP.
- **Audit log** records query hashes only, never raw queries or raw record values.

---

## License

MIT
