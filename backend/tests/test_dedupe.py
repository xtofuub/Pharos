"""Tests for dedupe hashing."""
from breachelens.entities.dedupe import compute_hashes, query_hash


def test_same_record_same_hash():
    a = compute_hashes("hello", "Google", "a@b.com", None, None)
    b = compute_hashes("hello", "Google", "a@b.com", None, None)
    assert a.record_hash == b.record_hash
    assert a.account_hash == b.account_hash


def test_different_records_different_hash():
    a = compute_hashes("hello", None, None, None, None)
    b = compute_hashes("world", None, None, None, None)
    assert a.record_hash != b.record_hash


def test_case_insensitive_account_dedupe():
    a = compute_hashes("x", "Google", "USER@GMAIL.COM", None, None)
    b = compute_hashes("y", "Google", "user@gmail.com", None, None)
    assert a.service_account_hash == b.service_account_hash


def test_query_hash_stable():
    h1 = query_hash("  Jsmith@Gmail.com  ")
    h2 = query_hash("jsmith@gmail.com")
    assert h1 == h2
    assert h1.startswith("q_")
