"""
運行時組件健康檢查

統一校驗 CBETA 數據目錄與各 SQLite 數據庫的可用性，
供 launcher、自檢接口與路由降級邏輯複用。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import config


def _status(
    name: str,
    *,
    ok: bool,
    required: bool,
    path: str | None = None,
    reason: str = "",
    message: str = "",
    detail: str = "",
) -> dict:
    return {
        "name": name,
        "ok": ok,
        "required": required,
        "path": path,
        "reason": reason,
        "message": message,
        "detail": detail,
    }


def _validate_sqlite_schema(
    db_path: Path,
    *,
    label: str,
    required_tables: dict[str, set[str]],
    required: bool,
) -> dict:
    if not db_path.exists():
        return _status(
            label,
            ok=False,
            required=required,
            path=str(db_path),
            reason="missing",
            message="文件不存在",
        )

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return _status(
            label,
            ok=False,
            required=required,
            path=str(db_path),
            reason="unreadable",
            message="數據庫無法打開",
            detail=str(exc),
        )

    try:
        actual_tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }

        missing_tables = sorted(
            table for table in required_tables if table not in actual_tables
        )
        if missing_tables:
            return _status(
                label,
                ok=False,
                required=required,
                path=str(db_path),
                reason="schema_invalid",
                message=f"缺少數據表: {', '.join(missing_tables)}",
            )

        for table, required_columns in required_tables.items():
            actual_columns = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            missing_columns = sorted(required_columns - actual_columns)
            if missing_columns:
                return _status(
                    label,
                    ok=False,
                    required=required,
                    path=str(db_path),
                    reason="schema_invalid",
                    message=f"{table} 缺少字段: {', '.join(missing_columns)}",
                )

        return _status(
            label,
            ok=True,
            required=required,
            path=str(db_path),
            reason="ok",
            message="可用",
        )
    except sqlite3.Error as exc:
        return _status(
            label,
            ok=False,
            required=required,
            path=str(db_path),
            reason="query_failed",
            message="數據庫查詢失敗",
            detail=str(exc),
        )
    finally:
        conn.close()


def check_cbeta_data() -> dict:
    xml_dir = config.CBETA_BASE / "XML"
    if xml_dir.exists():
        return _status(
            "cbeta_data",
            ok=True,
            required=True,
            path=str(xml_dir),
            reason="ok",
            message="CBETA XML 已就緒",
        )
    return _status(
        "cbeta_data",
        ok=False,
        required=True,
        path=str(xml_dir),
        reason="missing",
        message="缺少 CBETA XML 數據目錄",
    )


def check_search_db(db_path: Path | None = None) -> dict:
    return _validate_sqlite_schema(
        db_path or config.CBETA_SEARCH_DB,
        label="search_db",
        required=False,
        required_tables={
            "catalog": {"sutra_id", "canon", "title", "title_sc", "author", "total_juan"},
            "content": {"sutra_id", "juan", "plain_text", "plain_text_sc"},
            "content_fts": {"sutra_id", "juan", "plain_text_sc"},
        },
    )


def check_dict_db(db_path: Path | None = None) -> dict:
    return _validate_sqlite_schema(
        db_path or config.DICTS_DB,
        label="dict_db",
        required=False,
        required_tables={
            "dictionaries": {"dict_id", "name", "source", "entry_count", "char_type"},
            "entries": {"dict_id", "term", "term_tc", "term_sc", "definition"},
        },
    )


def check_lineage_db(db_path: Path | None = None) -> dict:
    return _validate_sqlite_schema(
        db_path or config.LINEAGE_DB,
        label="lineage_db",
        required=False,
        required_tables={
            "persons": {"person_id", "name", "dynasty", "sect"},
            "edges": {"source_id", "target_id", "edge_type"},
            "places": {"place_id", "name_zh"},
            "dynasties": {"dynasty_id", "name_zh", "type"},
            "eras": {"era_id", "dynasty_id", "name_zh", "start_year", "end_year"},
            "person_scriptures": {"person_id", "scripture_id", "relation"},
        },
    )


def collect_runtime_health(*, nav=None, parser=None) -> dict:
    components = {
        "cbeta_data": check_cbeta_data(),
        "search_db": check_search_db(),
        "dict_db": check_dict_db(),
        "lineage_db": check_lineage_db(),
    }

    parser_ready = nav is not None and parser is not None
    components["reader_core"] = _status(
        "reader_core",
        ok=parser_ready,
        required=components["cbeta_data"]["ok"],
        reason="ok" if parser_ready else "not_initialized",
        message="閱讀核心已初始化" if parser_ready else "閱讀核心未初始化",
    )

    required_failed = any(
        (not item["ok"]) and item["required"]
        for item in components.values()
    )
    optional_failed = any(
        (not item["ok"]) and (not item["required"])
        for item in components.values()
    )

    if required_failed:
        overall = "degraded"
        summary = "關鍵組件未完全就緒"
    elif optional_failed:
        overall = "degraded"
        summary = "服務可啟動，但部分可選能力已降級"
    else:
        overall = "ok"
        summary = "全部組件可用"

    return {
        "app": {
            "name": config.APP_NAME,
            "version": config.APP_VERSION,
            "display_version": config.APP_VERSION_DISPLAY,
        },
        "overall": overall,
        "summary": summary,
        "components": components,
    }
