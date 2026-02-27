"""
扫描所有 CBETA XML 文件，统计 <note> 标签的所有格式组合。
输出：按 (type, place, parent_tag, has_n) 分组的频次统计。
结果写入 tests/note_formats_report.txt
"""

import sys
import os
import re
from pathlib import Path
from collections import Counter
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

CBETA_XML_DIR = config.CBETA_BASE / "XML"
REPORT_PATH = Path(__file__).parent / "note_formats_report.txt"
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"


def local_tag(tag):
    """去除命名空间"""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def find_xml_files():
    pattern = re.compile(r'^[A-Z]\d+n\d+[a-zA-Z]?_\d+\.xml$')
    return sorted(f for f in CBETA_XML_DIR.rglob("*.xml") if pattern.match(f.name))


def main():
    xml_files = find_xml_files()
    total = len(xml_files)

    # 计数器
    note_combos = Counter()       # (type, place, parent_tag, has_n) → count
    note_type_only = Counter()    # type → count
    note_place_only = Counter()   # place → count
    note_parents = Counter()      # parent_tag → count
    app_children = Counter()      # app 内子元素组合
    note_inside_lem = Counter()   # lem 内 note type
    note_inside_app = Counter()   # app 内 note type

    xml_parser = etree.XMLParser(recover=True)

    for i, xml_path in enumerate(xml_files):
        try:
            tree = etree.parse(str(xml_path), xml_parser)
            root = tree.getroot()

            # 扫描所有 <note>
            for note in root.iter(f"{{{TEI_NS}}}note"):
                ntype = note.get("type", "")
                place = note.get("place", "")
                has_n = "yes" if note.get("n") else "no"
                parent = note.getparent()
                ptag = local_tag(parent.tag) if parent is not None else "ROOT"

                note_combos[(ntype, place, ptag, has_n)] += 1
                if ntype:
                    note_type_only[ntype] += 1
                if place:
                    note_place_only[place] += 1
                note_parents[ptag] += 1

                # 特别关注嵌套在 lem 内的 note
                if ptag == "lem":
                    note_inside_lem[ntype or "(empty)"] += 1
                if ptag == "app":
                    note_inside_app[ntype or "(empty)"] += 1

            # 扫描所有 <app> 的子元素结构
            for app in root.iter(f"{{{TEI_NS}}}app"):
                children = tuple(local_tag(c.tag) for c in app)
                app_children[children] += 1

        except Exception:
            pass

    # 写报告
    f = open(REPORT_PATH, 'w', encoding='utf-8')
    f.write(f"CBETA <note> 格式统计报告\n")
    f.write(f"扫描文件数: {total}\n")
    f.write(f"{'='*70}\n\n")

    # 1. note type 分布
    f.write(f"一、note type 分布（共 {sum(note_type_only.values())} 个有 type 的 note）\n")
    f.write(f"{'-'*50}\n")
    for ntype, cnt in note_type_only.most_common():
        f.write(f"  {ntype:20s}  {cnt:>8,d}\n")
    f.write(f"\n")

    # 2. note place 分布
    f.write(f"二、note place 分布\n")
    f.write(f"{'-'*50}\n")
    for place, cnt in note_place_only.most_common():
        f.write(f"  {place:20s}  {cnt:>8,d}\n")
    f.write(f"\n")

    # 3. note 父元素分布
    f.write(f"三、note 父元素分布\n")
    f.write(f"{'-'*50}\n")
    for ptag, cnt in note_parents.most_common():
        f.write(f"  {ptag:20s}  {cnt:>8,d}\n")
    f.write(f"\n")

    # 4. 嵌套在 lem 内的 note type
    f.write(f"四、嵌套在 <lem> 内的 note type\n")
    f.write(f"{'-'*50}\n")
    for ntype, cnt in note_inside_lem.most_common():
        f.write(f"  {ntype:20s}  {cnt:>8,d}\n")
    f.write(f"\n")

    # 5. 嵌套在 <app> 内的 note type
    f.write(f"五、嵌套在 <app> 内的 note type\n")
    f.write(f"{'-'*50}\n")
    for ntype, cnt in note_inside_app.most_common():
        f.write(f"  {ntype:20s}  {cnt:>8,d}\n")
    f.write(f"\n")

    # 6. <app> 子元素结构（前 30 种）
    f.write(f"六、<app> 子元素结构（前 30 种）\n")
    f.write(f"{'-'*50}\n")
    for children, cnt in app_children.most_common(30):
        f.write(f"  {str(children):50s}  {cnt:>8,d}\n")
    f.write(f"\n")

    # 7. 完整组合 (type, place, parent, has_n) — 前 50 种
    f.write(f"七、完整组合 (type, place, parent, has_n)（前 50 种）\n")
    f.write(f"{'-'*70}\n")
    for combo, cnt in note_combos.most_common(50):
        ntype, place, ptag, has_n = combo
        f.write(f"  type={ntype:12s} place={place:15s} parent={ptag:10s} n={has_n:3s}  {cnt:>8,d}\n")

    f.close()
    print(f"Done. {total} files. Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
