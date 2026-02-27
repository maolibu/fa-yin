"""
字典查询 API
用法: /api/dict/lookup?q=般若

支持:
  - 内置词典 (dicts.db, 6部精选佛学词典 + 通用汉语辞典)
  - 用户词典 (data/dicts/user/ 目录下的 MDX/JSON/CSV 文件)
"""
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from config import DATA_DIR, PROJECT_ROOT
from core.user_dicts import UserDictManager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dict", tags=["dict"])

# 内置词典数据库路径
DICT_DB = DATA_DIR / "dicts.db"

# 用户词典目录
USER_DICT_DIR = PROJECT_ROOT / "data" / "dicts" / "user"

# 用户词典管理器（延迟加载，首次查询时才真正读取词典文件）
_user_mgr: Optional[UserDictManager] = None


def _get_user_mgr() -> UserDictManager:
    """获取用户词典管理器（单例）"""
    global _user_mgr
    if _user_mgr is None:
        _user_mgr = UserDictManager(USER_DICT_DIR)
    return _user_mgr


def _get_conn() -> sqlite3.Connection:
    """获取内置词典只读连接"""
    conn = sqlite3.connect(f"file:{DICT_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/lookup")
async def lookup(q: str = Query(..., min_length=1, max_length=30)):
    """
    查询词条，同时匹配繁体和简体。
    返回内置词典 + 用户词典的合并结果。
    """
    results = []
    seen = set()

    # 1. 查询内置词典 (SQLite)
    if DICT_DB.exists():
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT e.term, e.definition, d.dict_id, d.name as dict_name, d.char_type
                FROM entries e
                JOIN dictionaries d ON e.dict_id = d.dict_id
                WHERE e.term_tc = ? OR e.term_sc = ? OR e.term = ?
                ORDER BY d.entry_count DESC
            """, (q, q, q)).fetchall()

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

    # 2. 查询用户词典 (MDX/JSON/CSV)
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
    }


@router.get("/dicts")
async def list_dicts():
    """列出所有收录的词典（内置 + 用户）"""
    results = []

    # 内置词典
    if DICT_DB.exists():
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT dict_id, name, source, entry_count, char_type
                FROM dictionaries ORDER BY entry_count DESC
            """).fetchall()
            results.extend([dict(r) for r in rows])
        finally:
            conn.close()

    # 用户词典
    mgr = _get_user_mgr()
    results.extend(mgr.list_dicts())

    return results


@router.post("/reload")
async def reload_user_dicts():
    """热重载用户词典（添加/删除词典文件后调用）"""
    global _user_mgr
    _user_mgr = UserDictManager(USER_DICT_DIR)
    dicts = _user_mgr.list_dicts()
    return {
        "message": f"用户词典已重新加载，共 {len(dicts)} 部",
        "dicts": dicts,
    }
