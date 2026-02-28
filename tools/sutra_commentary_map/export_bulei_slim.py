#!/usr/bin/env python3
"""
导出 bulei_nav.xhtml 精简版 — 只保留经-疏钞对应关系

原始目录中 6000+ 节点大部分是纯经文列表，与经疏映射无关。
关键信息集中在目录名含「／」的节点，例如：
  T0262-65 法華經／疏 T33-34, X27-35
  └── 表示法华经（T0262-65）的注疏在 T33-34 和 X27-35 中

本脚本筛选逻辑：
  1. 只保留含「／」的分类节点及其上下文（父级部类 + 子经文列表）
  2. 删除纯经文列表（如「長阿含經單本」下的几十部经，没有经疏关系）
  3. 输出缩进式 Markdown，清晰展示经→疏的层次

用法：
  ~/miniforge3/envs/fjlsc/bin/python export_bulei_slim.py
"""

import re
from pathlib import Path

import lxml.etree as ET

# ============================================================
# 路径配置
# ============================================================
_DIR = Path(__file__).resolve().parent
BULEI_NAV_FILE = _DIR / ".." / ".." / "data" / "raw" / "cbeta" / "bulei_nav.xhtml"
OUTPUT_MD = _DIR / "bulei_catalog_slim.md"


# ============================================================
# 解析函数
# ============================================================
def extract_sutra_id(text: str) -> str | None:
    """从 cblink 文本中提取经号"""
    m = re.match(r"^([A-Z]+[a-zA-Z]*\d+[a-zA-Z]*)\b", text)
    return m.group(1) if m else None


def extract_sutra_title(text: str) -> str:
    """从 cblink 文本中提取经名"""
    m = re.match(r"^[A-Z]+[a-zA-Z]*\d+[a-zA-Z]*\s+(.+)", text)
    return m.group(1).strip() if m else text.strip()


def parse_bulei_nav(file_path: Path) -> list[dict]:
    """解析 bulei_nav.xhtml 为树形结构（与 cbeta_nav.py 一致）"""
    content = file_path.read_text(encoding="utf-8")
    parser = ET.XMLParser(recover=True)
    root = ET.fromstring(content.encode("utf-8"), parser=parser)

    navs = root.xpath("//*[local-name()='nav']")
    if not navs:
        return []

    nav = navs[0]
    result = []

    def get_text(elem) -> str:
        return "".join(elem.itertext()).strip()

    def parse_li(li_elem) -> dict | None:
        cblink = li_elem.find("cblink")
        span = li_elem.find("span")
        node = {"title": "", "sutra_id": None, "children": []}

        if cblink is not None:
            text = get_text(cblink)
            node["title"] = text
            node["sutra_id"] = extract_sutra_id(text)
        elif span is not None:
            node["title"] = get_text(span)
        else:
            text = get_text(li_elem)
            if not text:
                return None
            node["title"] = text
            node["sutra_id"] = extract_sutra_id(text)

        for ol in li_elem.findall("ol"):
            for li in ol.findall("li"):
                child = parse_li(li)
                if child:
                    node["children"].append(child)
        return node

    children = list(nav)
    current_section = None
    for child in children:
        tag = child.tag if isinstance(child.tag, str) else ""
        local_tag = tag.split("}")[-1] if "}" in tag else tag

        if local_tag == "span":
            current_section = {"title": get_text(child), "sutra_id": None, "children": []}
            result.append(current_section)
        elif local_tag == "ol":
            parent = current_section if current_section else None
            for li in child.findall("li"):
                node = parse_li(li)
                if node:
                    if parent:
                        parent["children"].append(node)
                    else:
                        result.append(node)
        elif local_tag == "li":
            node = parse_li(child)
            if node:
                result.append(node)

    return result


# ============================================================
# 筛选：只保留含「／」的经疏对应节点
# ============================================================
def has_slash_descendant(node: dict) -> bool:
    """检查节点或其后代中是否有含「／」的标题"""
    if "／" in node["title"]:
        return True
    return any(has_slash_descendant(c) for c in node["children"])


def filter_tree(tree: list[dict]) -> list[dict]:
    """过滤树，只保留含「／」关系的分支"""
    filtered = []
    for node in tree:
        if has_slash_descendant(node):
            new_node = {
                "title": node["title"],
                "sutra_id": node["sutra_id"],
                "children": filter_tree(node["children"]) if node["children"] else [],
            }
            # 如果当前节点含「／」，保留所有子经文（它们就是具体的经和疏）
            if "／" in node["title"]:
                new_node["children"] = node["children"]
            filtered.append(new_node)
    return filtered


# ============================================================
# 导出精简版 Markdown
# ============================================================
def export_slim_md(tree: list[dict], output_path: Path):
    """导出精简版 Markdown"""
    lines = []
    lines.append("# CBETA 部类目录（精简版 — 经疏对应）\n")
    lines.append("> 只保留含「／」的经-疏钞对应目录，删除纯经文列表\n")
    lines.append(f"> 数据来源: `bulei_nav.xhtml`\n\n")

    stats = {"slash_groups": 0, "sutras": 0, "commentaries": 0}

    def write_node(node: dict, depth: int):
        title = node["title"]
        sutra_id = node["sutra_id"]
        is_leaf = len(node["children"]) == 0

        if is_leaf and sutra_id:
            # 叶子节点（具体经文/注疏）
            sutra_title = extract_sutra_title(title)
            lines.append(f"{'  ' * depth}- `{sutra_id}` {sutra_title}")
        elif "／" in title:
            # 含「／」的经疏对应目录 — 关键节点
            stats["slash_groups"] += 1
            # 拆分「／」前后来高亮
            parts = title.split("／")
            formatted = " **／** ".join(parts)
            lines.append(f"{'  ' * depth}- 📖 {formatted}")

            for child in node["children"]:
                write_node(child, depth + 1)
        else:
            # 中间分类节点
            if depth == 0:
                lines.append(f"\n## {title}\n")
            elif depth == 1:
                lines.append(f"\n{'  ' * depth}### {title}\n")
            else:
                lines.append(f"{'  ' * depth}- **{title}**")

            for child in node["children"]:
                write_node(child, depth + 1)

    for node in tree:
        write_node(node, 0)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    return stats


def main():
    print("=" * 60)
    print("导出精简版部类目录（经疏对应）")
    print("=" * 60)

    if not BULEI_NAV_FILE.exists():
        print(f"错误: 文件不存在: {BULEI_NAV_FILE}")
        return

    # 步骤 1: 解析
    print(f"\n[1/3] 解析 {BULEI_NAV_FILE.name} ...")
    tree = parse_bulei_nav(BULEI_NAV_FILE)

    # 统计原始数据
    def count_nodes(nodes):
        total = 0
        for n in nodes:
            total += 1 + count_nodes(n["children"])
        return total
    original_count = count_nodes(tree)
    print(f"  原始节点: {original_count}")

    # 步骤 2: 过滤
    print(f"\n[2/3] 筛选含「／」的经疏对应分支 ...")
    slim_tree = filter_tree(tree)
    slim_count = count_nodes(slim_tree)
    print(f"  精简后节点: {slim_count}")
    print(f"  删除比例: {(1 - slim_count / original_count) * 100:.1f}%")

    # 步骤 3: 导出
    print(f"\n[3/3] 导出 → {OUTPUT_MD.name}")
    stats = export_slim_md(slim_tree, OUTPUT_MD)
    print(f"  经疏对应目录数: {stats['slash_groups']}")

    print(f"\n输出文件: {OUTPUT_MD}")
    print("=" * 60)


if __name__ == "__main__":
    main()
