"""
閱讀頁路由 — /read/{sutra_id}
單欄閱讀 + HTMX 無刷新翻卷 + 側邊欄骨架
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

import logging
import sqlite3
import config
from core.runtime_status import check_lineage_db

log = logging.getLogger(__name__)

router = APIRouter(tags=["reader"])



@router.get("/read/{sutra_id}", response_class=HTMLResponse)
async def read_sutra(request: Request, sutra_id: str, juan: int = Query(1, ge=1)):
    """閱讀頁 — 經文單欄閱讀 + 側邊欄"""
    nav = request.app.state.nav
    parser = request.app.state.parser
    templates = request.app.state.templates

    if nav is None:
        return HTMLResponse("<h1>CBETA 數據未配置</h1><p>請先配置 CBETA_BASE 路徑。</p>", status_code=503)

    total_juan = nav.get_total_juan(sutra_id)
    title = nav.get_sutra_title(sutra_id)
    info = nav.get_sutra_info(sutra_id) or {}

    # 經號不在目錄中，返回 404
    if total_juan == 0 and not info:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": f"未找到經文：{sutra_id}",
        }, status_code=404)

    # 經藏名稱（如 "大正新修大藏經"）
    canon_code = info.get("canon", "") or ""
    canon_name = nav.canon_names.get(canon_code, canon_code)

    # 從 XML teiHeader 提取詳細元數據
    hm = {}
    if parser is not None:
        try:
            hm = parser.parse_header(sutra_id) or {}
        except Exception as exc:
            log.warning(f"讀取經文頭信息失敗，已回退到目錄元數據: {sutra_id}: {exc}")

    # 初始卷號校驗
    initial_juan = min(juan, total_juan) if total_juan > 0 else 1

    return templates.TemplateResponse("read.html", {
        "request": request,
        "sutra_id": sutra_id,
        "sutra_title": title or sutra_id,
        "total_juan": total_juan,
        "initial_juan": initial_juan,
        "author": hm.get("author", "") or info.get("author", ""),
        "category": info.get("category", ""),
        "canon_name": canon_name,
        "hm": hm,
    })


@router.get("/api/content/{sutra_id}/{scroll}", response_class=HTMLResponse)
async def get_content(request: Request, sutra_id: str, scroll: int):
    """獲取經文 HTML 內容（HTMX 片段）"""
    parser = request.app.state.parser

    if parser is None:
        return HTMLResponse("<div class='error'>解析器未初始化</div>", status_code=503)

    try:
        content = parser.parse_scroll(sutra_id, scroll)
        return HTMLResponse(content)
    except FileNotFoundError:
        return HTMLResponse(
            f"<div class='error'>未找到經文 {sutra_id} 卷{scroll} 的數據文件</div>",
            status_code=404,
        )
    except Exception as e:
        log.error(f"解析經文失敗 {sutra_id}/{scroll}: {e}")
        return HTMLResponse(
            "<div class='error'>經文解析出錯，請稍後再試</div>",
            status_code=500,
        )


@router.get("/api/search_sutra")
async def search_sutra(request: Request, q: str = Query("", min_length=1)):
    """
    搜索經文（供對照工作臺添加經文使用）。
    複用首頁搜索邏輯：輸入繁簡均可，內部轉為繁簡兩種形式匹配。
    """
    nav = request.app.state.nav
    if nav is None:
        return JSONResponse({"results": []})

    # OpenCC 簡繁互轉（與 search.py 同源）
    try:
        from opencc import OpenCC
        _t2s = OpenCC('t2s')
        _s2t = OpenCC('s2t')
        q_sc = _t2s.convert(q.strip())
        q_tc = _s2t.convert(q.strip())
    except ImportError:
        q_sc = q_tc = q.strip()

    q_upper = q.strip().upper()
    results = []

    for sid, info in nav.catalog.items():
        title = info.get("title", "")  # catalog 中標題為繁體
        # 匹配經號（忽略大小寫）或經名（繁簡均可）
        if (q_upper in sid.upper()
                or q_tc.lower() in title.lower()
                or q_sc.lower() in title.lower()):
            total_juan = nav.get_total_juan(sid)
            results.append({"id": sid, "title": title, "total_juan": total_juan})
            if len(results) >= 20:
                break

    return JSONResponse({"results": results})


@router.get("/api/persons/{sutra_id}")
async def get_sutra_persons(request: Request, sutra_id: str):
    """獲取與經文關聯的人物：authority 數據 + 正文掃描"""
    import re

    lineage_status = check_lineage_db()
    if not lineage_status["ok"]:
        return JSONResponse({
            "available": False,
            "error": lineage_status["message"],
            "authored": [],
            "mentioned": [],
            "text_found": [],
        }, status_code=503)

    db_path = config.LINEAGE_DB
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return JSONResponse({
            "available": False,
            "error": str(exc),
            "authored": [],
            "mentioned": [],
            "text_found": [],
        }, status_code=503)

    try:
        # ── 1. 從 person_scriptures 獲取權威數據 ──
        rows = conn.execute("""
            SELECT ps.person_id, p.name, p.dynasty, p.sect,
                   p.birth_year, p.death_year, ps.relation
            FROM person_scriptures ps
            JOIN persons p ON ps.person_id = p.person_id
            WHERE ps.scripture_id = ?
            ORDER BY ps.relation, p.birth_year
        """, (sutra_id,)).fetchall()

        authored = []
        mentioned = []
        known_pids = set()
        for r in rows:
            person = {
                "person_id": r["person_id"],
                "name": r["name"],
                "dynasty": r["dynasty"] or "",
                "sect": r["sect"] or "",
                "birth_year": r["birth_year"],
                "death_year": r["death_year"],
            }
            known_pids.add(r["person_id"])
            if r["relation"] == "authored":
                authored.append(person)
            else:
                mentioned.append(person)

        # ── 2. 正文掃描：從經文 HTML 提取文本，匹配人名 ──
        text_found = []
        parser = request.app.state.parser
        nav = request.app.state.nav
        if parser and nav:
            # 獲取前 3 卷文本（性能平衡）
            total = nav.get_total_juan(sutra_id)
            scan_juans = min(total, 3)
            all_text = []
            for j in range(1, scan_juans + 1):
                try:
                    html = parser.parse_scroll(sutra_id, j)
                    text = re.sub(r'<[^>]+>', '', html)
                    text = re.sub(r'\s+', '', text)
                    all_text.append(text)
                except Exception as e:
                    log.debug(f"人名掃描卷 {j} 出錯: {e}")
            full_text = ''.join(all_text)

            if full_text:
                # 誤匹配排除列表（佛教常見術語/身份而非具體人名）
                SKIP = {
                    "不可思議", "無為法", "阿那含", "阿羅漢",
                    "優婆塞", "優婆夷", "菩提薩埵", "善男子",
                    "善女人", "善知識", "轉輪聖王", "忍辱仙",
                    "金剛般若", "般若波羅", "波羅蜜多",
                    "大乘正宗", "如法受持", "法會因由",
                    "究竟無我", "離色離相", "一體同觀",
                    "無得無說", "能淨業障", "一相無相",
                    "金剛般若波羅蜜經",
                }

                # 加載 3 字以上人名
                prows = conn.execute("""
                    SELECT person_id, name, dynasty, sect,
                           birth_year, death_year
                    FROM persons
                    WHERE length(name) >= 3
                """).fetchall()

                name_to_persons = {}
                for pr in prows:
                    n = pr["name"]
                    if n in SKIP:
                        continue
                    if pr["person_id"] in known_pids:
                        continue
                    if n not in name_to_persons:
                        name_to_persons[n] = pr

                # 按長度降序匹配
                sorted_names = sorted(
                    name_to_persons.keys(),
                    key=len, reverse=True
                )
                found_pids = set()
                for name in sorted_names:
                    cnt = full_text.count(name)
                    if cnt > 0:
                        pr = name_to_persons[name]
                        pid = pr["person_id"]
                        if pid in found_pids:
                            continue
                        found_pids.add(pid)
                        text_found.append({
                            "person_id": pid,
                            "name": pr["name"],
                            "dynasty": pr["dynasty"] or "",
                            "sect": pr["sect"] or "",
                            "birth_year": pr["birth_year"],
                            "death_year": pr["death_year"],
                            "count": cnt,
                        })

                # 按出現次數排序
                text_found.sort(key=lambda x: x["count"], reverse=True)

        return JSONResponse({
            "authored": authored,
            "mentioned": mentioned,
            "text_found": text_found,
        })
    finally:
        conn.close()
