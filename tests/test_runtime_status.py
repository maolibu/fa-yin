import sqlite3

from core.runtime_status import _validate_sqlite_schema


def test_read_only_health_check_does_not_create_wal_sidecars(tmp_path):
    db_path = tmp_path / "health.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    status = _validate_sqlite_schema(
        db_path,
        label="sample",
        required=False,
        required_tables={"sample": {"id", "name"}},
    )

    assert status["ok"] is True
    assert not db_path.with_name(f"{db_path.name}-shm").exists()
    assert not db_path.with_name(f"{db_path.name}-wal").exists()
