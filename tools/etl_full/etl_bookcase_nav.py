#!/usr/bin/env python3
"""
Bookcase 导航数据 ETL — 重写版

将 CBETA Bookcase 中的导航数据解析并写入独立的 SQLite 数据库 (cbeta_nav.db)。
将来可合并到主库 cbeta.db，sutra_id 格式与 etl_xml_to_db.py 保持一致。

数据来源：
  ┌─────────────────────────┬────────────────────┬─────────────┐
  │ 数据源                  │ 目标表             │ 用途        │
  ├─────────────────────────┼────────────────────┼─────────────┤
  │ advance_nav.xhtml       │ nav_node (canon)   │ 经藏目录    │
  │ bulei_nav.xhtml         │ nav_node (category)│ 部类目录    │
  │ (从 nav_node 派生)      │ nav_bulei          │ 部类映射    │
  │ toc/*.xml               │ nav_toc + nav_juan │ 经文内部目录│
  │ mulu/*.js               │ nav_mulu           │ 品目索引    │
  └─────────────────────────┴────────────────────┴─────────────┘

用法：
  ~/miniforge3/envs/fjlsc/bin/python 10_etl/etl_bookcase_nav.py
"""

import json
import logging
import re
import sqlite3
import time
from pathlib import Path

import lxml.etree as ET

# ============================================================
# 路径配置
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOOKCASE_DIR = PROJECT_ROOT / "01_data_raw" / "cbeta"
TOC_DIR = BOOKCASE_DIR / "toc"
MULU_DIR = BOOKCASE_DIR / "mulu"
OUTPUT_DIR = PROJECT_ROOT / "10_etl" / "output"
NAV_DB = OUTPUT_DIR / "cbeta_nav.db"

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Schema
# ============================================================
SCHEMA_SQL = """
-- 通用导航树节点（支持经藏目录和部类目录两棵树）
-- tree_type='canon'    → 来自 advance_nav.xhtml（按大正藏/卍续藏等经藏分类）
-- tree_type='category' → 来自 bulei_nav.xhtml（按阿含部類等学术分类）
CREATE TABLE IF NOT EXISTS nav_node (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tree_type  TEXT NOT NULL,       -- 'canon' 或 'category'
    parent_id  INTEGER,             -- 父节点 ID（NULL=根下第一级）
    title      TEXT NOT NULL,       -- 显示标题
    sutra_id   TEXT,                -- 叶子节点的经号（如 'T0001'），分类节点为 NULL
    sort_order INTEGER DEFAULT 0,   -- 按此字段排序，保证显示顺序与原文件一致
    FOREIGN KEY (parent_id) REFERENCES nav_node(id)
);

CREATE INDEX IF NOT EXISTS idx_nav_node_parent ON nav_node(parent_id);
CREATE INDEX IF NOT EXISTS idx_nav_node_tree ON nav_node(tree_type);
CREATE INDEX IF NOT EXISTS idx_nav_node_sutra ON nav_node(sutra_id);

-- 部类映射（从 nav_node category 树派生的扁平缓存）
-- 方便前端快速查询某经属于哪个部类
CREATE TABLE IF NOT EXISTS nav_bulei (
    sutra_id   TEXT PRIMARY KEY,    -- 如 'T0001'
    bu_lei     TEXT NOT NULL        -- 部类名称（如 '01 阿含部類'）
);

-- 经文内部目录（来自 toc/ 中每经的 XML 文件，catalog 部分）
-- 支持层级化的品/分/章目录，含页码锚点
CREATE TABLE IF NOT EXISTS nav_toc (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sutra_id   TEXT NOT NULL,       -- 如 'T0001'
    canon      TEXT NOT NULL,       -- 如 'T'
    level      INTEGER DEFAULT 0,   -- 嵌套层级（0=顶层）
    parent_idx INTEGER,             -- 父节点在同经中的序号（NULL=顶层）
    seq        INTEGER NOT NULL,    -- 在同经中的顺序号
    title      TEXT,                -- 目录条目标题
    file_ref   TEXT,                -- 原始文件引用（如 XML/T/T01/T01n0001_001.xml）
    page_id    TEXT                 -- 页码锚点（如 p0001b11）
);

CREATE INDEX IF NOT EXISTS idx_nav_toc_sutra ON nav_toc(sutra_id);

-- 卷索引（来自 toc/ 文件的 <nav type="juan"> 部分）
CREATE TABLE IF NOT EXISTS nav_juan (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sutra_id   TEXT NOT NULL,       -- 如 'T0001'
    canon      TEXT NOT NULL,       -- 如 'T'
    juan       INTEGER NOT NULL,    -- 卷号
    title      TEXT,                -- 卷标题（如 '第一'）
    file_ref   TEXT,                -- 文件引用
    page_id    TEXT                 -- 页码锚点
);

CREATE INDEX IF NOT EXISTS idx_nav_juan_sutra ON nav_juan(sutra_id);

-- 品目索引（来自 mulu/ 下的 JS 文件，JSON 格式）
-- 每册每经每品一条记录，含行号定位
CREATE TABLE IF NOT EXISTS nav_mulu (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    canon      TEXT NOT NULL,       -- 如 'T'
    volume     TEXT NOT NULL,       -- 如 '01'
    sutra_id   TEXT NOT NULL,       -- 如 'T0001'
    juan       INTEGER,            -- 卷号（从文件名推断，可能为 NULL）
    seq        INTEGER NOT NULL,    -- 品目顺序
    line_id    TEXT,                -- 行号定位（如 0001a01）
    title      TEXT                 -- 品目标题
);

CREATE INDEX IF NOT EXISTS idx_nav_mulu_sutra ON nav_mulu(sutra_id);
"""


# ============================================================
# 工具函数
# ============================================================
def extract_sutra_id_from_cblink(text: str) -> str | None:
    """
    从 cblink 显示文本中提取 sutra_id。
    例: 'T0001 長阿含經' → 'T0001'
         'X0001 ...'     → 'X0001'
    返回 None 表示不是叶子节点。
    """
    m = re.match(r"^([A-Z]+\d+[a-zA-Z]*)\b", text.strip())
    return m.group(1) if m else None


def extract_sutra_id_from_filename(filename: str) -> tuple[str | None, str | None, int | None]:
    """
    从 Bookcase toc/mulu 文件名提取 sutra_id、volume 和 juan。
    例: T01n0001_001.xml → ('T0001', '01', 1)
         T08n0251.xml     → ('T0251', '08', None)  (toc 文件无 _juan 后缀)
         T01_mulu.js      → (None, '01', None)     (mulu 文件只有 volume)
    """
    # toc 文件名格式: {canon}{vol}_mulu.js 或 {sutra_id}.xml
    # 标准 toc: T0001.xml
    m = re.match(r"^([A-Z]+)(\d+[a-zA-Z]*)\.xml$", filename)
    if m:
        sutra_id = m.group(1) + m.group(2)
        return sutra_id, None, None

    # Bookcase XML 格式: {canon}{vol}n{no}_{juan}.xml
    m = re.match(r"([A-Z]+)(\d+)n(\d+[a-zA-Z]*)(?:_(\d+))?\.xml$", filename)
    if m:
        canon = m.group(1)
        vol = m.group(2)
        sutra_no = m.group(3)
        juan_str = m.group(4)
        sutra_id = f"{canon}{sutra_no}"
        juan = int(juan_str) if juan_str else None
        return sutra_id, vol, juan

    return None, None, None


# ============================================================
# 数据库初始化
# ============================================================
def init_db(db_path: Path) -> sqlite3.Connection:
    """创建数据库并初始化表结构"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    log.info(f"数据库已初始化: {db_path}")
    return conn


# ============================================================
# 解析 XHTML 导航文件 → nav_node
# ============================================================
def parse_xhtml_nav(file_path: Path, tree_type: str, conn: sqlite3.Connection):
    """
    解析 advance_nav.xhtml 或 bulei_nav.xhtml，写入 nav_node 表。

    XHTML 结构：
    <nav type="catalog">
      <span>T 大正新脩大藏經</span>      ← 根下第一级（分类节点）
      <ol>
        <li><span>T01 阿含部上</span>    ← 第二级（分类节点）
        <ol>
          <li><cblink>T0001 長阿含經</cblink></li>  ← 叶子节点
        </ol></li>
      </ol>
    </nav>
    """
    log.info(f"解析 {file_path.name} → nav_node (tree_type='{tree_type}')")

    # 使用 fromstring 避免 ET.parse 在某些环境下挂起
    # （与 etl_xml_to_db.py 中处理方式一致）
    content = file_path.read_text(encoding="utf-8")
    parser = ET.XMLParser(recover=True)
    root = ET.fromstring(content.encode("utf-8"), parser=parser)

    # 找到 <nav type="catalog">
    navs = root.xpath("//*[local-name()='nav']")
    if not navs:
        log.error(f"未找到 <nav> 元素: {file_path}")
        return 0

    nav = navs[0]
    count = 0
    global_order = 0  # 全局排序计数器

    def get_direct_text(elem) -> str:
        """获取元素的直接文本（不含子元素文本）"""
        parts = []
        if elem.text:
            parts.append(elem.text.strip())
        return "".join(parts)

    def get_all_text(elem) -> str:
        """获取元素及所有子元素的文本"""
        return "".join(elem.itertext()).strip()

    def process_li(li_elem, parent_db_id: int | None):
        """递归处理 <li> 元素"""
        nonlocal count, global_order

        # <li> 可能包含：
        #   1. <cblink>T0001 長阿含經</cblink>  → 叶子节点
        #   2. <span>T01 阿含部上</span> + <ol>...</ol>  → 分类节点 + 子节点
        cblink = li_elem.find("cblink")
        span = li_elem.find("span")

        if cblink is not None:
            # 叶子节点
            text = get_all_text(cblink)
            sutra_id = extract_sutra_id_from_cblink(text)
            global_order += 1
            cursor = conn.execute(
                "INSERT INTO nav_node (tree_type, parent_id, title, sutra_id, sort_order) VALUES (?, ?, ?, ?, ?)",
                (tree_type, parent_db_id, text, sutra_id, global_order),
            )
            count += 1
            node_id = cursor.lastrowid

            # cblink 下面可能还有 <ol>（罕见但可能）
            for ol in li_elem.findall("ol"):
                process_ol(ol, node_id)

        elif span is not None:
            # 分类节点
            title = get_all_text(span)
            global_order += 1
            cursor = conn.execute(
                "INSERT INTO nav_node (tree_type, parent_id, title, sutra_id, sort_order) VALUES (?, ?, ?, ?, ?)",
                (tree_type, parent_db_id, title, None, global_order),
            )
            count += 1
            node_id = cursor.lastrowid

            # 处理子 <ol>
            for ol in li_elem.findall("ol"):
                process_ol(ol, node_id)

        else:
            # 未知格式的 <li>，尝试提取文本
            text = get_all_text(li_elem)
            if text:
                global_order += 1
                cursor = conn.execute(
                    "INSERT INTO nav_node (tree_type, parent_id, title, sutra_id, sort_order) VALUES (?, ?, ?, ?, ?)",
                    (tree_type, parent_db_id, text, extract_sutra_id_from_cblink(text), global_order),
                )
                count += 1
                node_id = cursor.lastrowid
                for ol in li_elem.findall("ol"):
                    process_ol(ol, node_id)

    def process_ol(ol_elem, parent_db_id: int | None):
        """处理 <ol> 中的所有 <li>"""
        for li in ol_elem.findall("li"):
            process_li(li, parent_db_id)

    # 处理 <nav> 的直接子元素
    # 结构：<span>标题</span> + <ol>子节点列表</ol>，可能重复多次
    current_section_id = None

    children = list(nav)
    i = 0
    while i < len(children):
        child = children[i]
        tag = child.tag if isinstance(child.tag, str) else ""
        local_tag = tag.split("}")[-1] if "}" in tag else tag

        if local_tag == "span":
            # 根下第一级分类节点
            title = get_all_text(child)
            global_order += 1
            cursor = conn.execute(
                "INSERT INTO nav_node (tree_type, parent_id, title, sutra_id, sort_order) VALUES (?, ?, ?, ?, ?)",
                (tree_type, None, title, None, global_order),
            )
            count += 1
            current_section_id = cursor.lastrowid

        elif local_tag == "ol":
            # <ol> 紧跟 <span>，属于当前分类
            process_ol(child, current_section_id)

        elif local_tag == "li":
            # <li> 直接在 <nav> 下 = 根级节点（如 X、A、B 等经藏）
            # 注意：不能用 current_section_id 做父节点，否则会变成 T 的子节点
            process_li(child, None)

        i += 1

    conn.commit()
    log.info(f"  → 写入 {count} 条 nav_node 记录 (tree_type='{tree_type}')")
    return count


# ============================================================
# 从 nav_node 派生 nav_bulei 映射
# ============================================================
def derive_bulei(conn: sqlite3.Connection):
    """
    从 nav_node (tree_type='category') 生成 nav_bulei 扁平映射。
    逻辑：depth=0 的节点是部类名，其下所有叶子节点的 sutra_id 都属于该部类。
    """
    log.info("派生 nav_bulei 映射...")

    # 清空旧数据
    conn.execute("DELETE FROM nav_bulei")

    # 找所有根节点（部类名称）
    roots = conn.execute(
        "SELECT id, title FROM nav_node WHERE tree_type='category' AND parent_id IS NULL ORDER BY sort_order"
    ).fetchall()

    count = 0
    for root_id, bu_lei_name in roots:
        # 递归找此根下所有叶子节点
        # 使用 BFS 遍历
        queue = [root_id]
        while queue:
            node_id = queue.pop(0)
            children = conn.execute(
                "SELECT id, sutra_id FROM nav_node WHERE parent_id = ?", (node_id,)
            ).fetchall()
            for child_id, sutra_id in children:
                if sutra_id:
                    # 叶子节点，插入映射
                    conn.execute(
                        "INSERT OR IGNORE INTO nav_bulei (sutra_id, bu_lei) VALUES (?, ?)",
                        (sutra_id, bu_lei_name),
                    )
                    count += 1
                else:
                    # 非叶子，继续遍历
                    queue.append(child_id)

    conn.commit()
    log.info(f"  → 写入 {count} 条 nav_bulei 记录")
    return count


# ============================================================
# 解析 toc/ 文件 → nav_toc + nav_juan
# ============================================================
def parse_toc_file(toc_path: Path, sutra_id: str, canon: str, conn: sqlite3.Connection):
    """
    解析单个 toc XML 文件，写入 nav_toc 和 nav_juan。

    toc XML 结构包含两个 <nav>：
      <nav type="catalog"> → 品章层级目录 → nav_toc
      <nav type="juan">    → 卷索引      → nav_juan
    """
    parser = ET.XMLParser(recover=True)
    try:
        content = toc_path.read_text(encoding="utf-8")
        root = ET.fromstring(content.encode("utf-8"), parser=parser)
    except Exception as e:
        log.warning(f"解析失败 {toc_path.name}: {e}")
        return 0, 0

    navs = root.xpath("//*[local-name()='nav']")

    toc_count = 0
    juan_count = 0

    for nav in navs:
        nav_type = nav.get("type", "")

        if nav_type == "catalog":
            # 解析品章目录
            seq = [0]  # 用列表包装以便在嵌套函数中修改

            def parse_catalog_ol(ol_elem, level: int, parent_idx: int | None):
                nonlocal toc_count
                for li in ol_elem.findall("li"):
                    cblink = li.find("cblink")
                    span = li.find("span")

                    title = ""
                    file_ref = ""
                    page_id = ""

                    if cblink is not None:
                        title = "".join(cblink.itertext()).strip()
                        href = cblink.get("href", "")
                        if "#" in href:
                            file_ref, page_id = href.rsplit("#", 1)
                        else:
                            file_ref = href
                    elif span is not None:
                        title = "".join(span.itertext()).strip()

                    if not title:
                        continue

                    seq[0] += 1
                    current_seq = seq[0]
                    conn.execute(
                        """INSERT INTO nav_toc
                           (sutra_id, canon, level, parent_idx, seq, title, file_ref, page_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (sutra_id, canon, level, parent_idx, current_seq, title, file_ref, page_id),
                    )
                    toc_count += 1

                    # 递归处理子 <ol>
                    for sub_ol in li.findall("ol"):
                        parse_catalog_ol(sub_ol, level + 1, current_seq)

            for ol in nav.findall("ol"):
                parse_catalog_ol(ol, 0, None)

        elif nav_type == "juan":
            # 解析卷索引
            juan_num = 0
            for ol in nav.findall("ol"):
                for li in ol.findall("li"):
                    cblink = li.find("cblink")
                    if cblink is None:
                        continue
                    title = "".join(cblink.itertext()).strip()
                    href = cblink.get("href", "")
                    file_ref = ""
                    page_id = ""
                    if "#" in href:
                        file_ref, page_id = href.rsplit("#", 1)
                    else:
                        file_ref = href

                    juan_num += 1
                    conn.execute(
                        """INSERT INTO nav_juan
                           (sutra_id, canon, juan, title, file_ref, page_id)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (sutra_id, canon, juan_num, title, file_ref, page_id),
                    )
                    juan_count += 1

    return toc_count, juan_count


def process_all_toc(conn: sqlite3.Connection):
    """遍历 toc/ 目录，解析所有经文的内部目录"""
    log.info("处理 toc/ 目录...")

    if not TOC_DIR.exists():
        log.error(f"toc 目录不存在: {TOC_DIR}")
        return

    # 清空旧数据
    conn.execute("DELETE FROM nav_toc")
    conn.execute("DELETE FROM nav_juan")

    total_toc = 0
    total_juan = 0
    file_count = 0

    # 遍历 toc/ 下的藏经子目录（T/, X/, B/, ...）
    for canon_dir in sorted(TOC_DIR.iterdir()):
        if not canon_dir.is_dir():
            continue
        canon = canon_dir.name  # 如 'T', 'X'

        for xml_file in sorted(canon_dir.iterdir()):
            if not xml_file.name.endswith(".xml"):
                continue

            # 从文件名提取 sutra_id
            # toc 文件名格式: T0001.xml, ZWa037.xml — stem 就是完整的 sutra_id
            sutra_id = xml_file.stem
            # 验证 sutra_id 格式：藏经代号(大写) + 编号(可含小写字母前缀+数字)
            if not re.match(r"^[A-Z]+[a-z]*\d+", sutra_id):
                log.warning(f"跳过无法解析的文件: {xml_file.name}")
                continue

            t_count, j_count = parse_toc_file(xml_file, sutra_id, canon, conn)
            total_toc += t_count
            total_juan += j_count
            file_count += 1

        # 每个藏经处理完提交一次
        conn.commit()

    log.info(f"  → 处理 {file_count} 个 toc 文件")
    log.info(f"  → 写入 {total_toc} 条 nav_toc 记录")
    log.info(f"  → 写入 {total_juan} 条 nav_juan 记录")


# ============================================================
# 解析 mulu/ 文件 → nav_mulu
# ============================================================
def parse_mulu_file(mulu_path: Path, conn: sqlite3.Connection):
    """
    解析单个 mulu JS 文件，写入 nav_mulu。

    JS 格式：
      var mulu_txt = `{"T01n0001.xml":[
        ["0001a01","序"],
        ["0001b11","1 大本經"],
        ...
      ]}`;
      var mulu_json = JSON.parse(mulu_txt);
    """
    # 从文件名提取 canon 和 volume（格式: T01_mulu.js）
    m = re.match(r"([A-Z]+)(\d+)_mulu\.js$", mulu_path.name)
    if not m:
        log.warning(f"跳过无法解析的 mulu 文件: {mulu_path.name}")
        return 0

    canon = m.group(1)
    volume = m.group(2)

    # 读取文件，提取 JSON 部分
    try:
        text = mulu_path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning(f"读取失败 {mulu_path.name}: {e}")
        return 0

    # 提取反引号之间的 JSON
    json_match = re.search(r"`\s*(\{.*?\})\s*`", text, re.DOTALL)
    if not json_match:
        log.warning(f"未找到 JSON 数据: {mulu_path.name}")
        return 0

    try:
        mulu_data = json.loads(json_match.group(1))
    except json.JSONDecodeError as e:
        log.warning(f"JSON 解析失败 {mulu_path.name}: {e}")
        return 0

    count = 0
    for xml_filename, entries in mulu_data.items():
        # 从 xml_filename 提取 sutra_id
        # 格式: T01n0001.xml → T0001
        fm = re.match(r"([A-Z]+)\d+n(\d+[a-zA-Z]*)\.xml", xml_filename)
        if not fm:
            continue
        sutra_id = fm.group(1) + fm.group(2)

        # 尝试从文件名获取 juan（如有 _001 后缀）
        juan_match = re.search(r"_(\d+)\.xml", xml_filename)
        juan = int(juan_match.group(1)) if juan_match else None

        for seq, entry in enumerate(entries, start=1):
            if len(entry) >= 2:
                line_id = entry[0]
                title = entry[1]
                conn.execute(
                    """INSERT INTO nav_mulu
                       (canon, volume, sutra_id, juan, seq, line_id, title)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (canon, volume, sutra_id, juan, seq, line_id, title),
                )
                count += 1

    return count


def process_all_mulu(conn: sqlite3.Connection):
    """遍历 mulu/ 目录，解析所有品目索引"""
    log.info("处理 mulu/ 目录...")

    if not MULU_DIR.exists():
        log.error(f"mulu 目录不存在: {MULU_DIR}")
        return

    # 清空旧数据
    conn.execute("DELETE FROM nav_mulu")

    total = 0
    file_count = 0

    for js_file in sorted(MULU_DIR.iterdir()):
        if not js_file.name.endswith("_mulu.js"):
            continue

        count = parse_mulu_file(js_file, conn)
        total += count
        file_count += 1

    conn.commit()
    log.info(f"  → 处理 {file_count} 个 mulu 文件")
    log.info(f"  → 写入 {total} 条 nav_mulu 记录")


# ============================================================
# 主入口
# ============================================================
def main():
    """ETL 主流程"""
    log.info("=" * 60)
    log.info("开始导航数据 ETL")
    log.info("=" * 60)
    start_time = time.time()

    # 检查数据源目录
    if not BOOKCASE_DIR.exists():
        log.error(f"Bookcase 目录不存在: {BOOKCASE_DIR}")
        log.error("请确认 01_data_raw/cbeta/ 目录存在")
        return

    # 初始化数据库
    conn = init_db(NAV_DB)

    try:
        # ---- 步骤 1: 经藏目录（advance_nav.xhtml）----
        advance_nav = BOOKCASE_DIR / "advance_nav.xhtml"
        if advance_nav.exists():
            # 清空 canon 树的旧数据
            conn.execute("DELETE FROM nav_node WHERE tree_type='canon'")
            parse_xhtml_nav(advance_nav, "canon", conn)
        else:
            log.warning(f"未找到 advance_nav.xhtml: {advance_nav}")

        # ---- 步骤 2: 部类目录（bulei_nav.xhtml）----
        bulei_nav = BOOKCASE_DIR / "bulei_nav.xhtml"
        if bulei_nav.exists():
            # 清空 category 树的旧数据
            conn.execute("DELETE FROM nav_node WHERE tree_type='category'")
            parse_xhtml_nav(bulei_nav, "category", conn)
            derive_bulei(conn)
        else:
            log.warning(f"未找到 bulei_nav.xhtml: {bulei_nav}")

        # ---- 步骤 3: 经文内部目录（toc/）----
        process_all_toc(conn)

        # ---- 步骤 4: 品目索引（mulu/）----
        process_all_mulu(conn)

        # 汇总统计
        elapsed = time.time() - start_time
        stats = {}
        for table in ["nav_node", "nav_bulei", "nav_toc", "nav_juan", "nav_mulu"]:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            stats[table] = row[0]

        log.info("=" * 60)
        log.info("ETL 完成！")
        log.info(f"耗时: {elapsed:.1f}s")
        log.info(f"数据库: {NAV_DB}")
        log.info("记录统计:")
        for table, count in stats.items():
            log.info(f"  {table}: {count}")
        log.info("=" * 60)

    except Exception as e:
        log.error(f"ETL 失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
