"""
CBETA XML → SQLite ETL 转换脚本
将 TEI P5 XML 佛经文件转换为 SQLite 数据库（cbeta.db）

用法：
    python etl_xml_to_db.py T08n0251           # 转换单部经
    python etl_xml_to_db.py --canon T           # 转换整个大正藏
    python etl_xml_to_db.py --all               # 转换全部

注意：使用 stdlib xml.etree.ElementTree（而非 lxml），避免 lxml 在解析
CBETA XML 时因尝试解析远程 RNG schema 而挂起。

标签覆盖：扫描 4990 个 CBETA XML 文件后确认的完整标签处理策略。
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# 添加模块搜索路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaiji_map

# ============================================================
# 配置
# ============================================================
ETL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ETL_DIR.parent
XML_BASE = PROJECT_ROOT / "01_data_raw" / "cbeta_xml_p5"
CANONS_JSON = XML_BASE / "canons.json"
DB_PATH = ETL_DIR / "output" / "cbeta.db"
SCHEMA_PATH = ETL_DIR / "schema" / "schema.sql"
LOG_DIR = ETL_DIR / "logs"

# XML 命名空间
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# 注册命名空间（让 ElementTree 知道前缀）
ET.register_namespace("", TEI_NS)
ET.register_namespace("cb", CB_NS)

# 缓存 bookdata.txt
_canons_cache = None


def _load_canons():
    """从 canons.json 解析藏经代码 → 中文名映射
    
    canons.json 格式（P5 自带）：
        {"T": {"title-zh": "大正新脩大藏經", ...}, ...}
    """
    global _canons_cache
    if _canons_cache is not None:
        return _canons_cache
    _canons_cache = {}
    if not CANONS_JSON.exists():
        return _canons_cache
    try:
        with open(CANONS_JSON, "r", encoding="utf-8") as f:
            _canons_cache = json.load(f)
    except Exception as e:
        print(f"  ⚠️ 读取 canons.json 失败: {e}")
    return _canons_cache


def _local_tag(element):
    """获取元素的本地名（去除命名空间）"""
    tag = element.tag
    if "}" in tag:
        return tag.split("}")[1]
    return tag


# ============================================================
# 数据库初始化
# ============================================================
def init_db(db_path, schema_path):
    """初始化数据库，执行 schema.sql 建表"""
    os.makedirs(db_path.parent, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


# ============================================================
# 跳过类标签集合（不输出任何内容）
# ============================================================
# 这些标签的内容不构成正文，直接跳过
SKIP_TAGS_TEXT = {
    "note", "rdg", "anchor", "back",
    "mulu",            # 目录标记，单独提取到 toc 表
    "charDecl",        # 缺字声明（在 header 中）
    "teiHeader",       # 整个 header 不参与正文提取
}

# HTML 中跳过（但可能收集附带信息）
SKIP_TAGS_HTML = {
    "rdg", "back",
    "charDecl", "teiHeader",
}

# 自关闭/无内容标签
SELF_CLOSING = {
    "lb", "pb", "milestone", "anchor", "space", "caesura",
}


# ============================================================
# 纯文本提取（递归遍历，覆盖全部标签）
# ============================================================
def get_text_recursive(element):
    """
    递归提取元素的纯文本内容。
    覆盖 CBETA XML 全部 114 种标签的处理逻辑：
    - <g ref="#CB..."> 查 gaiji 映射
    - <lem> 取校勘正文
    - <note>, <rdg>, <anchor>, <back>, <mulu> 跳过
    - <space/> 输出空格
    - <caesura/> 输出空格（偈颂停顿）
    - <lb>, <pb>, <milestone> 不含文本，跳过
    - 其余元素（p, lg, l, div, list, item, table, row, cell,
      quote, unclear, foreign, sp, dialog, entry, tt, t, 等等）递归提取文本
    """
    parts = []
    if element.text:
        parts.append(element.text)

    for child in element:
        tag = _local_tag(child)

        if tag == "g":
            # Gaiji 缺字处理
            ref = child.get("ref", "")
            cb_id = ref.lstrip("#")
            resolved = gaiji_map.resolve(cb_id)
            parts.append(resolved)
        elif tag == "lem":
            # 校勘正文：取底本
            parts.append(get_text_recursive(child))
        elif tag == "app":
            # 校勘段：递归进入（会碰到 lem 和 rdg）
            parts.append(get_text_recursive(child))
        elif tag in SKIP_TAGS_TEXT:
            # 跳过不输出
            pass
        elif tag == "space":
            # 原文空格标记
            quantity = child.get("quantity", "1")
            try:
                n = int(quantity)
            except ValueError:
                n = 1
            parts.append("　" * n)  # 全角空格
        elif tag == "caesura":
            # 偈颂停顿
            parts.append("　")  # 一个全角空格
        elif tag == "choice":
            # <choice> 包含 <sic>+<corr> 或 <orig>+<reg>：递归进入
            # （内部会命中 corr/reg 保留、sic/orig 跳过）
            parts.append(get_text_recursive(child))
        elif tag in ("sic", "orig"):
            # 原文错误/原始形式：纯文本中跳过（只保留 corr/reg）
            pass
        elif tag in ("corr", "reg"):
            # 校正/正则化形式：保留
            parts.append(get_text_recursive(child))
        elif tag in SELF_CLOSING:
            # lb, pb, milestone 等自关闭无文本
            pass
        else:
            # 所有其余元素（p, div, lg, l, head, byline, list, item,
            # table, row, cell, quote, unclear, foreign, sp, dialog,
            # entry, form, def, tt, t, hi, seg, term, trailer,
            # figure, figDesc, graphic, juan, jhead, jl_title, etc.）
            # → 递归提取纯文本
            parts.append(get_text_recursive(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


# ============================================================
# HTML 提取（递归遍历，保留语义标记）
# ============================================================
def get_html_recursive(element):
    """
    递归提取元素的 HTML 内容（保留行号、偈颂、表格等标记）。
    覆盖全部标签，确保嵌套结构正确。
    """
    parts = []
    if element.text:
        parts.append(element.text)

    for child in element:
        tag = _local_tag(child)

        # ---- 行号/页号（自关闭标记）----
        if tag == "lb":
            line_id = child.get("n", "")
            if line_id:
                parts.append(
                    f'<br><span class="line-num" id="lb-{line_id}">{line_id}</span>'
                )
            else:
                parts.append("<br>")

        elif tag == "pb":
            page_id = child.get("n", "")
            ed = child.get("ed", "")
            if page_id:
                parts.append(
                    f'<div class="page-break" id="pb-{page_id}" data-ed="{ed}"></div>'
                )

        elif tag == "milestone":
            # 卷切分标记，HTML 中不输出
            pass

        elif tag == "anchor":
            # 注释锚点，HTML 中保留 id 以便关联
            anchor_id = child.get(f"{{{XML_NS}}}id", "") or child.get("id", "")
            if anchor_id:
                parts.append(f'<a id="{anchor_id}" class="anchor"></a>')

        # ---- 空格/停顿 ----
        elif tag == "space":
            quantity = child.get("quantity", "1")
            try:
                n = int(quantity)
            except ValueError:
                n = 1
            parts.append(f'<span class="space">{"　" * n}</span>')

        elif tag == "caesura":
            parts.append('<span class="caesura">　</span>')

        # ---- Gaiji 缺字 ----
        elif tag == "g":
            ref = child.get("ref", "")
            cb_id = ref.lstrip("#")
            resolved = gaiji_map.resolve(cb_id)
            parts.append(
                f'<span class="gaiji" data-cb="{cb_id}">{resolved}</span>'
            )

        # ---- 校勘 ----
        elif tag == "app":
            # 校勘段：递归处理（内含 lem + rdg）
            parts.append(get_html_recursive(child))

        elif tag == "lem":
            # 底本正文：直接取内容
            wit = child.get("wit", "")
            parts.append(
                f'<span class="lem" data-wit="{wit}">{get_html_recursive(child)}</span>'
            )

        elif tag == "rdg":
            # 异读：HTML 中保留但默认隐藏（CSS 可控）
            wit = child.get("wit", "")
            parts.append(
                f'<span class="rdg" data-wit="{wit}" hidden>{get_html_recursive(child)}</span>'
            )

        # ---- 注释 ----
        elif tag == "note":
            note_type = child.get("type", "")
            place = child.get("place", "")
            n = child.get("n", "")
            if place == "inline":
                # 夹注：显示在正文中
                parts.append(
                    f'<span class="note-inline" data-type="{note_type}">'
                    f'({get_html_recursive(child)})</span>'
                )
            else:
                # 脚注或其他注释：显示为上标链接
                if n:
                    parts.append(
                        f'<sup class="note-ref" data-n="{n}">[{n}]</sup>'
                    )

        # ---- 结构性标签 ----
        elif tag == "head":
            level = child.get("type", "")
            parts.append(f'<h3 class="head-{level}">{get_html_recursive(child)}</h3>')

        elif tag == "byline":
            cb_type = child.get(f"{{{CB_NS}}}type", "") or child.get("type", "")
            parts.append(
                f'<p class="byline" data-type="{cb_type}">{get_html_recursive(child)}</p>'
            )

        elif tag == "trailer":
            parts.append(
                f'<p class="trailer">{get_html_recursive(child)}</p>'
            )

        elif tag == "p":
            cb_type = child.get(f"{{{CB_NS}}}type", "")
            p_id = child.get(f"{{{XML_NS}}}id", "") or child.get("id", "")
            css_class = "dharani" if cb_type == "dharani" else ""
            inner = get_html_recursive(child)
            cls_str = f' class="{css_class}"' if css_class else ""
            id_str = f' id="{p_id}"' if p_id else ""
            parts.append(f"<p{cls_str}{id_str}>{inner}</p>")

        # ---- 偈颂 ----
        elif tag == "lg":
            lg_type = child.get("type", "")
            parts.append(
                f'<div class="verse" data-type="{lg_type}">{get_html_recursive(child)}</div>'
            )

        elif tag == "l":
            parts.append(
                f'<span class="verse-line">{get_html_recursive(child)}</span>'
            )

        # ---- 卷标记 ----
        elif tag == "juan":
            fun = child.get("fun", "")
            juan_text = get_text_recursive(child).strip()
            if juan_text:
                parts.append(
                    f'<h2 class="juan-title" data-fun="{fun}">{juan_text}</h2>'
                )

        elif tag == "jhead":
            parts.append(
                f'<span class="jhead">{get_html_recursive(child)}</span>'
            )

        # ---- 目录标记 ----
        elif tag == "mulu":
            # 目录标记在 HTML 中嵌入隐藏标记（供前端目录导航）
            mulu_type = child.get("type", "")
            mulu_n = child.get("n", "")
            title = get_text_recursive(child).strip() or child.get("n", "")
            parts.append(
                f'<span class="mulu" data-type="{mulu_type}" data-n="{mulu_n}" hidden>{title}</span>'
            )

        # ---- 章节 div ----
        elif tag == "div":
            div_type = child.get("type", "") or child.get(f"{{{CB_NS}}}type", "")
            parts.append(
                f'<div class="div-{div_type}" data-type="{div_type}">{get_html_recursive(child)}</div>'
            )

        # ---- 列表 ----
        elif tag == "list":
            rend = child.get("rend", "")
            parts.append(
                f'<ul class="list" data-rend="{rend}">{get_html_recursive(child)}</ul>'
            )

        elif tag == "item":
            n = child.get("n", "")
            n_str = f' data-n="{n}"' if n else ""
            parts.append(
                f'<li{n_str}>{get_html_recursive(child)}</li>'
            )

        # ---- 表格 ----
        elif tag == "table":
            parts.append(
                f'<table class="cbeta-table">{get_html_recursive(child)}</table>'
            )

        elif tag == "row":
            parts.append(f"<tr>{get_html_recursive(child)}</tr>")

        elif tag == "cell":
            cols = child.get("cols", "")
            rows = child.get("rows", "")
            attr_str = ""
            if cols:
                attr_str += f' colspan="{cols}"'
            if rows:
                attr_str += f' rowspan="{rows}"'
            parts.append(
                f"<td{attr_str}>{get_html_recursive(child)}</td>"
            )

        # ---- 引文 ----
        elif tag == "quote":
            q_type = child.get("type", "")
            source = child.get("source", "")
            parts.append(
                f'<blockquote class="quote" data-type="{q_type}" data-source="{source}">'
                f'{get_html_recursive(child)}</blockquote>'
            )

        # ---- 模糊字 ----
        elif tag == "unclear":
            cert = child.get("cert", "")
            reason = child.get("reason", "")
            parts.append(
                f'<span class="unclear" data-cert="{cert}" data-reason="{reason}">'
                f'{get_html_recursive(child)}</span>'
            )

        # ---- 外语 ----
        elif tag == "foreign":
            lang = child.get("lang", "") or child.get(f"{{{XML_NS}}}lang", "")
            parts.append(
                f'<span class="foreign" lang="{lang}">{get_html_recursive(child)}</span>'
            )

        # ---- 对话 ----
        elif tag == "sp":
            sp_type = child.get("type", "")
            parts.append(
                f'<div class="speech" data-type="{sp_type}">{get_html_recursive(child)}</div>'
            )

        elif tag == "dialog":
            d_type = child.get("type", "")
            parts.append(
                f'<div class="dialog" data-type="{d_type}">{get_html_recursive(child)}</div>'
            )

        # ---- 图片 ----
        elif tag == "figure":
            parts.append(
                f'<figure class="cbeta-figure">{get_html_recursive(child)}</figure>'
            )

        elif tag == "graphic":
            url = child.get("url", "")
            parts.append(f'<img src="{url}" class="cbeta-graphic" />')

        elif tag == "figDesc":
            parts.append(
                f'<figcaption>{get_html_recursive(child)}</figcaption>'
            )

        # ---- 字典/翻译（P2 标签）----
        elif tag == "entry":
            style = child.get("style", "")
            parts.append(
                f'<div class="dict-entry" style="{style}">{get_html_recursive(child)}</div>'
            )

        elif tag == "form":
            parts.append(
                f'<span class="dict-form">{get_html_recursive(child)}</span>'
            )

        elif tag == "def":
            parts.append(
                f'<span class="dict-def">{get_html_recursive(child)}</span>'
            )

        elif tag == "tt":
            tt_type = child.get("type", "")
            parts.append(
                f'<div class="translation" data-type="{tt_type}">{get_html_recursive(child)}</div>'
            )

        elif tag == "t":
            lang = child.get("lang", "") or child.get(f"{{{XML_NS}}}lang", "")
            parts.append(
                f'<span class="t-text" lang="{lang}">{get_html_recursive(child)}</span>'
            )

        elif tag == "sg":
            sg_type = child.get("type", "")
            parts.append(
                f'<span class="phonetic" data-type="{sg_type}">{get_html_recursive(child)}</span>'
            )

        # ---- 格式化 ----
        elif tag == "hi":
            rend = child.get("rend", "")
            style = child.get("style", "")
            if "bold" in rend:
                parts.append(f"<b>{get_html_recursive(child)}</b>")
            elif style:
                parts.append(
                    f'<span style="{style}">{get_html_recursive(child)}</span>'
                )
            else:
                parts.append(
                    f'<span class="hi" data-rend="{rend}">{get_html_recursive(child)}</span>'
                )

        elif tag == "seg":
            rend = child.get("rend", "")
            parts.append(
                f'<span class="seg" data-rend="{rend}">{get_html_recursive(child)}</span>'
            )

        # ---- 术语 ----
        elif tag == "term":
            lang = child.get("lang", "") or child.get(f"{{{XML_NS}}}lang", "")
            parts.append(
                f'<span class="term" lang="{lang}">{get_html_recursive(child)}</span>'
            )

        # ---- 引用链接 ----
        elif tag == "ref":
            target = child.get("target", "")
            parts.append(
                f'<a class="ref" href="{target}">{get_html_recursive(child)}</a>'
            )

        # ---- 正则化/校正 ----
        elif tag == "choice":
            # <choice> 包含 <sic>+<corr> 或 <orig>+<reg>：取 corr/reg
            parts.append(get_html_recursive(child))

        elif tag == "corr":
            parts.append(get_html_recursive(child))

        elif tag == "sic":
            # 原文错误，默认隐藏
            parts.append(
                f'<span class="sic" hidden>{get_html_recursive(child)}</span>'
            )

        elif tag == "orig":
            parts.append(
                f'<span class="orig" hidden>{get_html_recursive(child)}</span>'
            )

        elif tag == "reg":
            # 正则化后的形式
            parts.append(get_html_recursive(child))

        # ---- 编号/标签 ----
        elif tag == "num":
            n = child.get("n", "")
            parts.append(
                f'<span class="num" data-n="{n}">{get_html_recursive(child)}</span>'
            )

        elif tag == "label":
            parts.append(
                f'<span class="label">{get_html_recursive(child)}</span>'
            )

        elif tag == "formula":
            parts.append(
                f'<span class="formula">{get_html_recursive(child)}</span>'
            )

        elif tag == "docNumber":
            parts.append(
                f'<span class="doc-number">{get_html_recursive(child)}</span>'
            )

        # ---- 嘉兴藏专用 (jl_*) ----
        elif tag == "jl_title":
            parts.append(
                f'<span class="jl-title">{get_html_recursive(child)}</span>'
            )

        elif tag == "jl_juan":
            parts.append(
                f'<span class="jl-juan">{get_html_recursive(child)}</span>'
            )

        elif tag == "jl_byline":
            jl_type = child.get("type", "")
            parts.append(
                f'<span class="jl-byline" data-type="{jl_type}">{get_html_recursive(child)}</span>'
            )

        # ---- 音义 (yin/zi/fan) ----
        elif tag in ("yin", "zi", "fan"):
            parts.append(
                f'<span class="{tag}">{get_html_recursive(child)}</span>'
            )

        # ---- 指针 ----
        elif tag == "ptr":
            target = child.get("target", "")
            parts.append(f'<a class="ptr" href="{target}">[→]</a>')

        # ---- 引用来源 ----
        elif tag == "cit":
            parts.append(
                f'<span class="citation">{get_html_recursive(child)}</span>'
            )

        elif tag == "bibl":
            parts.append(
                f'<span class="bibl">{get_html_recursive(child)}</span>'
            )

        # ---- header/结构标签（跳过内容）----
        elif tag in SKIP_TAGS_HTML:
            pass

        # ---- 名字（<name> 在正文和 header 都出现）----
        elif tag == "name":
            parts.append(get_html_recursive(child))

        # ---- 默认处理：递归提取 ----
        else:
            # 对未知标签，递归其 children，不增加额外 HTML 包裹
            parts.append(get_html_recursive(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


# ============================================================
# 元数据提取
# ============================================================
def extract_metadata(tree):
    """从 teiHeader 提取经文元数据"""
    root = tree.getroot()

    # 经号：从根元素 xml:id 获取
    xml_id = root.get(f"{{{XML_NS}}}id", "")

    # 解析经号格式：T01n0001 → canon=T, volume=01, no=0001
    # 兼容扩展格式：B00na002（补编，n 后接字母）、GA040n... 等
    match = re.match(r"([A-Z]+)(\d+)n([a-z]*)(\d+[a-z]?)", xml_id)
    if match:
        canon = match.group(1)
        volume = match.group(2)
        sutra_no_prefix = match.group(3)   # 可能为空，如 'a' in B00na002
        sutra_no_digits = match.group(4)
        sutra_no = sutra_no_prefix + sutra_no_digits
        sutra_id = f"{canon}{sutra_no.zfill(4)}"
    else:
        canon = ""
        volume = ""
        sutra_id = xml_id

    # 经名：从 <title level="m" xml:lang="zh-Hant"> 提取
    # 使用 get_text_recursive 以处理包含 <g> 缺字标签的标题
    title = xml_id
    for title_elem in root.iter(f"{{{TEI_NS}}}title"):
        if (
            title_elem.get("level") == "m"
            and title_elem.get(f"{{{XML_NS}}}lang") == "zh-Hant"
        ):
            extracted = get_text_recursive(title_elem).strip()
            if extracted:
                title = extracted
            break

    # 作者/译者
    author = ""
    author_elem = root.find(f".//{{{TEI_NS}}}titleStmt/{{{TEI_NS}}}author")
    if author_elem is not None and author_elem.text:
        author = author_elem.text.strip()

    # 卷数：从 <extent> 提取（如 "22卷"）
    total_juan = 1
    extent_elem = root.find(f".//{{{TEI_NS}}}extent")
    if extent_elem is not None and extent_elem.text:
        juan_match = re.search(r"(\d+)", extent_elem.text)
        if juan_match:
            total_juan = int(juan_match.group(1))

    # 藏经中文名
    canons = _load_canons()
    category = canons.get(canon, {}).get("title-zh", "")

    return {
        "sutra_id": sutra_id,
        "canon": canon,
        "volume": volume,
        "title": title,
        "author": author,
        "total_juan": total_juan,
        "category": category,
        "xml_id": xml_id,
    }


# ============================================================
# 提取校勘记 (apparatus) — 从 <back> 或 <body> 提取
# ============================================================
def extract_apparatus(tree, sutra_id, initial_juan=1):
    """从 <back> 或 <body> 提取 <app>/<lem>/<rdg> 校勘数据
    
    GitHub 版 XML 校勘记在 <back> 中；Bookcase 版（每卷独立文件）
    可能没有 <back>，校勘记内嵌在 <body> 中。
    按 milestone 追踪卷号（与 extract_notes/extract_toc 一致）。
    """
    root = tree.getroot()
    # 优先从 <back> 提取，退而从 <body> 提取
    search_root = root.find(f".//{{{TEI_NS}}}back")
    if search_root is None:
        search_root = root.find(f".//{{{TEI_NS}}}body")
    if search_root is None:
        return []

    records = []
    current_juan = initial_juan
    for elem in search_root.iter():
        tag = _local_tag(elem)
        if tag == "milestone" and elem.get("unit") == "juan":
            n = elem.get("n", "1")
            try:
                current_juan = int(n)
            except ValueError:
                pass
        elif tag == "app":
            lem_text = ""
            readings = []
            for child in elem:
                ct = _local_tag(child)
                if ct == "lem":
                    lem_text = get_text_recursive(child).strip()
                elif ct == "rdg":
                    wit = child.get("wit", "")
                    rdg_text = get_text_recursive(child).strip()
                    readings.append({"wit": wit, "text": rdg_text})
            if lem_text or readings:
                from_ref = elem.get("from", "")
                records.append({
                    "sutra_id": sutra_id,
                    "juan": current_juan,
                    "line_id": from_ref,
                    "lem_text": lem_text,
                    "readings": json.dumps(readings, ensure_ascii=False),
                })
    return records


# ============================================================
# 提取注释 (notes) — 从 <body> 提取，按 milestone 追踪卷号
# ============================================================
def extract_notes(body, sutra_id, initial_juan=1):
    """从正文中提取 <note> 内容，并按 milestone 确定所属卷号"""
    records = []
    current_lb = ""
    current_juan = initial_juan

    for elem in body.iter():
        tag = _local_tag(elem)
        if tag == "milestone" and elem.get("unit") == "juan":
            n = elem.get("n", "1")
            try:
                current_juan = int(n)
            except ValueError:
                pass
        elif tag == "lb":
            current_lb = elem.get("n", "")
        elif tag == "note":
            note_type = elem.get("type", "")
            place = elem.get("place", "")
            content = get_text_recursive(elem).strip()
            if content:
                records.append({
                    "sutra_id": sutra_id,
                    "juan": current_juan,
                    "line_id": current_lb,
                    "note_type": note_type,
                    "place": place,
                    "content": content,
                })
    return records


# ============================================================
# 提取目录 (toc) — 从 <body> 提取，按 milestone 追踪卷号
# ============================================================
def extract_toc(body, sutra_id, initial_juan=1):
    """从正文中提取 <cb:mulu> 目录结构，按 milestone 确定所属卷号"""
    records = []
    current_juan = initial_juan

    for elem in body.iter():
        tag = _local_tag(elem)
        if tag == "milestone" and elem.get("unit") == "juan":
            n = elem.get("n", "1")
            try:
                current_juan = int(n)
            except ValueError:
                pass
        elif tag == "mulu":
            mulu_type = elem.get("type", "")
            mulu_n = elem.get("n", "")
            level = elem.get("level", "0")
            title = get_text_recursive(elem).strip() or mulu_n
            try:
                level_int = int(level)
            except ValueError:
                level_int = 0
            if title or mulu_n:
                records.append({
                    "sutra_id": sutra_id,
                    "juan": current_juan,
                    "level": level_int,
                    "type": mulu_type,
                    "n": mulu_n,
                    "title": title,
                })
    return records


# ============================================================
# 按卷切分正文（纯元素遍历，无序列化）
# ============================================================
def extract_juans(tree, initial_juan=1):
    """
    将正文按 <milestone unit="juan"> 切分为多卷。
    
    策略：遍历 body 的所有后代元素，遇到 milestone 时切换当前卷号，
    将每个顶层子元素分配到对应的卷。
    不使用 tostring（避免 CBETA XML charDecl 导致的挂起问题）。
    
    参数：
        initial_juan: 初始卷号，用于跨册经文（第二个文件可能从卷 N 开始）
    """
    root = tree.getroot()
    body = root.find(f".//{{{TEI_NS}}}body")
    if body is None:
        return []

    # 扫描所有 milestone unit="juan" 标记
    milestones = []
    for elem in body.iter():
        tag = _local_tag(elem)
        if tag == "milestone" and elem.get("unit") == "juan":
            n = elem.get("n", "1")
            try:
                milestones.append((int(n), elem))
            except ValueError:
                pass

    if len(milestones) <= 1:
        # 单卷经：整个 body 作为该 milestone 的卷号（无则用 initial_juan）
        juan_num = milestones[0][0] if milestones else initial_juan
        html = get_html_recursive(body)
        plain = get_text_recursive(body)
        return [(juan_num, html, plain)]

    # 多卷经：按 milestone 在元素树中的出现顺序分段
    milestone_ids = {id(m[1]): m[0] for m in milestones}

    current_juan = initial_juan  # 默认归入 initial_juan（序言属于起始卷）
    juan_html = {}
    juan_text = {}

    def _process_body_for_juans(element, depth=0):
        """深度优先遍历 body，遇到 milestone 切换卷号"""
        nonlocal current_juan

        parts_html = []
        parts_text = []

        if element.text:
            parts_html.append(element.text)
            parts_text.append(element.text)

        for child in element:
            tag = _local_tag(child)

            # 检查是否为 milestone（切换卷号）
            if tag == "milestone" and child.get("unit") == "juan":
                n = child.get("n", "1")
                try:
                    # 保存当前卷的内容
                    if parts_html or parts_text:
                        if current_juan not in juan_html:
                            juan_html[current_juan] = []
                            juan_text[current_juan] = []
                        juan_html[current_juan].extend(parts_html)
                        juan_text[current_juan].extend(parts_text)
                        parts_html = []
                        parts_text = []
                    current_juan = int(n)
                    if current_juan not in juan_html:
                        juan_html[current_juan] = []
                        juan_text[current_juan] = []
                except ValueError:
                    pass
                if child.tail:
                    parts_html.append(child.tail)
                    parts_text.append(child.tail)
                continue

            # 使用统一的 get_html/get_text 函数处理
            # 但需要检查子元素是否包含 milestone（需要递归进入）
            has_milestone = any(
                _local_tag(desc) == "milestone" and desc.get("unit") == "juan"
                for desc in child.iter()
                if desc is not child
            )

            if has_milestone:
                # 子树中有 milestone，递归进入分卷逻辑
                child_html, child_text = _process_body_for_juans(child, depth + 1)
                parts_html.append(child_html)
                parts_text.append(child_text)
            else:
                # 子树中没有 milestone，可以直接用统一函数处理
                parts_html.append(get_html_recursive(child))
                parts_text.append(get_text_recursive(child))

            if child.tail:
                parts_html.append(child.tail)
                parts_text.append(child.tail)

        html_result = "".join(parts_html)
        text_result = "".join(parts_text)

        # 如果在顶层（depth=0），保存最后一段内容
        if depth == 0:
            if current_juan not in juan_html:
                juan_html[current_juan] = []
                juan_text[current_juan] = []
            juan_html[current_juan].append(html_result)
            juan_text[current_juan].append(text_result)

        return html_result, text_result

    _process_body_for_juans(body)

    # 组装结果
    results = []
    for juan_num in sorted(juan_html.keys()):
        html = "".join(juan_html[juan_num])
        plain = "".join(juan_text[juan_num])
        results.append((juan_num, html, plain))

    return results


# ============================================================
# 单文件转换
# ============================================================
# 已处理的 sutra_id 集合（跨册经文需要首次 DELETE + 后续追加）
_processed_sutras = set()


def process_file(xml_path, conn):
    """处理单个 XML 文件，写入数据库
    
    P5 通常每经一个文件，但有 61 部经跨越多个卷册文件夹。
    首次遇到某 sutra_id 时清理旧数据，后续同 sutra_id 追加。
    """
    global _processed_sutras
    try:
        # 使用 fromstring 替代 parse，避免某些环境下 IO 挂起
        with open(str(xml_path), "r", encoding="utf-8") as f:
            content = f.read()
        tree = ET.ElementTree(ET.fromstring(content))

        # 提取元数据
        meta = extract_metadata(tree)
        sutra_id = meta["sutra_id"]

        # 首次遇到此 sutra_id 时，清理旧数据并写入 catalog
        if sutra_id not in _processed_sutras:
            _processed_sutras.add(sutra_id)
            conn.execute(
                """INSERT OR REPLACE INTO catalog 
                   (sutra_id, canon, volume, title, author, total_juan, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    sutra_id,
                    meta["canon"],
                    meta["volume"],
                    meta["title"],
                    meta["author"],
                    meta["total_juan"],
                    meta["category"],
                ),
            )
            # 全量清理该经的旧数据（content 用 INSERT OR REPLACE 覆盖，
            # apparatus/notes/toc 无唯一约束需先删）
            conn.execute("DELETE FROM content WHERE sutra_id = ?", (sutra_id,))
            conn.execute("DELETE FROM apparatus WHERE sutra_id = ?", (sutra_id,))
            conn.execute("DELETE FROM notes WHERE sutra_id = ?", (sutra_id,))
            conn.execute("DELETE FROM toc WHERE sutra_id = ?", (sutra_id,))

        # 按 milestone 切分卷
        juans = extract_juans(tree)

        root = tree.getroot()
        body = root.find(f".//{{{TEI_NS}}}body")

        for juan_num, html, plain_text in juans:
            conn.execute(
                """INSERT OR REPLACE INTO content (sutra_id, juan, html, plain_text)
                   VALUES (?, ?, ?, ?)""",
                (sutra_id, juan_num, html, plain_text),
            )

        # 提取校勘记（P5 在 <back> 中，extract_apparatus 已处理）
        for rec in extract_apparatus(tree, sutra_id):
            conn.execute(
                """INSERT INTO apparatus 
                   (sutra_id, juan, line_id, lem_text, readings)
                   VALUES (?, ?, ?, ?, ?)""",
                (rec["sutra_id"], rec["juan"], rec["line_id"],
                 rec["lem_text"], rec["readings"]),
            )

        # 提取注释和目录
        if body is not None:
            for rec in extract_notes(body, sutra_id):
                conn.execute(
                    """INSERT INTO notes 
                       (sutra_id, juan, line_id, note_type, place, content)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (rec["sutra_id"], rec["juan"], rec["line_id"],
                     rec["note_type"], rec["place"], rec["content"]),
                )

            for rec in extract_toc(body, sutra_id):
                conn.execute(
                    """INSERT INTO toc 
                       (sutra_id, juan, level, type, n, title)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (rec["sutra_id"], rec["juan"], rec["level"],
                     rec["type"], rec["n"], rec["title"]),
                )

        conn.commit()
        return sutra_id, len(juans)

    except Exception as e:
        conn.rollback()  # 显式回滚，防止残留脏数据
        print(f"  ❌ 处理失败 {xml_path}: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# 文件发现
# ============================================================
def find_xml_files(target):
    """
    根据目标参数找到要处理的 XML 文件列表。
    target: 经号（如 T0001）、藏经代码（如 T）、或 --all
    
    P5 文件名格式: {vol}n{sutra_id}.xml（每经一文件）
    例: T01n0001.xml, A120n1561.xml
    """
    if target == "--all":
        return sorted(glob.glob(str(XML_BASE / "*" / "*" / "*.xml")))

    # 藏经代码（如 T, A, X）
    canon_dir = XML_BASE / target
    if canon_dir.is_dir():
        return sorted(glob.glob(str(canon_dir / "*" / "*.xml")))

    # 精确经号匹配（支持 T0001 或 T08n0251 格式）
    # 格式1: 经号简写（如 T0001）→ 搜索所有 T*n0001.xml
    match_short = re.match(r"([A-Z]+)(\d+)$", target)
    if match_short:
        canon = match_short.group(1)
        sutra_no = match_short.group(2)
        pattern = str(XML_BASE / canon / "*" / f"{canon}*n{sutra_no}.xml")
        files = sorted(glob.glob(pattern))
        if files:
            return files
        print(f"❌ 找不到经号 {target} 的文件")
        return []

    # 格式2: 卷级精确（如 T08n0251）→ 搜索 T08/T08n0251.xml
    match_vol = re.match(r"([A-Z]+)(\d+)n(.+)", target)
    if match_vol:
        canon = match_vol.group(1)
        vol = match_vol.group(2)
        sutra_no = match_vol.group(3)
        vol_dir = f"{canon}{vol}"
        single = XML_BASE / canon / vol_dir / f"{target}.xml"
        if single.exists():
            return [str(single)]
        # 回退：尝试通配符匹配
        pattern = str(XML_BASE / canon / vol_dir / f"{vol_dir}n{sutra_no}*.xml")
        files = sorted(glob.glob(pattern))
        if files:
            return files
        print(f"❌ 找不到文件: {single}")
        return []

    print(f"❌ 无法识别目标: {target}")
    print("用法: python etl_xml_to_db.py T0001 | T08n0251 | --canon T | --all")
    return []


# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="CBETA XML → SQLite 转换工具")
    parser.add_argument(
        "target", nargs="?", default=None,
        help="经号（如 T08n0251）或藏经代码（如 T）",
    )
    parser.add_argument("--canon", type=str, help="按藏经代码转换（如 T, X）")
    parser.add_argument("--all", action="store_true", help="转换全部")
    args = parser.parse_args()

    if args.all:
        target = "--all"
    elif args.canon:
        target = args.canon
    elif args.target:
        target = args.target
    else:
        parser.print_help()
        return

    xml_files = find_xml_files(target)
    if not xml_files:
        return

    print(f"📚 找到 {len(xml_files)} 个 XML 文件待转换")
    print(f"📂 数据库: {DB_PATH}")
    print()

    # 重置已处理经典集合（跨册经文去重用）
    global _processed_sutras
    _processed_sutras = set()

    conn = init_db(DB_PATH, SCHEMA_PATH)
    gaiji_map.load_gaiji_map()
    print("✅ Gaiji 映射表已加载")

    success = 0
    errors = []
    start_time = time.time()

    for i, xml_path in enumerate(xml_files, 1):
        filename = os.path.basename(xml_path)
        print(f"  [{i}/{len(xml_files)}] {filename} ...", end=" ", flush=True)

        result = process_file(xml_path, conn)
        if result:
            sutra_id, juan_count = result
            print(f"✅ {sutra_id} ({juan_count} 卷)")
            success += 1
        else:
            errors.append(xml_path)

    elapsed = time.time() - start_time

    print()
    print("=" * 50)
    print(f"✅ 成功: {success}/{len(xml_files)}")
    print(f"❌ 失败: {len(errors)}/{len(xml_files)}")
    print(f"⏱️ 耗时: {elapsed:.1f} 秒")

    # 数据库统计
    for table in ["catalog", "content", "apparatus", "notes", "toc"]:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"📊 {table}: {count} 条")
        except Exception:
            pass

    if errors:
        print()
        print("❌ 失败文件列表:")
        for e in errors:
            print(f"  - {e}")
        os.makedirs(LOG_DIR, exist_ok=True)
        log_path = LOG_DIR / "etl_errors.log"
        with open(log_path, "w", encoding="utf-8") as f:
            for e in errors:
                f.write(f"{e}\n")
        print(f"  日志已保存: {log_path}")

    conn.close()


if __name__ == "__main__":
    main()
