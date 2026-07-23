"""Tests for URL normalization."""
import breachelens.entities.service_classifier as sc
from breachelens.entities.url_normalizer import normalize, split_domain


def setup_module():
    rules = [(d, s) for s, d in sc.default_service_mappings()]
    sc.populate_cache(rules)


def test_normalizes_google_accounts():
    u = normalize("https://accounts.google.com/signin?continue=https://app.com")
    assert u is not None
    assert u.root_domain == "google.com"
    assert u.subdomain == "accounts"
    assert u.endpoint_type == "login"


def test_handles_uk_suffix():
    u = normalize("https://mail.example.co.uk/inbox")
    assert u is not None
    assert u.root_domain == "example.co.uk"
    assert u.subdomain == "mail"


def test_rejects_localhost():
    assert normalize("http://localhost:8080/admin") is None


def test_rejects_private_ip():
    assert normalize("http://192.168.1.1/admin") is None


def test_split_domain_simple():
    assert split_domain("google.com") == ("google.com", None)


def test_split_domain_with_subdomain():
    assert split_domain("accounts.google.com") == ("google.com", "accounts")
