#!/usr/bin/env python3
"""验证 cbeta_nav.db 的数据质量"""
import sqlite3
from pathlib import Path

DB = Path("/data/fjlsc/10_etl/output/cbeta_nav.db")
if not DB.exists():
    print("❌ 数据库不存在，请先运行 ETL")
    exit(1)

conn = sqlite3.connect(str(DB))

print("=== 1. 各表记录数 ===")
for t in ["nav_node", "nav_bulei", "nav_toc", "nav_juan", "nav_mulu"]:
    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n}")

print("\n=== 2. 经藏目录根节点 (tree_type=canon) ===")
for r in conn.execute(
    "SELECT id, title, sort_order FROM nav_node "
    "WHERE tree_type='canon' AND parent_id IS NULL ORDER BY sort_order"
):
    print(f"  [{r[2]:2d}] {r[1]}")

print("\n=== 3. 部类目录根节点 (tree_type=category, 前5) ===")
for r in conn.execute(
    "SELECT title FROM nav_node "
    "WHERE tree_type='category' AND parent_id IS NULL ORDER BY sort_order LIMIT 5"
):
    print(f"  {r[0]}")

print("\n=== 4. T0001 验证 ===")
toc = conn.execute("SELECT COUNT(*) FROM nav_toc WHERE sutra_id='T0001'").fetchone()[0]
juan = conn.execute("SELECT COUNT(*) FROM nav_juan WHERE sutra_id='T0001'").fetchone()[0]
bulei = conn.execute("SELECT bu_lei FROM nav_bulei WHERE sutra_id='T0001'").fetchone()
print(f"  nav_toc: {toc} 条, nav_juan: {juan} 卷, 部类: {bulei[0] if bulei else '无'}")

print("\n=== 5. T0001 内部目录前5条 ===")
for r in conn.execute(
    "SELECT level, title, page_id FROM nav_toc WHERE sutra_id='T0001' ORDER BY seq LIMIT 5"
):
    print(f"  {'  '*r[0]}L{r[0]}: {r[1]} (#{r[2]})")

print("\n=== 6. sutra_id 格式样本 (T开头) ===")
for r in conn.execute(
    "SELECT DISTINCT sutra_id FROM nav_node "
    "WHERE sutra_id IS NOT NULL AND sutra_id LIKE 'T%' ORDER BY sutra_id LIMIT 5"
):
    print(f"  {r[0]}")

conn.close()
print("\n✅ 验证完成")
