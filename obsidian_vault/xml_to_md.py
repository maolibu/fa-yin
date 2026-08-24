"""
CBETA XML → Obsidian Markdown 转换脚本
使用 Bookcase 分卷版 XML（与阅读器共用同一份数据），
将每部经的所有卷合并为一个 Obsidian 友好的 Markdown 文件。

用法：
    python xml_to_md.py --sutra T08n0251         # 转换单部经（心经）
    python xml_to_md.py --canon T --limit 10      # 转换大正藏前 10 部
    python xml_to_md.py --all --limit 50          # 转换全部前 50 部

输出结构：
    output/
    ├── 首頁.md
    ├── 目錄/部類/ + 目錄/經藏/
    ├── 經文/{Canon}/{CanonVol}/{SutraId}_{Title}.md
    └── 筆記/

依赖：
    - 需要 data/raw/cbeta/XML/ 下的分卷 XML 文件（Bookcase 版）
    - 需要 data/raw/cbeta/gaiji-CB/ 下的缺字数据
    - 需要 data/raw/cbeta/bulei_nav.xhtml（部类分类）
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import config
from core.cbeta_ids import (
    discover_bookcase_xml_files,
    filename_matches_xml_id,
    parse_bookcase_id,
    split_sutra_id,
    try_parse_bookcase_id,
)

# Bookcase 分卷版数据（与阅读器共用）
CBETA_BASE = config.CBETA_BASE
XML_BASE = CBETA_BASE / "XML"
GAIJI_JSON = config.GAIJI_PATH
BOOKDATA_TXT = CBETA_BASE / "bookdata.txt"
BULEI_NAV = CBETA_BASE / "bulei_nav.xhtml"
OUTPUT_DIR = config.OBSIDIAN_VAULT_DIR

# XML 命名空间
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", TEI_NS)
ET.register_namespace("cb", CB_NS)

# ============================================================
# Gaiji 映射（内联，不依赖外部模块）
# ============================================================
_gaiji_map = None

def _load_gaiji():
    """加载缺字映射表"""
    global _gaiji_map
    if _gaiji_map is not None:
        return _gaiji_map
    if not GAIJI_JSON.exists():
        print(f"  ⚠️ 找不到 gaiji 映射文件: {GAIJI_JSON}")
        _gaiji_map = {}
        return _gaiji_map
    with open(GAIJI_JSON, "r", encoding="utf-8") as f:
        _gaiji_map = json.load(f)
    return _gaiji_map

def resolve_gaiji(cb_id):
    """将 CB 编号解析为可显示的字符"""
    cb_id = cb_id.lstrip("#")
    gmap = _load_gaiji()
    entry = gmap.get(cb_id)
    if entry is None:
        return f"[{cb_id}]"
    # 优先级：精确 Unicode → 标准化 Unicode → Big5 替代 → 组字式 → CB 编号
    for key in ("uni_char", "norm_uni_char", "norm_big5_char", "composition"):
        if entry.get(key):
            return entry[key]
    return f"[{cb_id}]"

# ============================================================
# 藏经名称映射
# ============================================================
_canons_cache = None

def _load_canons():
    """从当前 Bookcase bookdata.txt 解析藏经代码 → 中文名映射。"""
    global _canons_cache
    if _canons_cache is not None:
        return _canons_cache
    _canons_cache = {}
    if not BOOKDATA_TXT.exists():
        return _canons_cache
    try:
        for line in BOOKDATA_TXT.read_text(
            encoding="utf-16", errors="replace"
        ).splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 4 and parts[0] and parts[3]:
                _canons_cache[parts[0]] = {"title-zh": parts[3]}
    except Exception as e:
        print(f"  ⚠️ 读取 Bookcase bookdata.txt 失败: {e}")
    return _canons_cache

# ============================================================
# 工具函数
# ============================================================
def _local_tag(element):
    """获取元素的本地名（去除命名空间）"""
    tag = element.tag
    if "}" in tag:
        return tag.split("}")[1]
    return tag

def _clean_text(text):
    """清理 XML 格式化产生的多余空白
    
    CBETA XML 中 <lb> 标签后的物理换行只是 XML 格式化，
    不是有意义的段落断行。将换行符替换为空字符串，保留全角空格。
    """
    if not text:
        return text
    # 将换行符和首尾空白清除（XML 中的换行只是格式化）
    return text.replace('\n', '').replace('\r', '')


def _yaml_quote(value):
    """Return a JSON string, which is also a safe YAML double-quoted scalar."""
    return json.dumps(str(value), ensure_ascii=False)

# 跳过标签集
SKIP_TAGS = {
    "rdg", "anchor", "back",
    "charDecl", "teiHeader",
    "docNumber",  # CBETA 编目号（如 No. 251）
}

SELF_CLOSING = {
    "lb", "pb", "milestone", "anchor", "space", "caesura",
}

# 中文数字映射
CN_NUMS = "一二三四五六七八九十"

def juan_to_cn(n):
    """将阿拉伯数字卷号转为中文：1→一, 12→十二, 20→二十"""
    if n <= 0:
        return str(n)
    if n <= 10:
        return CN_NUMS[n - 1]
    if n < 20:
        return f"十{CN_NUMS[n - 11]}"
    if n == 20:
        return "二十"
    if n < 100:
        tens = n // 10
        ones = n % 10
        result = f"{CN_NUMS[tens - 1]}十"
        if ones > 0:
            result += CN_NUMS[ones - 1]
        return result
    return str(n)

# ============================================================
# 纯文本提取（用于元数据和脚注等场景）
# ============================================================
def get_text_recursive(element):
    """递归提取纯文本"""
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        tag = _local_tag(child)
        if tag == "g":
            ref = child.get("ref", "")
            parts.append(resolve_gaiji(ref))
        elif tag == "lem":
            parts.append(get_text_recursive(child))
        elif tag == "app":
            parts.append(get_text_recursive(child))
        elif tag in SKIP_TAGS:
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
# Markdown 提取（核心：将 XML 递归转为 Markdown）
# ============================================================
def _parse_ref_target(target):
    """解析 <ref target="..."> 为 Obsidian wikilink 格式
    
    示例输入：../T30/T30n1579.xml#xpath2(//0279a03)
    输出：T30n1579（经号部分）
    """
    if not target:
        return ""
    file_part = target.split("#", 1)[0].rsplit("/", 1)[-1]
    parsed = try_parse_bookcase_id(file_part)
    return parsed.file_id if parsed else ""


class MarkdownBuilder:
    """带状态的 Markdown 构建器，跟踪脚注和上下文"""

    def __init__(self):
        self.footnotes = []         # 脚注列表 [(id, content)]
        self.footnote_counter = 0
        self.in_verse = False       # 是否在偈颂中
        self.current_lb = ""        # 当前行号（用于 Block ID）
        self.pending_block_id = ""  # 待输出的 Block ID
        self.current_pb = ""        # 当前页码

    def add_footnote(self, content):
        """添加脚注，返回脚注标记"""
        self.footnote_counter += 1
        fn_id = self.footnote_counter
        self.footnotes.append((fn_id, content))
        return f"[^{fn_id}]"

    def get_md_recursive(self, element, depth=0):
        """递归将 XML 元素转换为 Markdown"""
        parts = []
        if element.text:
            parts.append(_clean_text(element.text))

        for child in element:
            tag = _local_tag(child)

            # ---- Gaiji 缺字 ----
            if tag == "g":
                ref = child.get("ref", "")
                parts.append(resolve_gaiji(ref))

            # ---- 行号 → Block ID（用于 Obsidian 段落引用）----
            elif tag == "lb":
                line_id = child.get("n", "")
                if line_id:
                    self.current_lb = line_id
                    self.pending_block_id = line_id

            # ---- 页码（跳过，不输出页码标记）----
            elif tag == "pb":
                pass

            elif tag == "milestone":
                pass

            elif tag == "anchor":
                pass

            # ---- 空格/停顿 ----
            elif tag == "space":
                quantity = child.get("quantity", "1")
                try:
                    n = int(quantity)
                except ValueError:
                    n = 1
                parts.append("　" * n)

            elif tag == "caesura":
                parts.append("　")

            # ---- 校勘 ----
            elif tag == "app":
                # 只取 <lem> 正文，校勘异读不输出
                for app_child in child:
                    ct = _local_tag(app_child)
                    if ct == "lem":
                        parts.append(self.get_md_recursive(app_child, depth + 1))
                        break

            elif tag == "lem":
                parts.append(self.get_md_recursive(child, depth + 1))

            elif tag == "rdg":
                # 单独遇到 rdg 跳过（已在 app 中处理）
                pass

            # ---- 注释 ----
            elif tag == "note":
                place = child.get("place", "")
                content = get_text_recursive(child).strip()
                if place == "inline" and content:
                    # 夹注：括号显示
                    parts.append(f"（{content}）")
                # 其他注释类型（校勘等）不输出

            # ---- 标题 ----
            elif tag == "head":
                head_text = self.get_md_recursive(child, depth + 1).strip()
                if head_text:
                    # mulu 已生成章节标题时，head 可能重复
                    # 检查同一 div 下是否已有 mulu 产生了标题
                    parent = element
                    has_mulu = any(
                        _local_tag(sib) == "mulu"
                        for sib in parent
                        if sib is not child
                    )
                    if not has_mulu:
                        parts.append(f"\n\n### {head_text}\n\n")
                    # 如果有 mulu，head 文字不重复输出

            # ---- 作者 ----
            elif tag == "byline":
                byline_text = self.get_md_recursive(child, depth + 1).strip()
                if byline_text:
                    parts.append(f"\n\n*{byline_text}*\n\n")

            elif tag == "trailer":
                trailer_text = self.get_md_recursive(child, depth + 1).strip()
                if trailer_text:
                    parts.append(f"\n\n---\n*{trailer_text}*\n\n")

            # ---- 段落 ----
            elif tag == "p":
                cb_type = child.get(f"{{{CB_NS}}}type", "")
                p_text = self.get_md_recursive(child, depth + 1).strip()
                if p_text:
                    # 附加 Block ID（段落级，取段落内最后一个行号）
                    block_id_str = ""
                    if self.pending_block_id:
                        block_id_str = f" ^{self.pending_block_id}"
                        self.pending_block_id = ""
                    if cb_type == "dharani":
                        parts.append(f"\n\n> 🔔 {p_text}\n\n")
                    else:
                        parts.append(f"\n\n{p_text}{block_id_str}\n\n")

            # ---- 偈颂 ----
            elif tag == "lg":
                self.in_verse = True
                verse_content = self.get_md_recursive(child, depth + 1)
                self.in_verse = False
                parts.append(f"\n\n{verse_content}\n\n")

            elif tag == "l":
                line_text = self.get_md_recursive(child, depth + 1).strip()
                if line_text:
                    parts.append(f"> {line_text}  \n")

            # ---- 卷标记 ----
            elif tag == "juan":
                fun = child.get("fun", "")
                if fun == "close":
                    # 卷尾标记
                    juan_text = get_text_recursive(child).strip()
                    if juan_text:
                        parts.append(f"\n\n---\n*{juan_text}*\n\n")
                # fun="open" 跳过：卷标题已由 convert_sutra_group 生成

            elif tag == "jhead":
                pass  # 已由 <juan> 生成卷标题，jhead 跳过避免混乱

            # ---- 中外对照术语（cb:tt / cb:t）→ 只取中文 ----
            elif tag == "tt":
                for tt_child in child:
                    if _local_tag(tt_child) == "t":
                        lang = tt_child.get(f"{{{XML_NS}}}lang", "")
                        if "zh" in lang:
                            parts.append(self.get_md_recursive(tt_child, depth + 1))
                            break

            elif tag == "t":
                parts.append(self.get_md_recursive(child, depth + 1))

            # ---- 目录标记 → Markdown 标题 ----
            elif tag == "mulu":
                mulu_type = child.get("type", "")
                level = child.get("level", "1")
                title = get_text_recursive(child).strip() or child.get("n", "")
                if title and mulu_type != "卷":
                    # 卷标记已由 <juan> 处理，避免重复
                    # level 1 → ###, level 2 → ####, level 3 → #####
                    try:
                        md_level = min(int(level) + 2, 6)  # h3 ~ h6
                    except ValueError:
                        md_level = 3
                    heading = "#" * md_level
                    parts.append(f"\n\n{heading} {title}\n\n")

            # ---- div 章节 ----
            elif tag == "div":
                div_content = self.get_md_recursive(child, depth + 1)
                parts.append(div_content)

            # ---- 列表 ----
            elif tag == "list":
                list_content = self.get_md_recursive(child, depth + 1)
                parts.append(f"\n\n{list_content}\n\n")

            elif tag == "item":
                item_text = self.get_md_recursive(child, depth + 1).strip()
                n = child.get("n", "")
                prefix = f"{n}. " if n else "- "
                parts.append(f"{prefix}{item_text}\n")

            # ---- 表格 ----
            elif tag == "table":
                rows = []
                for row_elem in child:
                    if _local_tag(row_elem) == "row":
                        cells = []
                        for cell_elem in row_elem:
                            if _local_tag(cell_elem) == "cell":
                                cells.append(get_text_recursive(cell_elem).strip())
                        rows.append(cells)
                if rows:
                    # 输出 Markdown 表格
                    max_cols = max(len(r) for r in rows)
                    parts.append("\n\n")
                    for i, row in enumerate(rows):
                        # 补齐列数
                        while len(row) < max_cols:
                            row.append("")
                        parts.append("| " + " | ".join(row) + " |\n")
                        if i == 0:
                            parts.append("| " + " | ".join(["---"] * max_cols) + " |\n")
                    parts.append("\n")

            # ---- 引文 ----
            elif tag == "quote":
                quote_text = self.get_md_recursive(child, depth + 1).strip()
                if quote_text:
                    parts.append(f"\n\n> {quote_text}\n\n")

            # ---- 模糊字 ----
            elif tag == "unclear":
                unclear_text = self.get_md_recursive(child, depth + 1)
                parts.append(f"〔{unclear_text}〕")

            # ---- 外语 ----
            elif tag == "foreign":
                parts.append(f"*{self.get_md_recursive(child, depth + 1)}*")

            # ---- 格式化 ----
            elif tag == "hi":
                rend = child.get("rend", "")
                inner = self.get_md_recursive(child, depth + 1)
                if "bold" in rend:
                    parts.append(f"**{inner}**")
                else:
                    parts.append(inner)

            # ---- 交叉引用 → Obsidian wikilink ----
            elif tag == "ref":
                target = child.get("target", "")
                ref_text = self.get_md_recursive(child, depth + 1).strip()
                sutra_ref = _parse_ref_target(target)
                if ref_text and sutra_ref:
                    # 转为 Obsidian wikilink：[[T30n1579|論本卷第一]]
                    parts.append(f"[[{sutra_ref}|{ref_text}]]")
                elif ref_text:
                    parts.append(ref_text)

            # ---- 正则化/校正 ----
            elif tag == "choice":
                parts.append(self.get_md_recursive(child, depth + 1))

            elif tag in ("corr", "reg"):
                parts.append(self.get_md_recursive(child, depth + 1))

            elif tag in ("sic", "orig"):
                pass

            # ---- header/skip ----
            elif tag in SKIP_TAGS:
                pass

            # ---- 所有其余元素：递归提取 ----
            else:
                parts.append(self.get_md_recursive(child, depth + 1))

            if child.tail:
                parts.append(_clean_text(child.tail))

        return "".join(parts)

    def build_footnotes_section(self):
        """生成脚注区域"""
        if not self.footnotes:
            return ""
        lines = ["\n\n---\n"]
        for fn_id, content in self.footnotes:
            lines.append(f"[^{fn_id}]: {content}\n")
        return "\n".join(lines)


# ============================================================
# 元数据提取
# ============================================================
def extract_metadata(tree):
    """从 teiHeader 提取经文元数据"""
    root = tree.getroot()

    xml_id = root.get(f"{{{XML_NS}}}id", "")

    parsed_id = parse_bookcase_id(xml_id)
    canon = parsed_id.canon
    volume = parsed_id.volume
    sutra_id = parsed_id.sutra_id

    # 经名
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

    # 作者
    author = ""
    author_elem = root.find(f".//{{{TEI_NS}}}titleStmt/{{{TEI_NS}}}author")
    if author_elem is not None and author_elem.text:
        author = author_elem.text.strip()

    # 卷数
    total_juan = 1
    extent_elem = root.find(f".//{{{TEI_NS}}}extent")
    if extent_elem is not None and extent_elem.text:
        juan_match = re.search(r"(\d+)", extent_elem.text)
        if juan_match:
            total_juan = int(juan_match.group(1))

    # 藏经名
    canons = _load_canons()
    category = canons.get(canon, {}).get("title-zh", "")

    return {
        "sutra_id": sutra_id,
        "canon": canon,
        "volume": volume,
        "title": title,
        "author": author,
        "total_juan": total_juan,
        "category": category,
        "xml_id": xml_id,
    }


# ============================================================
# 从 Bookcase 分卷 XML 合并为一个 Markdown
# ============================================================
def convert_sutra_group(xml_files, output_base, verbose=True):
    """将同一部经的多个分卷 XML 合并为一个 MD 文件
    
    xml_files: 按卷排序的 XML 文件路径列表
    返回: 元数据 dict 或 None
    """
    if not xml_files:
        return None

    # 1. 从第一个文件提取元数据
    first_file = xml_files[0]
    try:
        tree = ET.parse(str(first_file))
    except ET.ParseError as e:
        print(f"  ❌ XML 解析失败: {first_file} - {e}")
        return None

    meta = extract_metadata(tree)
    if verbose:
        print(f"  📖 {meta['xml_id']} {meta['title']} ({len(xml_files)} 卷)")

    # 2. 逐卷解析并合并 Markdown
    builder = MarkdownBuilder()
    all_parts = []
    back_notes_parts = []
    source_xml_ids = []
    source_volumes = []
    available_juans = set()
    last_heading_juan = None

    for idx, xml_path in enumerate(xml_files):
        juan_num = _parse_juan_from_filename(xml_path)

        try:
            t = ET.parse(str(xml_path))
        except ET.ParseError as exc:
            print(f"  ❌ XML 解析失败: {xml_path} - {exc}")
            return None

        root = t.getroot()
        xml_id = root.get(f"{{{XML_NS}}}id", "")
        filename_id = parse_bookcase_id(xml_path, require_juan=True)
        authoritative_id = parse_bookcase_id(xml_id)
        if not filename_matches_xml_id(filename_id, authoritative_id):
            print(
                f"  ❌ 文件名/XML ID 不一致: {xml_path} "
                f"({filename_id.file_id} != {authoritative_id.file_id})"
            )
            return None
        if authoritative_id.sutra_id != meta["sutra_id"]:
            print(
                f"  ❌ 分组混入其他经号: {xml_path} "
                f"({authoritative_id.sutra_id} != {meta['sutra_id']})"
            )
            return None
        if authoritative_id.file_id not in source_xml_ids:
            source_xml_ids.append(authoritative_id.file_id)
        if authoritative_id.volume not in source_volumes:
            source_volumes.append(authoritative_id.volume)
        available_juans.add(juan_num)

        body = root.find(f".//{{{TEI_NS}}}body")
        if body is None:
            print(f"  ❌ XML 缺少 body: {xml_path}")
            return None

        # 卷标题分隔（多卷经才输出）
        if len(xml_files) > 1 and juan_num != last_heading_juan:
            juan_cn = juan_to_cn(juan_num)
            all_parts.append(f"\n\n## 卷{juan_cn}\n\n")
            last_heading_juan = juan_num

        # 转换正文
        md_text = builder.get_md_recursive(body)
        all_parts.append(md_text)

        # <back> 校勘注不提取（阅读器已保留）

    if not all_parts:
        return None

    # 3. 组装完整 Markdown
    meta["total_juan"] = len(available_juans)
    meta["source_xml_count"] = len(xml_files)
    meta["cbeta_ids"] = source_xml_ids
    meta["volumes"] = source_volumes

    frontmatter_lines = [
        "---",
        f"sutra_id: {_yaml_quote(meta['sutra_id'])}",
        f"title: {_yaml_quote(meta['title'])}",
        f"author: {_yaml_quote(meta['author'])}",
        f"canon: {_yaml_quote(meta['category'])}",
        f"volume: {_yaml_quote(meta['volume'])}",
        "volumes:",
        *[f"  - {_yaml_quote(volume)}" for volume in source_volumes],
        f"total_juan: {meta['total_juan']}",
        f"source_xml_count: {meta['source_xml_count']}",
        f"cbeta_id: {_yaml_quote(source_xml_ids[0])}",
        "cbeta_ids:",
        *[f"  - {_yaml_quote(cbeta_id)}" for cbeta_id in source_xml_ids],
        "aliases:",
        *[f"  - {_yaml_quote(cbeta_id)}" for cbeta_id in source_xml_ids],
        "tags:",
        "  - 佛經",
        f"  - {meta['canon']}藏",
        "---",
        "",
        "",
    ]
    frontmatter = "\n".join(frontmatter_lines)
    header = f"# {meta['title']}\n\n"
    content = "".join(all_parts).strip()
    content = re.sub(r'\n{3,}', '\n\n', content)

    full_md = frontmatter + header + content




    # 4. 写入文件
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', meta['title'])
    sutra_dir = Path(output_base) / "經文" / meta['canon'] / f"{meta['canon']}{meta['volume']}"
    sutra_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{meta['sutra_id']}_{safe_title}.md"
    filepath = sutra_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_md)

    if verbose:
        print(f"     ✅ → {filepath.relative_to(output_base)}")

    # 保存文件名信息，供目录生成时使用
    meta['_link_name'] = f"{meta['sutra_id']}_{safe_title}"

    return meta


def _parse_juan_from_filename(xml_path):
    """从 Bookcase 文件名解析卷号：T01n0001_003.xml → 3"""
    parsed = parse_bookcase_id(xml_path, require_juan=True)
    assert parsed.juan is not None
    return parsed.juan


# ============================================================
# 部类分类（从 bulei_nav.xhtml 解析）
# ============================================================
_bulei_map = None

def _load_bulei_map():
    """解析 bulei_nav.xhtml，建立 经号→部类 映射"""
    global _bulei_map
    if _bulei_map is not None:
        return _bulei_map

    _bulei_map = {}
    if not BULEI_NAV.exists():
        print(f"  ⚠️ 找不到 bulei_nav: {BULEI_NAV}，使用默认分类")
        return _bulei_map

    with open(BULEI_NAV, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取部类名称（<span> 标签中的顶层分类）
    # 格式: <span>01 阿含部類 T01-02,25,33 etc.</span>
    current_category = "其他"
    for line in content.split('\n'):
        # 匹配部类标题
        cat_match = re.search(r'<span>\d+\s+(.+?)\s+[A-Z]', line)
        if cat_match:
            current_category = cat_match.group(1).strip()

        # 匹配经文条目
        # <cblink href="XML/T/T01/T01n0001_001.xml">T0001 長阿含經</cblink>
        entry_match = re.search(r'<cblink[^>]*>([A-Za-z0-9]+)\s', line)
        if entry_match and '<cblink' in line:
            sutra_id = entry_match.group(1)
            _bulei_map[sutra_id] = current_category

    return _bulei_map


def get_category(meta):
    """获取经文的部类分类"""
    bulei = _load_bulei_map()
    # 尝试匹配 sutra_id
    cat = bulei.get(meta.get('sutra_id', ''))
    if cat:
        return cat
    # 回退：用藏经名
    canons = _load_canons()
    name = canons.get(meta.get('canon', ''), {}).get("title-zh", "")
    return name if name else (meta.get('canon', '') or "其他")


# ============================================================
# 生成 Vault 结构（目录、首页、笔记文件夹）
# ============================================================
def generate_vault_structure(output_base, all_meta):
    """在转换完成后生成 Vault 的索引结构"""
    output_base = Path(output_base)
    canons_data = _load_canons()

    print("\n📂 生成 Vault 结构...")

    # --- 目录/經藏/ ---
    canon_dir = output_base / "目錄" / "經藏"
    canon_dir.mkdir(parents=True, exist_ok=True)

    by_canon = {}
    for m in all_meta:
        code = m['canon']
        if code not in by_canon:
            by_canon[code] = []
        by_canon[code].append(m)

    for code in sorted(by_canon.keys()):
        sutras = by_canon[code]
        canon_name = canons_data.get(code, {}).get("short-title-zh", "") or code
        canon_full = canons_data.get(code, {}).get("title-zh", code)

        lines = [f"---\ntype: moc\ntags: [經藏目錄]\n---\n\n"]
        lines.append(f"# {canon_full}\n\n")
        lines.append(f"經數：{len(sutras)} 部\n\n")

        by_vol = {}
        for m in sutras:
            v = m.get('volume', '??')
            if v not in by_vol:
                by_vol[v] = []
            by_vol[v].append(m)

        for vol in sorted(by_vol.keys()):
            lines.append(f"### 第 {vol} 冊\n\n")
            for m in by_vol[vol]:
                author = f" — {m['author']}" if m['author'] else ""
                link = m.get('_link_name', m['title'])
                lines.append(f"- [[{link}|{m['sutra_id']} {m['title']}]]{author}\n")
            lines.append("\n")

        filepath = canon_dir / f"{canon_name}.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        print(f"  📚 經藏: {canon_name} ({len(sutras)} 部)")

    # --- 目录/部類/ ---
    cat_dir = output_base / "目錄" / "部類"
    cat_dir.mkdir(parents=True, exist_ok=True)

    by_cat = {}
    for m in all_meta:
        cat = get_category(m)
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(m)

    for cat_name in sorted(by_cat.keys()):
        sutras = by_cat[cat_name]
        lines = [f"---\ntype: moc\ntags: [部類目錄]\n---\n\n"]
        lines.append(f"# {cat_name}\n\n")
        lines.append(f"經數：{len(sutras)} 部\n\n")

        for m in sutras:
            author = f" — {m['author']}" if m['author'] else ""
            link = m.get('_link_name', m['title'])
            lines.append(f"- [[{link}|{m['sutra_id']} {m['title']}]]{author}\n")

        filepath = cat_dir / f"{cat_name}.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        print(f"  📖 部類: {cat_name} ({len(sutras)} 部)")

    # --- 首頁.md ---
    homepage = ["---\ntype: homepage\n---\n\n"]
    homepage.append("# 📛 法印對照 CBETA 佛經 Vault\n\n")
    homepage.append(f"共計 {len(all_meta)} 部經典\n\n")

    homepage.append("## 部類索引\n\n")
    for cat_name in sorted(by_cat.keys()):
        count = len(by_cat[cat_name])
        homepage.append(f"- [[{cat_name}]]  ({count} 部)\n")

    homepage.append("\n## 經藏索引\n\n")
    for code in sorted(by_canon.keys()):
        canon_name = canons_data.get(code, {}).get("short-title-zh", "") or code
        count = len(by_canon[code])
        homepage.append(f"- [[{canon_name}]]  ({count} 部)\n")

    homepage.append("\n## 📝 筆記\n\n")
    homepage.append("在 `筆記/` 文件夾中創建讀經筆記，使用 Block ID 精確引用經文。\n")

    with open(output_base / "首頁.md", "w", encoding="utf-8") as f:
        f.write("".join(homepage))
    print("  🏠 首頁.md")

    # --- 筆記/ ---
    notes_dir = output_base / "筆記"
    notes_dir.mkdir(parents=True, exist_ok=True)
    readme = "---\ntype: folder-note\n---\n\n# 📝 讀經筆記\n\n在此文件夾中創建筆記。\n\n## 建議\n\n- 使用 `![[經名#^0848c07]]` 嵌入經文\n- 使用 `> [!note] 眉批` 做段落批注\n- 標籤：`#讀經` `#心得` `#疑商`\n"
    with open(notes_dir / "讀經筆記.md", "w", encoding="utf-8") as f:
        f.write(readme)
    print("  📝 筆記/讀經筆記.md")


# ============================================================
# 文件发现与分组
# ============================================================
def find_sutra_groups(canon=None):
    """扫描 Bookcase XML 文件，按经号分组
    
    返回: [(sutra_key, [xml_file_paths_sorted_by_juan])]
    sutra_key = 如 "T0001"（用于排序和去重）
    """
    all_paths = discover_bookcase_xml_files(XML_BASE)
    if canon:
        all_paths = [
            path for path in all_paths
            if parse_bookcase_id(path, require_juan=True).canon == canon
        ]

    # 以 XML 权威经号分组；同一部经跨册时仍只生成一个 Markdown。
    groups = {}
    for path in all_paths:
        filename_id = parse_bookcase_id(path, require_juan=True)
        _event, root = next(ET.iterparse(path, events=("start",)))
        xml_id = root.get(f"{{{XML_NS}}}id", "")
        authoritative_id = parse_bookcase_id(xml_id)
        if not filename_matches_xml_id(filename_id, authoritative_id):
            raise ValueError(
                f"Bookcase filename/XML ID mismatch: {path}: "
                f"{filename_id.file_id} != {authoritative_id.file_id}"
            )
        sutra_key = authoritative_id.sutra_id
        if sutra_key not in groups:
            groups[sutra_key] = []
        groups[sutra_key].append(str(path))

    # 每组内按文件名排序（确保卷次顺序）
    result = []
    for key in sorted(groups.keys()):
        result.append((key, sorted(groups[key], key=_sutra_file_sort_key)))

    return result


def _sutra_file_sort_key(xml_path):
    parsed = parse_bookcase_id(xml_path, require_juan=True)
    assert parsed.juan is not None
    return parsed.juan, parsed.file_id, str(xml_path)


# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="CBETA Bookcase XML → Obsidian Markdown 转换器（一经一文件）"
    )
    parser.add_argument(
        "--sutra", type=str, help="转换单部经，如 T0251 或 T08n0251"
    )
    parser.add_argument("--canon", type=str, help="转换整个藏经，如 T, X, J")
    parser.add_argument("--all", action="store_true", help="转换全部")
    parser.add_argument("--limit", type=int, default=0, help="限制转换数量")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR), help="输出目录")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("CBETA Bookcase XML → Obsidian Markdown（一经一文件）")
    print("=" * 60)
    print(f"XML 来源: {XML_BASE}")
    print(f"输出目录: {output_dir}")
    print()

    start_time = time.time()
    success_count = 0
    fail_count = 0
    all_meta = []

    if args.sutra:
        groups = dict(find_sutra_groups())
        try:
            requested_id = parse_bookcase_id(args.sutra).sutra_id
        except ValueError:
            canon_codes = {
                path.name for path in XML_BASE.iterdir() if path.is_dir()
            }
            try:
                canon, work = split_sutra_id(args.sutra, canon_codes)
                requested_id = f"{canon}{work}"
            except ValueError:
                print(f"❌ 无法解析经号: {args.sutra}")
                sys.exit(1)
        xml_files = groups.get(requested_id, [])

        if not xml_files:
            print(f"❌ 找不到文件: {args.sutra}")
            sys.exit(1)

        result = convert_sutra_group(xml_files, output_dir)
        if result:
            all_meta.append(result)
            success_count += 1
        else:
            fail_count += 1

    elif args.canon or args.all:
        canon = args.canon if args.canon else None
        groups = find_sutra_groups(canon)
        total = len(groups)
        if args.limit > 0:
            groups = groups[:args.limit]
        print(f"找到 {total} 部经，将转换 {len(groups)} 部\n")
        source_count = sum(len(xml_files) for _, xml_files in groups)
        print(f"源 XML: {source_count} 个\n")

        for i, (sutra_key, xml_files) in enumerate(groups, 1):
            print(f"[{i}/{len(groups)}]")
            result = convert_sutra_group(xml_files, output_dir)
            if result:
                all_meta.append(result)
                success_count += 1
            else:
                fail_count += 1

    else:
        parser.print_help()
        return 2

    # 生成 Vault 结构
    if all_meta:
        generate_vault_structure(output_dir, all_meta)

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"转换完成！")
    print(f"  ✅ 成功: {success_count}")
    print(f"  ❌ 失败: {fail_count}")
    print(f"  ⏱️  耗时: {elapsed:.1f} 秒")
    print(f"  📂 输出: {output_dir}")
    print("=" * 60)
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
