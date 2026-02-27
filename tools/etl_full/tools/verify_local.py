"""
本地标签验证脚本 — XML 源 vs 数据库对比

对比 XML 源文件的结构化数据（注释、校勘、目录）数量与数据库表行数。
统计逻辑与 ETL (etl_xml_to_db.py) 保持一致：
  - 校勘：优先查 <back>，不存在则查 <body>（匹配 extract_apparatus）
  - 注释：过滤内容为空的 <note>（匹配 extract_notes 的 get_text_recursive + strip）
  - 目录：统计 <cb:mulu>（匹配 extract_toc）

用法：
    python tools/verify_local.py T0001          # 验证单部经
    python tools/verify_local.py --canon A       # 验证整个藏经
    python tools/verify_local.py --all           # 验证全部

输出：
    output/verify_local_report.json
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

# 复用 ETL 的配置
ETL_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ETL_DIR.parent
XML_BASE = PROJECT_ROOT / "01_data_raw" / "cbeta_xml_p5"
DB_PATH = ETL_DIR / "output" / "cbeta.db"
OUTPUT_DIR = ETL_DIR / "output"

# XML 命名空间
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"

# 添加模块搜索路径（复用 gaiji_map）
# tools/.. (10_etl)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gaiji_map

# 与 ETL 一致的跳过标签
SKIP_TAGS_TEXT = {"note", "rdg", "anchor", "back", "mulu", "charDecl", "teiHeader"}
SELF_CLOSING = {"lb", "pb", "milestone"}


def _local_tag(element):
    """获取元素的本地名（去除命名空间）"""
    tag = element.tag
    if "}" in tag:
        return tag.split("}")[1]
    return tag


def get_text_recursive(element):
    """递归提取元素纯文本（与 ETL 逻辑完全一致，用于判断注释是否为空）"""
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
            # 跳过不输出（note, rdg, anchor, back, mulu, charDecl, teiHeader）
            pass
        elif tag == "space":
            quantity = child.get("quantity", "1")
            try:
                n = int(quantity)
            except ValueError:
                n = 1
            parts.append("　" * n)
        elif tag == "caesura":
            # 偈颂停顿
            parts.append("　")
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
            # 所有其余元素递归提取纯文本
            parts.append(get_text_recursive(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


def scan_xml(xml_files):
    """扫描 XML 文件，统计关键标签数量（与 ETL 逻辑对齐）"""
    juan_set = set()  # 用 set 去重卷号（跨册经文同一卷号只算一次）
    counts = {
        "juans": 0,       # 最后从 juan_set 计算
        "notes": 0,       # 非空 <note> 数量（匹配 extract_notes）
        "apps": 0,        # <app> 数量（匹配 extract_apparatus）
        "toc_entries": 0, # <cb:mulu> 数量（匹配 extract_toc）
    }

    for xml_path in xml_files:
        try:
            # 使用 fromstring 替代 parse，避免 IO 挂起
            with open(str(xml_path), "r", encoding="utf-8") as f:
                content = f.read()
            root = ET.fromstring(content)
            body = root.find(f".//{{{TEI_NS}}}body")
            if body is None:
                continue

            # --- 卷数：从 milestone 统计，用 set 去重（匹配 ETL 的 extract_juans） ---
            # extract_juans 逻辑：
            #   - len(milestones) <= 1：整个 body 归入该 milestone 的卷号（无则默认 1）
            #   - len(milestones) > 1：按 milestone 切分，first_n != 1 时前导内容归入默认卷 1
            milestones = [e for e in body.iter()
                          if _local_tag(e) == "milestone" and e.get("unit") == "juan"]
            if milestones:
                if len(milestones) == 1:
                    # 单 milestone：整个 body 归入该卷号（与 ETL 一致）
                    n = milestones[0].get("n", "1")
                    try:
                        juan_set.add(int(n))
                    except ValueError:
                        juan_set.add(1)
                else:
                    # 多 milestone：first_n != 1 时前导内容归入默认卷 1
                    first_n = milestones[0].get("n", "1")
                    try:
                        if int(first_n) != 1:
                            juan_set.add(1)  # 前导内容被分配到默认卷 1
                    except ValueError:
                        pass
                    for m in milestones:
                        n = m.get("n", "1")
                        try:
                            juan_set.add(int(n))
                        except ValueError:
                            pass
            else:
                juan_set.add(1)  # 无 milestone 的单卷经

            # --- 注释 + 目录：从 body 中统计（匹配 extract_notes / extract_toc）---
            for elem in body.iter():
                tag = _local_tag(elem)
                if tag == "note":
                    # 匹配 ETL：只统计内容非空的注释
                    content_text = get_text_recursive(elem).strip()
                    if content_text:
                        counts["notes"] += 1
                elif tag == "mulu":
                    counts["toc_entries"] += 1

            # --- 校勘：优先 back，退而 body（匹配 extract_apparatus）---
            search_root = root.find(f".//{{{TEI_NS}}}back")
            if search_root is None:
                search_root = body
            for elem in search_root.iter():
                tag = _local_tag(elem)
                if tag == "app":
                    # 匹配 ETL：有 lem 文本或有 rdg 子元素即算
                    lem_text = ""
                    readings = []
                    for child in elem:
                        ct = _local_tag(child)
                        if ct == "lem":
                            lem_text = get_text_recursive(child).strip()
                        elif ct == "rdg":
                            readings.append(child)
                    if lem_text or readings:
                        counts["apps"] += 1

        except Exception as e:
            print(f"  ⚠️ XML 解析失败 {os.path.basename(xml_path)}: {e}")

    counts["juans"] = len(juan_set)
    return counts


def scan_db(conn, sutra_id):
    """从数据库查询各项计数"""
    counts = {}

    # 卷数
    cur = conn.execute("SELECT COUNT(*) FROM content WHERE sutra_id=?", (sutra_id,))
    counts["juans"] = cur.fetchone()[0]

    # notes 表
    cur = conn.execute("SELECT COUNT(*) FROM notes WHERE sutra_id=?", (sutra_id,))
    counts["notes"] = cur.fetchone()[0]

    # apparatus 表
    cur = conn.execute("SELECT COUNT(*) FROM apparatus WHERE sutra_id=?", (sutra_id,))
    counts["apps"] = cur.fetchone()[0]

    # toc 表
    cur = conn.execute("SELECT COUNT(*) FROM toc WHERE sutra_id=?", (sutra_id,))
    counts["toc_entries"] = cur.fetchone()[0]

    return counts


def find_sutra_files(sutra_id):
    """根据 sutra_id 找到 P5 XML 文件"""
    # 情况1：sutra_id 包含 'n'，说明保留了完整的 xml_id 格式
    # （如 J01nA042 — 嘉兴藏大写编号，ETL 正则未能解析）
    if "n" in sutra_id:
        # 提取藏经代码用于定位目录
        m = re.match(r"([A-Z]+)", sutra_id)
        if m:
            canon = m.group(1)
            pattern = str(XML_BASE / canon / "*" / f"{sutra_id}.xml")
            files = sorted(glob.glob(pattern))
            if files:
                return files

    # 情况2：标准格式如 T0001, Ba001, GA0037
    match = re.match(r"([A-Z]+)([a-z]?\d+[a-z]?\d*)", sutra_id)
    if not match:
        return []
    canon = match.group(1)
    sutra_no = match.group(2)
    # 先精确匹配（如 T*n0001.xml）
    pattern = str(XML_BASE / canon / "*" / f"{canon}*n{sutra_no}.xml")
    files = sorted(glob.glob(pattern))
    if not files:
        # 回退：匹配带大写后缀的文件（如 T02n0150A.xml, T02n0150B.xml）
        pattern = str(XML_BASE / canon / "*" / f"{canon}*n{sutra_no}[A-Z].xml")
        files = sorted(glob.glob(pattern))
    return files


def verify_sutra(sutra_id, conn):
    """验证单部经，返回结果 dict"""
    xml_files = find_sutra_files(sutra_id)
    if not xml_files:
        return {"sutra_id": sutra_id, "status": "skip", "reason": "无 XML 文件"}

    xml = scan_xml(xml_files)
    db = scan_db(conn, sutra_id)

    # 比较结果（全部要求精确匹配）
    checks = []
    all_pass = True

    for field, label in [
        ("juans", "卷数"), ("notes", "注释"),
        ("apps", "校勘"), ("toc_entries", "目录"),
    ]:
        xml_val = xml[field]
        db_val = db[field]
        match = xml_val == db_val
        checks.append({"item": label, "xml": xml_val, "db": db_val, "pass": match})
        if not match:
            all_pass = False

    # 打印结果
    status = "✅" if all_pass else "❌"
    items_str = " | ".join(
        f"{c['item']}={'✅' if c['pass'] else '❌'}{c['xml']}→{c['db']}"
        for c in checks
    )
    print(f"  {status} {sutra_id}: {items_str}")

    return {
        "sutra_id": sutra_id,
        "status": "pass" if all_pass else "fail",
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description="本地标签验证：XML vs 数据库")
    parser.add_argument("target", nargs="?", default=None, help="经号或藏经代码")
    parser.add_argument("--canon", type=str, help="按藏经验证（如 A）")
    parser.add_argument("--all", action="store_true", help="验证全部已转换经典")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    gaiji_map.load_gaiji_map()

    # 确定要验证的经典
    sutra_ids = []
    if args.all:
        cur = conn.execute("SELECT sutra_id FROM catalog ORDER BY sutra_id")
        sutra_ids = [row[0] for row in cur]
    elif args.canon:
        cur = conn.execute(
            "SELECT sutra_id FROM catalog WHERE canon=? ORDER BY sutra_id",
            (args.canon,),
        )
        sutra_ids = [row[0] for row in cur]
    elif args.target:
        sutra_ids = [args.target]
    else:
        parser.print_help()
        return

    print(f"📋 验证 {len(sutra_ids)} 部经典")
    print()

    results = []
    passed = failed = skipped = 0
    start = time.time()

    for sid in sutra_ids:
        r = verify_sutra(sid, conn)
        results.append(r)
        if r["status"] == "pass":
            passed += 1
        elif r["status"] == "fail":
            failed += 1
        else:
            skipped += 1

    elapsed = time.time() - start
    print()
    print("=" * 50)
    print(f"✅ 通过: {passed}  ❌ 不一致: {failed}  ⏭️ 跳过: {skipped}")
    print(f"⏱️ 耗时: {elapsed:.1f} 秒")

    # 保存报告
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = OUTPUT_DIR / "verify_local_report.json"
    report = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"📄 报告: {report_path}")

    conn.close()


if __name__ == "__main__":
    main()
