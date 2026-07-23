"""Tests for entity detectors."""
import breachelens.entities.service_classifier as sc
from breachelens.entities.detectors import extract


def setup_module():
    rules = [(d, s) for s, d in sc.default_service_mappings()]
    sc.populate_cache(rules)


def test_extracts_email_and_domain():
    e = extract("contact: fake.user@gmail.com pass: hello123")
    assert "fake.user@gmail.com" in e.emails
    assert "gmail.com" in e.email_domains


def test_extracts_sha256():
    e = extract("hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert len(e.hashes) == 1
    assert e.hashes[0].algorithm == "sha256"


def test_extracts_labeled_username_and_password():
    e = extract("Username: jsmith Password: Winter2024!")
    assert "jsmith" in e.usernames
    assert "Winter2024!" in e.possible_passwords


def test_extracts_url_with_path():
    e = extract("https://accounts.google.com/signin?continue=https://app.com")
    assert len(e.urls) == 1
    u = e.urls[0]
    assert u.host == "accounts.google.com"
    assert u.root_domain == "google.com"
    assert u.endpoint_type == "login"
    assert u.service_name == "Google"


def test_extracts_ipv4():
    e = extract("source: 73.14.224.18 port 443")
    assert "73.14.224.18" in e.ipv4s


def test_extracts_credit_card_luhn_valid():
    e = extract("card: 4111 1111 1111 1111")
    assert any(s.kind == "credit_card" for s in e.secrets)
