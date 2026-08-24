"""
CBETA XML 标签扫描器
遍历所有 XML 文件，统计所有出现的标签、属性、命名空间，
用于验证 cbeta_README.md 的标签文档是否完整。

输出：
1. 所有唯一标签及其出现次数
2. 每个标签的属性分布
3. 未在 README 中记录的标签
"""

import argparse
import xml.etree.ElementTree as ET
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATAETL_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = DATAETL_DIR.parents[1]
XML_BASE = PROJECT_ROOT / "data" / "raw" / "cbeta_xml_p5"

# README 已记录的标签（用于对比）
README_TAGS = {
    # TEI header
    "TEI", "teiHeader", "fileDesc", "titleStmt", "title", "author",
    "publicationStmt", "idno", "date", "extent",
    "encodingDesc", "charDecl", "char", "charName", "charProp",
    "localName", "value", "mapping",
    # 正文
    "text", "body", "back",
    "lb", "pb", "p", "head",
    "div", "mulu", "juan", "jhead",
    "lg", "l", "caesura",
    "note", "app", "lem", "rdg",
    "anchor", "g", "byline", "ref",
    "space", "milestone",
}


def scan_file(xml_path, tag_counter, attr_counter, ns_set, sample_attrs):
    """扫描单个 XML 文件，收集标签和属性统计"""
    try:
        # 使用 fromstring 替代 parse，避免 lxml/ET 尝试解析远程 RNG schema 而挂起
        with open(str(xml_path), "r", encoding="utf-8") as f:
            content = f.read()
        tree = ET.ElementTree(ET.fromstring(content))
    except ET.ParseError as e:
        print(f"  ⚠️ 解析失败: {xml_path}: {e}", file=sys.stderr)
        return

    for elem in tree.iter():
        # 完整标签名（含命名空间）
        full_tag = elem.tag

        # 提取命名空间和本地名
        ns_match = re.match(r"\{(.+?)\}(.+)", full_tag)
        if ns_match:
            ns = ns_match.group(1)
            local = ns_match.group(2)
            ns_set.add(ns)
        else:
            local = full_tag

        tag_counter[local] += 1

        # 收集属性
        for attr_name in elem.attrib:
            # 去命名空间
            attr_match = re.match(r"\{.+?\}(.+)", attr_name)
            attr_local = attr_match.group(1) if attr_match else attr_name
            attr_counter[local][attr_local] += 1

            # 收集样本属性值（每个最多5个）
            key = f"{local}@{attr_local}"
            if len(sample_attrs[key]) < 5:
                val = elem.get(attr_name, "")
                if val and val not in sample_attrs[key]:
                    sample_attrs[key].add(val)


def main():
    parser = argparse.ArgumentParser(description="扫描 CBETA P5 XML 标签")
    parser.add_argument("--xml-base", type=Path, default=XML_BASE, help="CBETA P5 XML 根目录")
    args = parser.parse_args()
    tag_counter = Counter()
    attr_counter = defaultdict(Counter)  # tag -> {attr: count}
    ns_set = set()
    sample_attrs = defaultdict(set)  # "tag@attr" -> {val1, val2, ...}

    # 找到所有 XML 文件
    xml_files = sorted(args.xml_base.resolve().rglob("*.xml"))
    print(f"📂 找到 {len(xml_files)} 个 XML 文件")

    # 扫描每个文件
    for i, f in enumerate(xml_files):
        if i % 500 == 0:
            print(f"  扫描中... {i}/{len(xml_files)}")
        scan_file(f, tag_counter, attr_counter, ns_set, sample_attrs)

    print(f"\n{'='*70}")
    print(f"📊 扫描完成: {len(xml_files)} 文件, {len(tag_counter)} 种标签")
    print(f"{'='*70}")

    # 1. 命名空间
    print(f"\n## 命名空间 ({len(ns_set)})")
    for ns in sorted(ns_set):
        print(f"  - {ns}")

    # 2. 所有标签（按出现次数排序）
    print(f"\n## 所有标签 ({len(tag_counter)})")
    print(f"{'标签':<25} {'次数':>10}  {'属性'}")
    print("-" * 70)
    for tag, count in tag_counter.most_common():
        attrs = dict(attr_counter[tag])
        attr_str = ", ".join(
            f"{a}({c})" for a, c in sorted(attrs.items(), key=lambda x: -x[1])[:5]
        )
        in_readme = "✅" if tag in README_TAGS else "❌"
        print(f"  {in_readme} {tag:<22} {count:>10,}  {attr_str}")

    # 3. README 中有但扫描中没有的标签
    scanned_tags = set(tag_counter.keys())
    readme_only = README_TAGS - scanned_tags
    if readme_only:
        print(f"\n## README 有但未扫描到的标签 ({len(readme_only)})")
        for t in sorted(readme_only):
            print(f"  ⚠️ {t}")

    # 4. 扫描到但 README 没有的标签
    scan_only = scanned_tags - README_TAGS
    if scan_only:
        print(f"\n## 扫描到但 README 未记录的标签 ({len(scan_only)})")
        for t in sorted(scan_only):
            count = tag_counter[t]
            attrs = dict(attr_counter[t])
            attr_str = ", ".join(
                f"{a}({c})" for a, c in sorted(attrs.items(), key=lambda x: -x[1])[:3]
            )
            # 样本属性值
            samples = []
            for a in list(attrs.keys())[:3]:
                key = f"{t}@{a}"
                if sample_attrs[key]:
                    samples.append(f"{a}={list(sample_attrs[key])[:3]}")
            sample_str = " | ".join(samples) if samples else ""
            print(f"  🆕 {t:<22} {count:>10,}  attrs: {attr_str}")
            if sample_str:
                print(f"     样本: {sample_str}")

    # 5. 保存 JSON 报告
    report = {
        "file_count": len(xml_files),
        "tag_count": len(tag_counter),
        "namespaces": sorted(ns_set),
        "tags": {
            tag: {
                "count": count,
                "in_readme": tag in README_TAGS,
                "attributes": dict(attr_counter[tag]),
            }
            for tag, count in tag_counter.most_common()
        },
    }
    report_path = DATAETL_DIR / "output" / "tag_scan_report.json"
    os.makedirs(report_path.parent, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 JSON 报告: {report_path}")


if __name__ == "__main__":
    main()
