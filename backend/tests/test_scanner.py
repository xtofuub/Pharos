from pathlib import Path

from breachelens.ingest.scanner import normalize_extensions, scan_folder_detailed


def test_scan_folder_reports_files_and_skips_noise(tmp_path: Path):
    (tmp_path / "visible").mkdir()
    (tmp_path / "visible" / "alpha.TXT").write_text("hello\n", encoding="utf-8")
    (tmp_path / "visible" / "combo.lst").write_text("user:pass\n", encoding="utf-8")
    (tmp_path / "visible" / "ignore.exe").write_bytes(b"MZ")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "secret.txt").write_text("hidden", encoding="utf-8")

    result = scan_folder_detailed(tmp_path, [".txt", "LST"])

    assert [item.file_name for item in result.files] == ["alpha.TXT", "combo.lst"]
    assert result.extension_counts == {"lst": 1, "txt": 1}
    assert result.total_bytes > 0
    assert result.skipped_directories >= 1
    assert all(item.mtime > 1_000_000_000_000 for item in result.files)


def test_scan_folder_respects_max_file_size(tmp_path: Path):
    (tmp_path / "small.txt").write_bytes(b"123")
    (tmp_path / "large.txt").write_bytes(b"123456789")

    result = scan_folder_detailed(tmp_path, ["txt"], max_file_size_bytes=4)

    assert [item.file_name for item in result.files] == ["small.txt"]
    assert result.skipped_large_files == 1


def test_normalize_extensions_deduplicates_and_strips_dots():
    assert normalize_extensions([".TXT", "txt", " .Csv ", ""]) == ["csv", "txt"]
