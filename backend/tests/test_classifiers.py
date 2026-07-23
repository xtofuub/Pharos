"""Tests for service and endpoint classification."""
import breachelens.entities.service_classifier as sc
from breachelens.entities.endpoint_classifier import classify_endpoint


def setup_module():
    rules = [(d, s) for s, d in sc.default_service_mappings()]
    sc.populate_cache(rules)


def test_classifies_known_services():
    assert sc.classify_service("google.com") == "Google"
    assert sc.classify_service("github.com") == "GitHub"
    assert sc.classify_service("microsoftonline.com") == "Microsoft"


def test_returns_none_for_unknown():
    assert sc.classify_service("example.com") is None


def test_classifies_login_paths():
    assert classify_endpoint("/login") == "login"
    assert classify_endpoint("/signin") == "login"
    assert classify_endpoint("/auth/callback") == "login"
    assert classify_endpoint("/oauth/authorize") == "login"


def test_classifies_admin_paths():
    assert classify_endpoint("/admin/users") == "admin"
    assert classify_endpoint("/wp-admin/") == "admin"


def test_classifies_api_paths():
    assert classify_endpoint("/api/v1/users") == "api"
    assert classify_endpoint("/graphql") == "api"


def test_unknown_for_root():
    assert classify_endpoint("/") == "unknown"
