"""
字典查詢 API
用法: /api/dict/lookup?q=般若

支持:
  - 內置詞典 (dicts.db, 6部精選佛學詞典 + 通用漢語辭典)
  - 用戶詞典 (data/dicts/user/ 目錄下的 MDX/JSON/CSV 文件)
"""
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from config import DATA_DIR, PROJECT_ROOT
from core.runtime_status import check_dict_db
from core.user_dicts import UserDictManager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dict", tags=["dict"])

# 內置詞典數據庫路徑
DICT_DB = DATA_DIR / "dicts.db"

# 啟動時校驗 schema，避免每次請求都嘗試連接損壞的數據庫
_builtin_ok: bool = check_dict_db(DICT_DB)["ok"] if DICT_DB.exists() else False

# 用戶詞典目錄
USER_DICT_DIR = PROJECT_ROOT / "data" / "dicts" / "user"

# 用戶詞典管理器（延遲加載，首次查詢時才真正讀取詞典文件）
_user_mgr: Optional[UserDictManager] = None


def _get_user_mgr() -> UserDictManager:
    """獲取用戶詞典管理器（單例）"""
    global _user_mgr
    if _user_mgr is None:
        _user_mgr = UserDictManager(USER_DICT_DIR)
    return _user_mgr


def _get_conn() -> sqlite3.Connection:
    """獲取內置詞典只讀連接"""
    conn = sqlite3.connect(f"file:{DICT_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/lookup")
async def lookup(q: str = Query(..., min_length=1, max_length=30)):
    """
    查詢詞條，同時匹配繁體和簡體。
    返回內置詞典 + 用戶詞典的合併結果。
    """
    results = []
    seen = set()
    builtin_available = False

    # 1. 查詢內置詞典 (SQLite)
    if _builtin_ok:
        try:
            conn = _get_conn()
            try:
                rows = conn.execute("""
                    SELECT e.term, e.definition, d.dict_id, d.name as dict_name, d.char_type
                    FROM entries e
                    JOIN dictionaries d ON e.dict_id = d.dict_id
                    WHERE e.term_tc = ? OR e.term_sc = ? OR e.term = ?
                    ORDER BY d.entry_count DESC
                """, (q, q, q)).fetchall()
                builtin_available = True

                for r in rows:
                    key = (r["dict_id"], r["term"])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append({
                        "dict_id": r["dict_id"],
                        "dict_name": r["dict_name"],
                        "char_type": r["char_type"],
                        "term": r["term"],
                        "definition": r["definition"],
                    })
            finally:
                conn.close()
        except sqlite3.Error as exc:
            log.warning(f"內置詞典數據庫不可用，已降級到用戶詞典: {exc}")

    # 2. 查詢用戶詞典 (MDX/JSON/CSV)
    mgr = _get_user_mgr()
    user_results = mgr.lookup(q)
    for r in user_results:
        key = (r["dict_id"], r["term"])
        if key not in seen:
            seen.add(key)
            results.append(r)

    return {
        "query": q,
        "count": len(results),
        "results": results,
        "builtin_available": builtin_available,
    }


@router.get("/dicts")
async def list_dicts():
    """列出所有收錄的詞典（內置 + 用戶）"""
    results = []

    # 內置詞典
    if _builtin_ok:
        try:
            conn = _get_conn()
            try:
                rows = conn.execute("""
                    SELECT dict_id, name, source, entry_count, char_type
                    FROM dictionaries ORDER BY entry_count DESC
                """).fetchall()
                results.extend([dict(r) for r in rows])
            finally:
                conn.close()
        except sqlite3.Error as exc:
            log.warning(f"讀取內置詞典列表失敗，已降級到用戶詞典: {exc}")

    # 用戶詞典
    mgr = _get_user_mgr()
    results.extend(mgr.list_dicts())

    return results


@router.post("/reload")
async def reload_user_dicts():
    """熱重載用戶詞典（添加/刪除詞典文件後調用）"""
    global _user_mgr
    _user_mgr = UserDictManager(USER_DICT_DIR)
    dicts = _user_mgr.list_dicts()
    return {
        "message": f"用戶詞典已重新加載，共 {len(dicts)} 部",
        "dicts": dicts,
    }
