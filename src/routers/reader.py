"""
阅读页路由 — /read/{sutra_id}
单栏阅读 + HTMX 无刷新翻卷 + 侧边栏骨架
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

import logging
import sqlite3
import config

log = logging.getLogger(__name__)

router = APIRouter(tags=["reader"])



@router.get("/read/{sutra_id}", response_class=HTMLResponse)
async def read_sutra(request: Request, sutra_id: str, juan: int = Query(1, ge=1)):
    """阅读页 — 经文单栏阅读 + 侧边栏"""
    nav = request.app.state.nav
    parser = request.app.state.parser
    templates = request.app.state.templates

    if nav is None:
        return HTMLResponse("<h1>CBETA 数据未配置</h1><p>请先配置 CBETA_BASE 路径。</p>", status_code=503)

    total_juan = nav.get_total_juan(sutra_id)
    title = nav.get_sutra_title(sutra_id)
    info = nav.get_sutra_info(sutra_id) or {}

    # 经藏名称（如 "大正新修大藏經"）
    canon_code = info.get("canon", "") or ""
    canon_name = nav.canon_names.get(canon_code, canon_code)

    # 从 XML teiHeader 提取详细元数据
    hm = parser.parse_header(sutra_id)

    # 初始卷号校验
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
    """获取经文 HTML 内容（HTMX 片段）"""
    parser = request.app.state.parser

    if parser is None:
        return HTMLResponse("<div class='error'>解析器未初始化</div>", status_code=503)

    try:
        content = parser.parse_scroll(sutra_id, scroll)
        return HTMLResponse(content)
    except FileNotFoundError as e:
        return HTMLResponse(f"<div class='error'>未找到: {str(e)}</div>")
    except Exception as e:
        return HTMLResponse(f"<div class='error'>解析错误: {str(e)}</div>")


@router.get("/api/search_sutra")
async def search_sutra(request: Request, q: str = Query("", min_length=1)):
    """
    搜索经文（供对照工作台添加经文使用）。
    复用首页搜索逻辑：输入繁简均可，内部转为繁简两种形式匹配。
    """
    nav = request.app.state.nav
    if nav is None:
        return JSONResponse({"results": []})

    # OpenCC 简繁互转（与 search.py 同源）
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
        title = info.get("title", "")  # catalog 中标题为繁体
        # 匹配经号（忽略大小写）或经名（繁简均可）
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
    """获取与经文关联的人物：authority 数据 + 正文扫描"""
    import re, json

    db_path = config.LINEAGE_DB
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except Exception:
        return JSONResponse({"authored": [], "mentioned": [], "text_found": []})

    try:
        # ── 1. 从 person_scriptures 获取权威数据 ──
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

        # ── 2. 正文扫描：从经文 HTML 提取文本，匹配人名 ──
        text_found = []
        parser = request.app.state.parser
        nav = request.app.state.nav
        if parser and nav:
            # 获取前 3 卷文本（性能平衡）
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
                    log.debug(f"人名扫描卷 {j} 出错: {e}")
            full_text = ''.join(all_text)

            if full_text:
                # 误匹配排除列表（佛教常见术语/身份而非具体人名）
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

                # 加载 3 字以上人名
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

                # 按长度降序匹配
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

                # 按出现次数排序
                text_found.sort(key=lambda x: x["count"], reverse=True)

        return JSONResponse({
            "authored": authored,
            "mentioned": mentioned,
            "text_found": text_found,
        })
    finally:
        conn.close()
