"""Tests for format detection."""
from pathlib import Path

from breachelens.ingest.format_detection import RecordFormat, detect_format


def test_detects_csv_by_extension():
    p = Path("/data/leak.csv")
    assert detect_format(p, b"a,b,c\n1,2,3\n") == RecordFormat.CSV


def test_detects_sql_dump():
    p = Path("/data/dump.sql")
    sample = b"INSERT INTO users (id, email) VALUES (1, 'a@b.com');\n"
    assert detect_format(p, sample) == RecordFormat.SQL_DUMP


def test_detects_stealer_log():
    p = Path("/data/stealer.log")
    sample = b"URL: https://accounts.google.com/signin\nUsername: fake.user@gmail.com\nPassword: FAKE_MASK_ME\n"
    assert detect_format(p, sample) == RecordFormat.STEALER_LOG


def test_detects_tsv_by_tab_count():
    p = Path("/data/data.txt")
    sample = b"email\tusername\tpassword\na@b.com\tjoe\txxx\n"
    assert detect_format(p, sample) == RecordFormat.TSV


def test_detects_combo_format():
    p = Path("/data/combo.txt")
    sample = b"user1@gmail.com:pass1\nuser2@yahoo.com:pass2\nuser3@hotmail.com:pass3\n"
    assert detect_format(p, sample) == RecordFormat.COMBO


def test_detects_jsonl():
    p = Path("/data/records.jsonl")
    sample = b'{"email":"a@b.com","user":"joe"}\n{"email":"c@d.com"}\n'
    assert detect_format(p, sample) == RecordFormat.JSONL
