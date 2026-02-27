"""
CBETA Bookcase XML → 搜索专用 SQLite 数据库
使用与阅读页面相同的分卷版 XML 数据（cbeta/XML/），用户只需下载一份数据。

用法：
    python etl_build_search.py --all               # 转换全部（推荐）
    python etl_build_search.py --canon T            # 转换大正藏
    python etl_build_search.py T0251                # 转换单部经

数据源：data/raw/cbeta/XML/（Bookcase 分卷版，21960 文件）
输出：  data/db/cbeta_search.db
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
ETL_DIR = Path(__file__).resolve().parent
SRC_DIR = ETL_DIR.parent
sys.path.insert(0, str(ETL_DIR))
sys.path.insert(0, str(SRC_DIR))
import gaiji_map
import config

# OpenCC 繁→简
from opencc import OpenCC
cc_t2s = OpenCC('t2s')

# ============================================================
# 配置（从 config 模块读取，零硬编码）
# ============================================================

# Bookcase 分卷版 XML 路径（与阅读页面共用同一份数据）
XML_BASE = Path(os.getenv(
    "CBETA_XML_BASE",
    str(config.CBETA_BASE / "XML")
))

# 搜索数据库输出路径
DB_PATH = config.CBETA_SEARCH_DB

LOG_DIR = ETL_DIR / "logs"
GAIJI_PATH = config.GAIJI_PATH

# XML 命名空间
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", TEI_NS)
ET.register_namespace("cb", CB_NS)

# ============================================================
# Schema（内嵌）
# ============================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS catalog (
    sutra_id   TEXT PRIMARY KEY,
    canon      TEXT NOT NULL,
    title      TEXT,
    title_sc   TEXT,
    author     TEXT,
    total_juan INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS content (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sutra_id      TEXT NOT NULL,
    juan          INTEGER NOT NULL,
    plain_text    TEXT,
    plain_text_sc TEXT,
    FOREIGN KEY (sutra_id) REFERENCES catalog(sutra_id),
    UNIQUE(sutra_id, juan)
);

CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
    sutra_id,
    juan,
    plain_text_sc,
    content=content,
    content_rowid=id,
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS content_ai AFTER INSERT ON content BEGIN
    INSERT INTO content_fts(rowid, sutra_id, juan, plain_text_sc)
    VALUES (new.id, new.sutra_id, new.juan, new.plain_text_sc);
END;

CREATE TRIGGER IF NOT EXISTS content_ad AFTER DELETE ON content BEGIN
    INSERT INTO content_fts(content_fts, rowid, sutra_id, juan, plain_text_sc)
    VALUES ('delete', old.id, old.sutra_id, old.juan, old.plain_text_sc);
END;

CREATE TRIGGER IF NOT EXISTS content_au AFTER UPDATE ON content BEGIN
    INSERT INTO content_fts(content_fts, rowid, sutra_id, juan, plain_text_sc)
    VALUES ('delete', old.id, old.sutra_id, old.juan, old.plain_text_sc);
    INSERT INTO content_fts(rowid, sutra_id, juan, plain_text_sc)
    VALUES (new.id, new.sutra_id, new.juan, new.plain_text_sc);
END;

CREATE INDEX IF NOT EXISTS idx_catalog_canon ON catalog(canon);
CREATE INDEX IF NOT EXISTS idx_content_sutra ON content(sutra_id);
CREATE INDEX IF NOT EXISTS idx_catalog_title_sc ON catalog(title_sc);
"""


def init_db(db_path):
    """初始化搜索数据库"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ============================================================
# 辅助函数
# ============================================================
def _local_tag(element):
    """获取元素的本地名（去除命名空间）"""
    tag = element.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


# 跳过类标签
SKIP_TAGS_TEXT = {
    "note", "rdg", "anchor", "back",
    "mulu", "charDecl", "teiHeader",
}

SELF_CLOSING = {
    "lb", "pb", "milestone", "anchor", "space", "caesura",
}


def get_text_recursive(element):
    """递归提取元素的纯文本内容，覆盖 CBETA XML 全部标签"""
    parts = []
    if element.text:
        parts.append(element.text)

    for child in element:
        tag = _local_tag(child)

        if tag == "g":
            ref = child.get("ref", "")
            cb_id = ref.lstrip("#")
            resolved = gaiji_map.resolve(cb_id)
            parts.append(resolved)
        elif tag == "lem":
            parts.append(get_text_recursive(child))
        elif tag == "app":
            parts.append(get_text_recursive(child))
        elif tag in SKIP_TAGS_TEXT:
            pass
        elif tag == "space":
            quantity = child.get("quantity", "1")
            try:
                n = int(quantity)
            except ValueError:
                n = 1
            parts.append("　" * n)
        elif tag == "caesura":
            parts.append("　")
        elif tag == "choice":
            parts.append(get_text_recursive(child))
        elif tag in ("sic", "orig"):
            pass
        elif tag in ("corr", "reg"):
            parts.append(get_text_recursive(child))
        elif tag in SELF_CLOSING:
            pass
        else:
            parts.append(get_text_recursive(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


# ============================================================
# 元数据提取
# ============================================================
def extract_metadata(tree):
    """从 teiHeader 提取经文元数据"""
    root = tree.getroot()
    xml_id = root.get(f"{{{XML_NS}}}id", "")

    match = re.match(r"([A-Z]+)(\d+)n([a-z]*)(\d+[a-z]?)", xml_id)
    if match:
        canon = match.group(1)
        sutra_no = match.group(3) + match.group(4)
        sutra_id = f"{canon}{sutra_no.zfill(4)}"
    else:
        canon = ""
        sutra_id = xml_id

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

    author = ""
    author_elem = root.find(f".//{{{TEI_NS}}}titleStmt/{{{TEI_NS}}}author")
    if author_elem is not None and author_elem.text:
        author = author_elem.text.strip()

    total_juan = 1
    extent_elem = root.find(f".//{{{TEI_NS}}}extent")
    if extent_elem is not None and extent_elem.text:
        juan_match = re.search(r"(\d+)", extent_elem.text)
        if juan_match:
            total_juan = int(juan_match.group(1))

    return {
        "sutra_id": sutra_id,
        "canon": canon,
        "title": title,
        "title_sc": cc_t2s.convert(title),
        "author": author,
        "total_juan": total_juan,
    }


# ============================================================
# 从文件名解析卷号
# ============================================================
def parse_juan_from_filename(filename):
    """从 Bookcase 文件名解析卷号，如 T08n0251_001.xml → 1"""
    m = re.search(r"_(\d+)\.xml$", filename)
    if m:
        return int(m.group(1))
    return 1


# ============================================================
# 单文件处理（Bookcase 分卷版：每文件 = 一卷）
# ============================================================
_processed_sutras = set()

def process_file(xml_path, conn):
    """处理单个 Bookcase XML 文件（一卷），写入搜索数据库"""
    global _processed_sutras
    try:
        with open(str(xml_path), "r", encoding="utf-8") as f:
            content = f.read()
        tree = ET.ElementTree(ET.fromstring(content))

        meta = extract_metadata(tree)
        sutra_id = meta["sutra_id"]
        juan = parse_juan_from_filename(os.path.basename(xml_path))

        # 首次遇到此经，写入 catalog
        if sutra_id not in _processed_sutras:
            _processed_sutras.add(sutra_id)
            conn.execute(
                """INSERT OR REPLACE INTO catalog
                   (sutra_id, canon, title, title_sc, author, total_juan)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sutra_id, meta["canon"], meta["title"],
                 meta["title_sc"], meta["author"], meta["total_juan"]),
            )

        # 直接提取 body 纯文本（每文件就是一卷，不需要 milestone 分卷）
        root = tree.getroot()
        body = root.find(f".//{{{TEI_NS}}}body")
        if body is not None:
            plain_text = get_text_recursive(body)
            plain_text_sc = cc_t2s.convert(plain_text)

            conn.execute(
                """INSERT OR REPLACE INTO content
                   (sutra_id, juan, plain_text, plain_text_sc)
                   VALUES (?, ?, ?, ?)""",
                (sutra_id, juan, plain_text, plain_text_sc),
            )

        return sutra_id, juan

    except Exception as e:
        conn.rollback()
        print(f"  ❌ 处理失败 {xml_path}: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# 文件发现（适配 Bookcase 目录结构）
# Bookcase 结构: XML/{Canon}/{CanonVol}/{CanonVol}n{No}_{Juan}.xml
# 例: XML/T/T08/T08n0251_001.xml
# ============================================================
def find_xml_files(target):
    """根据目标参数找到要处理的 XML 文件列表"""
    if target == "--all":
        return sorted(glob.glob(str(XML_BASE / "*" / "*" / "*.xml")))

    # 藏经代码（如 T, X, A）
    canon_dir = XML_BASE / target
    if canon_dir.is_dir():
        return sorted(glob.glob(str(canon_dir / "*" / "*.xml")))

    # 经号（如 T0251 或 T08n0251）
    # 尝试匹配所有卷
    match_short = re.match(r"([A-Z]+)(\d+)$", target)
    if match_short:
        canon = match_short.group(1)
        sutra_no = match_short.group(2)
        # 搜索所有卷册目录
        pattern = str(XML_BASE / canon / "*" / f"*n{sutra_no}_*.xml")
        files = sorted(glob.glob(pattern))
        if files:
            return files
        # 也尝试不补零
        pattern2 = str(XML_BASE / canon / "*" / f"*n{sutra_no.lstrip('0')}_*.xml")
        files = sorted(glob.glob(pattern2))
        if files:
            return files
        print(f"❌ 找不到经号 {target} 的文件")
        return []

    print(f"❌ 无法识别目标: {target}")
    return []


# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="CBETA Bookcase XML → 搜索专用数据库（含简体列 + FTS5）"
    )
    parser.add_argument(
        "target", nargs="?", default=None,
        help="经号（如 T0251）或藏经代码（如 T）",
    )
    parser.add_argument("--canon", type=str, help="按藏经代码转换")
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
    print(f"📂 数据源: {XML_BASE}")
    print(f"💾 搜索数据库: {DB_PATH}")
    print(f"🔤 OpenCC 繁→简: 已启用")
    print()

    global _processed_sutras
    _processed_sutras = set()

    conn = init_db(DB_PATH)
    gaiji_map.load_gaiji_map(str(GAIJI_PATH))
    print("✅ Gaiji 映射表已加载")

    success = 0
    errors = []
    start_time = time.time()

    for i, xml_path in enumerate(xml_files, 1):
        filename = os.path.basename(xml_path)
        # 每100个文件显示一次进度，避免刷屏
        if i % 100 == 1 or i == len(xml_files):
            print(f"  [{i}/{len(xml_files)}] {filename} ...", end=" ", flush=True)

        result = process_file(xml_path, conn)
        if result:
            if i % 100 == 1 or i == len(xml_files):
                sutra_id, juan = result
                print(f"✅ {sutra_id} 卷{juan}")
            success += 1
        else:
            errors.append(xml_path)

        # 每500个文件提交一次
        if i % 500 == 0:
            conn.commit()

    conn.commit()
    elapsed = time.time() - start_time

    print()
    print("=" * 50)
    print(f"✅ 成功: {success}/{len(xml_files)}")
    print(f"❌ 失败: {len(errors)}/{len(xml_files)}")
    print(f"⏱️ 耗时: {elapsed:.1f} 秒")

    for table in ["catalog", "content"]:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"📊 {table}: {count} 条")
        except Exception:
            pass

    db_size = os.path.getsize(str(DB_PATH))
    print(f"💾 数据库体积: {db_size / 1024 / 1024:.1f} MB")

    if errors:
        print()
        print(f"❌ 失败文件: {len(errors)} 个")
        os.makedirs(LOG_DIR, exist_ok=True)
        log_path = LOG_DIR / "search_etl_errors.log"
        with open(log_path, "w", encoding="utf-8") as f:
            for e in errors:
                f.write(f"{e}\n")
        print(f"  日志已保存: {log_path}")

    conn.close()
    print(f"\n✅ 搜索数据库已生成: {DB_PATH}")


if __name__ == "__main__":
    main()
