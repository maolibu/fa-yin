"""
将 6 部精选佛学词典 + 萌典 导入 SQLite 数据库

词典清单（全部版权安全）：
  1. 丁福保佛學大辭典 (13Dicts, 繁体, 公有领域)
  2. 通用汉语辞典 (CC BY-ND 3.0)
  3. Soothill-Hodous 漢英佛學詞典 (13Dicts, 公有领域)
  4. 法相辞典·朱芾煌 (28Dicts, 公有领域)
  5. 三藏法数·明一如 (28Dicts, 公有领域)
  6. 祖庭事苑·北宋陈善卿 (28Dicts, 古典公有)

用法: python build_dict_db.py
输出: 60_ready/data/dicts/dicts.db
"""
import json
import re
import sqlite3
import time
from pathlib import Path

import opencc

# ═══ 配置 ═══
ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent  # tools/dict_converter → tools → 90_fa_yin
OUTPUT_DB = PROJECT_ROOT / "data" / "db" / "dicts.db"

# 繁简转换器
s2t = opencc.OpenCC("s2t")
t2s = opencc.OpenCC("t2s")

# HTML 标签清理
HTML_TAG_RE = re.compile(r"<[^>]+>")

# 垃圾词条后缀（BGL 嵌入文件）
JUNK_SUFFIXES = (".png", ".ico", ".bmp", ".gif", ".jpg", ".css", ".js")

# ═══ 白名单：只导入这 6 部词典 ═══
# 格式: (子目录/文件名去.json, 显示名, 字符类型, 版权说明)
DICT_WHITELIST = [
    # --- 13Dicts (DILA/DDBC) ---
    ("13dicts/babylon-dingfubao.dila", "丁福保佛學大辭典", "繁体",
     "公有领域 (1922年出版, 作者1952年去世)"),
    ("13dicts/stardict-ddbc.soothill-hodous", "Soothill-Hodous 漢英佛學詞典", "繁体",
     "公有领域 (1937年出版)"),
    # --- 28Dicts (fodict2) ---
    ("28dicts/009.faxiang-j", "法相辞典 (朱芾煌 编)", "简体",
     "公有领域 (1939年出版)"),
    ("28dicts/004.szfs-j", "三藏法数 (明·一如等 撰)", "简体",
     "公有领域 (明朝永乐年间)"),
    ("28dicts/020.ztsy-j", "祖庭事苑 (北宋·陈善卿)", "简体",
     "公有领域 (北宋古籍)"),
]

# 萌典单独处理（格式不同）
MOEDICT_FILE = ROOT / "萌典.json"
MOEDICT_ID = "moedict"
MOEDICT_NAME = "通用汉语辞典"
MOEDICT_CHAR = "繁体"
MOEDICT_LICENSE = "CC BY-ND 3.0 (来源: moedict.tw)"


def clean_definition(text: str) -> str:
    """清理释义中的 HTML 标签"""
    if "<" in text:
        text = HTML_TAG_RE.sub("", text)
    return text.strip()


def flatten_moedict_entry(item: dict) -> str:
    """
    展平萌典嵌套结构为纯文本释义。
    输入: {title, heteronyms: [{bopomofo, pinyin, definitions: [{def, quote, example}]}]}
    输出: 包含注音 + 多义项的文本
    """
    parts = []
    heteronyms = item.get("heteronyms", [])
    if not isinstance(heteronyms, list):
        return ""

    for het in heteronyms:
        if not isinstance(het, dict):
            continue
        het_parts = []

        # 注音 + 拼音
        bopomofo = het.get("bopomofo", "")
        pinyin = het.get("pinyin", "")
        reading = []
        if bopomofo:
            reading.append(bopomofo)
        if pinyin:
            reading.append(pinyin)
        if reading:
            het_parts.append("【" + " / ".join(reading) + "】")

        # 释义
        definitions = het.get("definitions", [])
        if isinstance(definitions, list):
            circled = "❶❷❸❹❺❻❼❽❾❿"
            for i, d in enumerate(definitions):
                if not isinstance(d, dict):
                    continue
                defn = d.get("def", "")
                if not defn:
                    continue
                # 清理 HTML
                defn = clean_definition(defn)
                if not defn:
                    continue
                prefix = circled[i] if i < len(circled) else f"({i + 1})"
                entry = f"{prefix} {defn}"
                # 附加引用
                quote = d.get("quote", [])
                if isinstance(quote, list):
                    for q in quote:
                        entry += f"\n　　📖 {q}"
                elif isinstance(quote, str) and quote:
                    entry += f"\n　　📖 {quote}"
                # 附加例句
                example = d.get("example", [])
                if isinstance(example, list):
                    for ex in example:
                        entry += f"\n　　例：{ex}"
                elif isinstance(example, str) and example:
                    entry += f"\n　　例：{example}"
                het_parts.append(entry)

        if het_parts:
            parts.append("\n".join(het_parts))

    return "\n\n".join(parts)


def import_standard_dict(conn, json_path: Path, display_name: str,
                         char_type: str, license_info: str) -> int:
    """导入标准格式词典 (13dicts/28dicts 的 {meta, entries} 格式)"""
    data = json.loads(json_path.read_text("utf-8"))
    meta = data.get("meta", {})
    dict_id = meta.get("id", json_path.stem)
    entries = data.get("entries", [])

    valid_entries = []
    for e in entries:
        term = e.get("term", "").strip()
        defn = e.get("definition", "").strip()

        # 跳过垃圾条目
        if not term or any(term.endswith(s) for s in JUNK_SUFFIXES):
            continue
        if not defn:
            continue

        defn = clean_definition(defn)
        if not defn:
            continue

        # 繁简双列
        term_tc = s2t.convert(term)
        term_sc = t2s.convert(term)
        valid_entries.append((dict_id, term, term_tc, term_sc, defn))

    # 批量插入
    conn.executemany(
        "INSERT INTO entries (dict_id, term, term_tc, term_sc, definition) "
        "VALUES (?, ?, ?, ?, ?)",
        valid_entries,
    )

    # 元数据
    conn.execute(
        "INSERT INTO dictionaries (dict_id, name, source, entry_count, char_type, license) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (dict_id, display_name, meta.get("source", ""), len(valid_entries),
         char_type, license_info),
    )

    print(f"  📖 {display_name} — {len(valid_entries):,} 条 [{char_type}]")
    return len(valid_entries)


def import_moedict(conn) -> int:
    """导入萌典（教育部重编国语辞典），格式为 [{title, heteronyms, ...}]"""
    print(f"  📖 {MOEDICT_NAME} — 加载中...")
    data = json.loads(MOEDICT_FILE.read_text("utf-8"))

    valid_entries = []
    skipped = 0
    for item in data:
        if not isinstance(item, dict):
            continue

        title = item.get("title", "").strip()
        if not title:
            continue

        # 跳过组字式残缺条目
        if "{" in title or "}" in title:
            skipped += 1
            continue

        # 展平释义
        defn = flatten_moedict_entry(item)
        if not defn:
            continue

        # 清理 HTML
        defn = clean_definition(defn)
        if not defn:
            continue

        # 繁简双列
        term_tc = s2t.convert(title)
        term_sc = t2s.convert(title)
        valid_entries.append((MOEDICT_ID, title, term_tc, term_sc, defn))

    # 批量插入
    conn.executemany(
        "INSERT INTO entries (dict_id, term, term_tc, term_sc, definition) "
        "VALUES (?, ?, ?, ?, ?)",
        valid_entries,
    )

    # 元数据
    conn.execute(
        "INSERT INTO dictionaries (dict_id, name, source, entry_count, char_type, license) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (MOEDICT_ID, MOEDICT_NAME, "moedict.tw", len(valid_entries),
         MOEDICT_CHAR, MOEDICT_LICENSE),
    )

    print(f"  📖 {MOEDICT_NAME} — {len(valid_entries):,} 条 [{MOEDICT_CHAR}]"
          f" (跳过组字式 {skipped} 条)")
    return len(valid_entries)


def build_db():
    """主构建流程"""
    # 创建输出目录
    OUTPUT_DB.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_DB.exists():
        OUTPUT_DB.unlink()

    conn = sqlite3.connect(str(OUTPUT_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # 词典元数据表（新增 license 列）
    conn.execute("""
        CREATE TABLE dictionaries (
            dict_id     TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            source      TEXT,
            entry_count INTEGER DEFAULT 0,
            char_type   TEXT,
            license     TEXT
        )
    """)

    # 词条表
    conn.execute("""
        CREATE TABLE entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            dict_id    TEXT NOT NULL,
            term       TEXT NOT NULL,
            term_tc    TEXT NOT NULL,
            term_sc    TEXT NOT NULL,
            definition TEXT NOT NULL,
            FOREIGN KEY (dict_id) REFERENCES dictionaries(dict_id)
        )
    """)

    total_entries = 0
    total_dicts = 0

    # 1. 导入白名单词典
    for stem, name, char_type, license_info in DICT_WHITELIST:
        json_path = ROOT / f"{stem}.json"
        if not json_path.exists():
            print(f"  ⚠️  未找到: {json_path}")
            continue
        count = import_standard_dict(conn, json_path, name, char_type, license_info)
        total_entries += count
        total_dicts += 1

    # 2. 导入萌典
    if MOEDICT_FILE.exists():
        count = import_moedict(conn)
        total_entries += count
        total_dicts += 1
    else:
        print(f"  ⚠️  未找到萌典: {MOEDICT_FILE}")

    # 3. 创建索引
    print("\n  📊 建立索引...")
    conn.execute("CREATE INDEX idx_entries_term_tc ON entries (term_tc)")
    conn.execute("CREATE INDEX idx_entries_term_sc ON entries (term_sc)")
    conn.execute("CREATE INDEX idx_entries_dict ON entries (dict_id)")

    # 4. FTS5 全文索引（用于模糊搜索）
    print("  🔍 建立 FTS5 全文索引...")
    conn.execute("""
        CREATE VIRTUAL TABLE entries_fts USING fts5(
            term, term_tc, term_sc, definition,
            content='entries',
            content_rowid='id',
            tokenize='unicode61'
        )
    """)
    conn.execute("""
        INSERT INTO entries_fts (rowid, term, term_tc, term_sc, definition)
        SELECT id, term, term_tc, term_sc, definition FROM entries
    """)

    conn.commit()

    # 统计
    print(f"\n{'=' * 50}")
    print(f"  ✅ 完成: {total_dicts} 部词典, {total_entries:,} 条目")
    print(f"  📁 输出: {OUTPUT_DB}")
    size_mb = OUTPUT_DB.stat().st_size / 1024 / 1024
    print(f"  💾 大小: {size_mb:.1f} MB")
    print(f"{'=' * 50}")

    conn.close()


if __name__ == "__main__":
    start = time.time()
    print("═══ 佛学词典数据库构建（6 部精选）═══\n")
    build_db()
    elapsed = time.time() - start
    print(f"\n  ⏱️  耗时: {elapsed:.1f} 秒")
