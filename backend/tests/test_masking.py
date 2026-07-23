"""Tests for masking."""
from breachelens.security.masking import (
    mask_email,
    mask_ip,
    mask_phone,
    mask_preview,
    mask_secret,
    mask_value,
)


def test_masks_email():
    assert mask_email("jsmith@gmail.com") == "js••••@gmail.com"


def test_masks_ipv4():
    assert mask_ip("73.14.224.18") == "73.14.••.••"


def test_masks_value_short():
    assert mask_value("ab", 2) == "••••"


def test_masks_password_in_preview():
    masked = mask_preview("user: jsmith password: Winter2024!", "jsmith")
    assert "jsmith" in masked
    assert "password:•••••••••••" in masked or "password:" in masked
    assert "Winter2024!" not in masked


def test_masks_credit_card_in_preview():
    masked = mask_preview("card: 4111111111111111", "card")
    # Last 4 digits should be visible
    assert "1111" in masked
    assert "4111111111111111" not in masked
