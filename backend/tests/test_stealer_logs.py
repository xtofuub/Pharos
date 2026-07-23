"""Tests for stealer-log parser."""
import breachelens.entities.service_classifier as sc
from breachelens.ingest.stealer_logs import extract_entities


def setup_module():
    rules = [(d, s) for s, d in sc.default_service_mappings()]
    sc.populate_cache(rules)


def test_parses_url_line():
    e = extract_entities("URL: https://mail.google.com/mail/u/0/")
    assert len(e.urls) == 1
    assert e.urls[0].host == "mail.google.com"
    assert e.urls[0].service_name == "Google"


def test_parses_username_line():
    e = extract_entities("Username: fake.user@gmail.com")
    assert "fake.user@gmail.com" in e.emails


def test_parses_password_line():
    e = extract_entities("Password: FAKE_MASK_ME")
    assert "FAKE_MASK_ME" in e.possible_passwords
