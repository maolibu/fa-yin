import sqlite3

import pytest

from scripts.capture_reader_screenshots import (
    BLOCK_WRITE_REQUESTS_JS,
    choose_sutra,
    create_output_dir,
)


def test_choose_sutra_reads_configured_database_read_only(tmp_path):
    db_path = tmp_path / "搜索库.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE catalog (sutra_id TEXT, title TEXT, total_juan INTEGER)"
    )
    conn.execute(
        "INSERT INTO catalog VALUES (?, ?, ?)", ("T0001", "長阿含經", 22)
    )
    conn.commit()
    conn.close()

    assert choose_sutra(db_path) == ("T0001", "長阿含經", 22)


def test_choose_sutra_missing_database_uses_documented_fallback(tmp_path):
    assert choose_sutra(tmp_path / "missing.db") == ("T0001", "T0001", 1)


def test_screenshot_output_path_is_required_and_repo_relative(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="--output-dir is required"):
        create_output_dir("")

    monkeypatch.setattr(
        "scripts.capture_reader_screenshots.PROJECT_ROOT", tmp_path
    )
    assert create_output_dir("测试截图").is_relative_to(tmp_path)


def test_screenshot_preload_blocks_browser_write_transports():
    assert "Page.addScriptToEvaluateOnNewDocument" not in BLOCK_WRITE_REQUESTS_JS
    for method in ("fetch", "XMLHttpRequest", "sendBeacon"):
        assert method in BLOCK_WRITE_REQUESTS_JS
    assert "blocked_by_screenshot" in BLOCK_WRITE_REQUESTS_JS
