# Pharos

> Local-first breach intelligence search, entity extraction, and identity correlation.

Pharos indexes authorized local datasets without uploading them anywhere. It can search emails, usernames, URLs, domains, IPs, hashes, phones, and other structured indicators, then bundle repeated email observations into a single identity profile.

## Pharos 0.3

- Native Windows folder picker and scan preview
- Streaming indexing for large files
- Clean re-indexing without duplicate rows
- Automatic removal of stale results for deleted or moved files
- Permission and file-level error reporting
- Exact, contains, FTS5-ranked, and real timeout-protected regex search
- Multi-entity indexing: every email, username, URL, phone, IP, hash, service, and domain on a line is stored
- Identity profiles grouped by normalized email
- Gmail alias correlation (`john.smith+tag@gmail.com` → `johnsmith@gmail.com`)
- Secure reveal: the browser sends only a record ID; trusted file offsets stay server-side
- Mandatory password change after the first login
- Local database backup, reset-index, and open-data-folder controls
- Windows executable builds through GitHub Actions

## Download the Windows build

Open **Actions → Build Windows EXE**, choose the latest successful run, and download the `Pharos-Windows-...` artifact.

Tagged builds are attached to GitHub Releases:

```bash
git tag v0.3.0
git push origin v0.3.0
```

## Run from source

```bash
cd backend
python run.py
```

Then open `http://127.0.0.1:8443`.

First login:

```text
username: admin
password: breachelens
```

Pharos requires a new password before the dashboard can be used.

## Supported files

`.txt`, `.csv`, `.tsv`, `.log`, `.jsonl`, and `.sql` are enabled by default. Extensions can be changed for each source.

## Identity profiles

An identity begins with a canonical email address. Every record containing that email is linked to the profile, along with associated:

- email aliases
- usernames
- services and domains
- URLs and hosts
- phone numbers
- IP addresses
- hashes and detected secret types
- source records and files

Pharos does not automatically merge unrelated non-email identifiers. That avoids aggressive false-positive identity matches.

## Data location

Windows and other platforms currently store local application data under:

```text
~/.local/share/breachelens/
```

The directory name remains `breachelens` for compatibility with earlier builds.

## Security model

- Binds to loopback only by default
- No telemetry or cloud upload
- Argon2 password hashing
- Mandatory first-login password change
- Sensitive values masked by default
- Reveal events are audit logged
- Reveal paths and offsets are loaded from SQLite, not trusted from the browser
- Changed source files must be re-indexed before reveal
- Regex matching has per-row execution timeouts and result caps

## Development

```bash
cd backend
python -m pip install -e ".[dev]"
python -m pytest -q
python -m PyInstaller breachelens.spec --noconfirm --clean
```

The Windows executable is written to `backend/dist/Pharos.exe`.

## Legal

For authorized security analysis only. The operator is responsible for ensuring that all indexed data is handled lawfully and with appropriate permission.

## License

MIT
