"""
全局搜索 API
统一搜索：先返回标题匹配，再返回全文匹配（带 snippet），繁简兼容。
连接 cbeta_search.db（ETL 生成），降级到内存字典搜索。
"""

import logging
import sqlite3
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

import config

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])

# OpenCC 繁简互转
try:
    from opencc import OpenCC
    _cc_t2s = OpenCC('t2s')
    _cc_s2t = OpenCC('s2t')
    def to_sc(text):
        return _cc_t2s.convert(text)
    def to_tc(text):
        return _cc_s2t.convert(text)
except ImportError:
    def to_sc(text):
        return text
    def to_tc(text):
        return text


def _get_search_db():
    """获取搜索数据库只读连接"""
    conn = sqlite3.connect(
        f"file:{config.CBETA_SEARCH_DB}?mode=ro", uri=True
    )
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/search", response_class=JSONResponse)
async def search_sutras(
    request: Request,
    q: str = Query(..., min_length=1, description="搜索关键词"),
    lang: str = Query(default="tc", description="显示语言: tc(繁体) | sc(简体)"),
):
    """
    统一搜索：先标题匹配再全文匹配。
    lang 参数控制返回结果的繁简，跟随用户阅读设置。
    """
    if config.cbeta_search_available:
        return _unified_search(q, lang)

    return _memory_search(request, q)


def _unified_search(q: str, lang: str = "tc"):
    """统一搜索：标题匹配在前，全文匹配在后。lang 控制返回繁简。"""
    use_sc = (lang == "sc")
    db = _get_search_db()
    try:
        results = []

        # ── 1. 标题匹配 ──
        q_upper = q.upper()
        q_sc = to_sc(q)

        title_rows = db.execute("""
            SELECT sutra_id, title, title_sc, author, total_juan
            FROM catalog
            WHERE sutra_id LIKE ? || '%'
               OR title_sc LIKE '%' || ? || '%'
               OR title LIKE '%' || ? || '%'
            ORDER BY
                CASE WHEN sutra_id LIKE ? || '%' THEN 0
                     WHEN title_sc LIKE ? || '%' THEN 1
                     ELSE 2 END,
                sutra_id
            LIMIT 20
        """, (q_upper, q_sc, q, q_upper, q_sc)).fetchall()

        for r in title_rows:
            results.append({
                "sutra_id": r["sutra_id"],
                "title": r["title_sc"] if use_sc else r["title"],
                "author": r["author"] or "",
                "section": "title",
            })

        # ── 2. 全文匹配（≥2字才搜） ──
        if len(q.strip()) >= 2:
            fts_query = f'"{q_sc}"'
            try:
                ft_rows = db.execute("""
                    SELECT
                        f.sutra_id,
                        f.juan,
                        c.title,
                        c.title_sc,
                        snippet(content_fts, 2, '<mark>', '</mark>', '…', 30) as snippet
                    FROM content_fts f
                    JOIN catalog c ON f.sutra_id = c.sutra_id
                    WHERE content_fts MATCH ?
                    ORDER BY rank
                    LIMIT 20
                """, (fts_query,)).fetchall()

                for r in ft_rows:
                    # snippet 来自简体列
                    raw_snippet = r["snippet"] or ""
                    display_snippet = raw_snippet if use_sc else to_tc(raw_snippet)
                    results.append({
                        "sutra_id": r["sutra_id"],
                        "title": r["title_sc"] if use_sc else r["title"] or "",
                        "juan": str(r["juan"]),
                        "snippet": display_snippet,
                        "section": "fulltext",
                    })
            except Exception as e:
                log.debug(f"FTS 全文搜索出错（已降级为仅标题）: {e}")

        return results
    finally:
        db.close()


def _memory_search(request: Request, q: str):
    """降级：内存字典搜索（原有逻辑，cbeta_search.db 不可用时）"""
    nav = request.app.state.nav
    if nav is None:
        return []

    q_upper = q.upper()
    q_lower = q.lower()
    q_sc = to_sc(q)
    results = []

    for sutra_id, info in nav.catalog.items():
        title = info.get("title", "")
        title_sc = to_sc(title)
        if (sutra_id.upper().startswith(q_upper)
                or q in title or q_lower in title.lower()
                or q_sc in title_sc):
            results.append({
                "sutra_id": sutra_id,
                "title": title,
                "author": info.get("author", ""),
                "section": "title",
            })
            if len(results) >= 50:
                break

    return results
