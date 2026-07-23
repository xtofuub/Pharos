from pathlib import Path

import pytest

from breachelens.errors import PathNotAllowedError
from breachelens.security.validation import clean_local_path, validate_source_folder


def test_quoted_folder_path_is_accepted(tmp_path: Path):
    assert validate_source_folder(f'"{tmp_path}"') == tmp_path.resolve()


def test_clean_local_path_expands_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert clean_local_path("~/folder") == str(tmp_path / "folder")


def test_relative_folder_is_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathNotAllowedError):
        validate_source_folder("relative")
