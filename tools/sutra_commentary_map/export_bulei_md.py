#!/usr/bin/env python3
"""
导出 bulei_nav.xhtml 部类目录为 Markdown 文件

功能：
  1. 解析 bulei_nav.xhtml，提取层次结构
  2. 导出为缩进式 Markdown（只含经名、经号和层次）
  3. 校验解析结果：统计各层级节点数量，检查经号格式

用法：
  ~/miniforge3/envs/fjlsc/bin/python export_bulei_md.py

输出：
  bulei_catalog.md  — 部类目录（Markdown 格式）
"""

import re
import os
from pathlib import Path

import lxml.etree as ET

# ============================================================
# 路径配置
# ============================================================
_DIR = Path(__file__).resolve().parent
BULEI_NAV_FILE = _DIR / ".." / ".." / "data" / "raw" / "cbeta" / "bulei_nav.xhtml"
OUTPUT_MD = _DIR / "bulei_catalog.md"


# ============================================================
# 解析函数（与 cbeta_nav.py 一致的逻辑）
# ============================================================
def extract_sutra_id(text: str) -> str | None:
    """
    从 cblink 文本中提取经号。
    支持：T0001、Ba001、JA042、GA0026、T0150A 等
    """
    m = re.match(r"^([A-Z]+[a-zA-Z]*\d+[a-zA-Z]*)\b", text)
    return m.group(1) if m else None


def extract_sutra_title(text: str) -> str:
    """
    从 cblink 文本中提取经名（去掉前面的经号）。
    'T0001 長阿含經' → '長阿含經'
    """
    m = re.match(r"^[A-Z]+[a-zA-Z]*\d+[a-zA-Z]*\s+(.+)", text)
    return m.group(1).strip() if m else text.strip()


def parse_bulei_nav(file_path: Path) -> list[dict]:
    """
    解析 bulei_nav.xhtml 为树形结构。
    返回: [{title, sutra_id, children: [...]}]

    逻辑与 cbeta_nav.py 的 _parse_nav_xhtml 一致。
    """
    content = file_path.read_text(encoding="utf-8")
    parser = ET.XMLParser(recover=True)
    root = ET.fromstring(content.encode("utf-8"), parser=parser)

    navs = root.xpath("//*[local-name()='nav']")
    if not navs:
        print("错误: 未找到 <nav> 元素")
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

        # 递归处理子 <ol>
        for ol in li_elem.findall("ol"):
            for li in ol.findall("li"):
                child = parse_li(li)
                if child:
                    node["children"].append(child)

        return node

    # 处理 <nav> 的直接子元素
    children = list(nav)
    current_section = None
    for child in children:
        tag = child.tag if isinstance(child.tag, str) else ""
        local_tag = tag.split("}")[-1] if "}" in tag else tag

        if local_tag == "span":
            current_section = {
                "title": get_text(child),
                "sutra_id": None,
                "children": [],
            }
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
# 导出 + 校验
# ============================================================
def export_to_md(tree: list[dict], output_path: Path):
    """将树形结构导出为 Markdown"""
    lines = []
    lines.append("# CBETA 部类目录\n")
    lines.append(f"> 数据来源: `bulei_nav.xhtml`\n\n")

    # 统计信息
    stats = {"total_nodes": 0, "leaf_nodes": 0, "category_nodes": 0, "max_depth": 0}
    # 按层级统计
    depth_counts = {}
    # 收集所有经号用于校验
    all_sutra_ids = []
    # 校验问题
    issues = []

    def write_node(node: dict, depth: int):
        stats["total_nodes"] += 1
        stats["max_depth"] = max(stats["max_depth"], depth)
        depth_counts[depth] = depth_counts.get(depth, 0) + 1

        indent = "  " * depth
        is_leaf = len(node["children"]) == 0
        sutra_id = node["sutra_id"]
        title = node["title"]

        if is_leaf and sutra_id:
            # 叶子节点（具体经文）
            stats["leaf_nodes"] += 1
            all_sutra_ids.append(sutra_id)
            sutra_title = extract_sutra_title(title)
            lines.append(f"{indent}- `{sutra_id}` {sutra_title}")
        else:
            # 分类节点
            stats["category_nodes"] += 1
            if depth == 0:
                lines.append(f"\n## {title}\n")
            elif depth == 1:
                lines.append(f"\n{indent}### {title}\n")
            else:
                lines.append(f"{indent}- **{title}**")

            # 校验：分类节点不应该有经号
            if sutra_id and not is_leaf:
                issues.append(f"分类节点却有经号: {sutra_id} ({title})")

        for child in node["children"]:
            write_node(child, depth + 1)

    for node in tree:
        write_node(node, 0)

    # 校验经号格式
    id_pattern = re.compile(r"^[A-Z]+[a-zA-Z]*\d+[a-zA-Z]*$")
    bad_ids = [sid for sid in all_sutra_ids if not id_pattern.match(sid)]
    if bad_ids:
        issues.append(f"格式异常的经号 ({len(bad_ids)} 个): {bad_ids[:10]}")

    # 检查重复经号
    seen = {}
    for sid in all_sutra_ids:
        seen[sid] = seen.get(sid, 0) + 1
    duplicates = {sid: cnt for sid, cnt in seen.items() if cnt > 1}
    if duplicates:
        issues.append(f"重复出现的经号 ({len(duplicates)} 个): "
                       f"{dict(list(duplicates.items())[:10])}")

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    return stats, depth_counts, all_sutra_ids, issues


def main():
    print("=" * 60)
    print("导出 bulei_nav.xhtml 部类目录")
    print("=" * 60)

    if not BULEI_NAV_FILE.exists():
        print(f"错误: 文件不存在: {BULEI_NAV_FILE}")
        return

    # 步骤 1: 解析
    print(f"\n[1/3] 解析 {BULEI_NAV_FILE.name} ...")
    tree = parse_bulei_nav(BULEI_NAV_FILE)
    print(f"  顶级节点数: {len(tree)}")

    if not tree:
        print("错误: 解析结果为空")
        return

    # 步骤 2: 导出
    print(f"\n[2/3] 导出 Markdown → {OUTPUT_MD.name} ...")
    stats, depth_counts, all_ids, issues = export_to_md(tree, OUTPUT_MD)

    # 步骤 3: 校验报告
    print(f"\n[3/3] 校验报告")
    print(f"  总节点数:   {stats['total_nodes']}")
    print(f"  分类节点:   {stats['category_nodes']}")
    print(f"  叶子节点（经文）: {stats['leaf_nodes']}")
    print(f"  最大嵌套深度: {stats['max_depth']}")
    print(f"  层级分布:")
    for depth in sorted(depth_counts.keys()):
        label = ["部类", "子分类", "子子分类", "条目"][min(depth, 3)]
        print(f"    第 {depth} 层 ({label}): {depth_counts[depth]} 个")

    # 经号前缀统计（检查 canon 覆盖度）
    canon_counts = {}
    for sid in all_ids:
        m = re.match(r"^([A-Z]+)", sid)
        if m:
            canon = m.group(1)
            canon_counts[canon] = canon_counts.get(canon, 0) + 1
    print(f"\n  各藏经经文数量:")
    for canon in sorted(canon_counts.keys()):
        print(f"    {canon}: {canon_counts[canon]} 部")

    if issues:
        print(f"\n  ⚠️ 发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print(f"\n  ✅ 未发现问题，解析逻辑正确")

    print(f"\n输出文件: {OUTPUT_MD}")
    print("=" * 60)


if __name__ == "__main__":
    main()
