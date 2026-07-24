"""Regression checks for Pharos's password-free local mode."""
from pathlib import Path

import pytest

from breachelens.api.auth import require_session


@pytest.mark.asyncio
async def test_local_request_context_needs_no_credentials() -> None:
    session = await require_session(None)  # request is intentionally unused in local mode
    assert session.username == "local"
    assert session.token == ""


def test_dashboard_has_no_login_form_or_browser_token() -> None:
    static_dir = Path(__file__).resolve().parents[1] / "breachelens" / "static"
    index = (static_dir / "index.html").read_text(encoding="utf-8")
    core = (static_dir / "app-core.js").read_text(encoding="utf-8")
    pages = (static_dir / "app-pages.js").read_text(encoding="utf-8")

    combined = "\n".join((index, core, pages))
    assert 'id="login"' not in combined
    assert "pharos_token" not in combined
    assert "Bearer " not in combined
    assert "/auth/login" not in combined
