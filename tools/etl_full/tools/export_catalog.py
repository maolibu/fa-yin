"""
综合目录导出工具 — 从 cbeta.db + cbeta_nav.db 生成完整目录 CSV

生成内容：
  1. catalog_full.csv — 主目录（经号、名称、作者、藏经、卷数、目录条目数）
  2. 终端输出摘要统计

用法：
    python tools/export_catalog.py              # 默认导出
    python tools/export_catalog.py --xlsx       # 同时生成 xlsx（需要 openpyxl）
"""

import csv
import os
import sqlite3
import time
import argparse
from pathlib import Path

# 配置
ETL_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ETL_DIR / "output"
CANON_DB = OUTPUT_DIR / "cbeta.db"
NAV_DB = OUTPUT_DIR / "cbeta_nav.db"


def export_catalog():
    """导出综合目录"""
    start = time.time()

    if not CANON_DB.exists():
        print(f"❌ 找不到 cbeta.db: {CANON_DB}")
        return

    conn = sqlite3.connect(str(CANON_DB))
    conn.row_factory = sqlite3.Row

    # 获取 catalog 表结构
    cols = [r[1] for r in conn.execute("PRAGMA table_info(catalog)").fetchall()]
    print(f"📋 catalog 字段: {cols}")
    print()

    parser = argparse.ArgumentParser(description="综合目录导出工具")
    parser.add_argument("--fast", action="store_true", help="快速模式（跳过字数统计，瞬间完成）")
    parser.add_argument("--xlsx", action="store_true", help="同时生成 xlsx（需要 openpyxl）")
    args = parser.parse_args()

    # 主查询
    if args.fast:
        print("🚀 快速模式：跳过全库字数统计...")
        query = """
            SELECT 
                sutra_id, canon, volume, title, author, total_juan, category,
                (SELECT COUNT(*) FROM content WHERE content.sutra_id = catalog.sutra_id) AS juan_count_db,
                0 AS total_chars
            FROM catalog
            ORDER BY sutra_id
        """
    else:
        # full scan aggregation (slow on 4.7GB+ DB)
        query = """
            SELECT 
                c.sutra_id,
                c.canon,
                c.volume,
                c.title,
                c.author,
                c.total_juan,
                c.category,
                COUNT(DISTINCT ct.juan) AS juan_count_db,
                SUM(LENGTH(ct.plain_text)) AS total_chars
            FROM catalog c
            LEFT JOIN content ct ON c.sutra_id = ct.sutra_id
            GROUP BY c.sutra_id
            ORDER BY c.sutra_id
        """

    print("⏳ 查询 cbeta.db（可能需要几秒）...")
    rows = conn.execute(query).fetchall()
    print(f"📊 查到 {len(rows)} 条记录")

    # 如果有 cbeta_nav.db，附加目录条目数和部类信息
    nav_toc_counts = {}
    nav_juan_counts = {}
    nav_bulei_map = {}  # sutra_id -> 部类名
    if NAV_DB.exists():
        nav_conn = sqlite3.connect(str(NAV_DB))
        print("📊 加载 cbeta_nav.db 数据...")
        for r in nav_conn.execute("SELECT sutra_id, COUNT(*) FROM nav_toc GROUP BY sutra_id"):
            nav_toc_counts[r[0]] = r[1]
        for r in nav_conn.execute("SELECT sutra_id, COUNT(*) FROM nav_juan GROUP BY sutra_id"):
            nav_juan_counts[r[0]] = r[1]
        # 读取部类映射
        try:
            for r in nav_conn.execute("SELECT sutra_id, bu_lei FROM nav_bulei"):
                nav_bulei_map[r[0]] = r[1]
            print(f"  nav_bulei: {len(nav_bulei_map)} 经有部类数据")
        except Exception:
            print("  ⚠️ nav_bulei 表不存在，跳过部类（请先运行 etl_bookcase_nav.py）")
        nav_conn.close()
        print(f"  nav_toc: {len(nav_toc_counts)} 经有目录数据")
        print(f"  nav_juan: {len(nav_juan_counts)} 经有卷索引数据")

    # 写入 CSV
    csv_path = OUTPUT_DIR / "catalog_full.csv"
    headers = [
        "sutra_id",     # 经号
        "bu_lei",       # 部类（如 '阿含部類'）
        "canon",        # 藏经代码（T/X/J 等）
        "volume",       # 册号
        "title",        # 经名
        "author",       # 作者/译者
        "category",     # 所属藏经中文名
        "total_juan",   # 元数据卷数
        "juan_count",   # DB 实际卷数
        "total_chars",  # 总字数（纯文本）
        "toc_entries",  # 目录条目数（来自 cbeta_nav.db）
        "nav_juans",    # 卷索引数（来自 cbeta_nav.db）
    ]

    # 按部类+经号排序
    rows_with_bulei = []
    for row in rows:
        sid = row["sutra_id"]
        bu_lei = nav_bulei_map.get(sid, "")
        rows_with_bulei.append((bu_lei, row))
    rows_with_bulei.sort(key=lambda x: (x[0] if x[0] else "zzz", x[1]["sutra_id"]))

    with open(str(csv_path), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)

        for bu_lei, row in rows_with_bulei:
            sid = row["sutra_id"]
            w.writerow([
                sid,
                bu_lei,
                row["canon"] or "",
                row["volume"] or "",
                row["title"] or "",
                row["author"] or "",
                row["category"] or "",
                row["total_juan"] or "",
                row["juan_count_db"],
                row["total_chars"] or 0,
                nav_toc_counts.get(sid, 0),
                nav_juan_counts.get(sid, 0),
            ])

    conn.close()
    elapsed = time.time() - start

    # 统计摘要
    print()
    print("=" * 60)
    print(f"✅ 已导出: {csv_path}")
    print(f"📊 总经典数: {len(rows)}")
    print(f"📊 总卷数: {sum(r['juan_count_db'] for r in rows)}")
    total_chars = sum(r['total_chars'] or 0 for r in rows)
    print(f"📊 总字数: {total_chars:,} ({total_chars/10000:.0f} 万字)")
    print(f"💾 文件大小: {csv_path.stat().st_size / 1024:.0f} KB")
    print(f"⏱️ 耗时: {elapsed:.1f} 秒")

    # 按部类汇总
    if nav_bulei_map:
        print()
        print("📚 各部类汇总:")
        print(f"{'部类':<20} {'经典数':>6} {'卷数':>6} {'万字':>8}")
        print("-" * 45)
        bulei_stats = {}
        for row in rows:
            bl = nav_bulei_map.get(row["sutra_id"], "(未分类)")
            if bl not in bulei_stats:
                bulei_stats[bl] = {"count": 0, "juans": 0, "chars": 0}
            bulei_stats[bl]["count"] += 1
            bulei_stats[bl]["juans"] += row["juan_count_db"]
            bulei_stats[bl]["chars"] += row["total_chars"] or 0

        for bl, stats in sorted(bulei_stats.items(), key=lambda x: -x[1]["count"]):
            print(f"  {bl:<18} {stats['count']:>6} {stats['juans']:>6} {stats['chars']/10000:>8.0f}")

    # 按藏经汇总
    print()
    print("📚 各藏经汇总:")
    print(f"{'藏经':<20} {'经典数':>6} {'卷数':>6} {'万字':>8}")
    print("-" * 45)
    canon_stats = {}
    for row in rows:
        cat = row["category"] or "(未分类)"
        if cat not in canon_stats:
            canon_stats[cat] = {"count": 0, "juans": 0, "chars": 0}
        canon_stats[cat]["count"] += 1
        canon_stats[cat]["juans"] += row["juan_count_db"]
        canon_stats[cat]["chars"] += row["total_chars"] or 0

    for cat, stats in sorted(canon_stats.items(), key=lambda x: -x[1]["count"]):
        print(f"  {cat:<18} {stats['count']:>6} {stats['juans']:>6} {stats['chars']/10000:>8.0f}")


if __name__ == "__main__":
    export_catalog()
