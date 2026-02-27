"""
CBETA 导航数据解析模块 — 零数据库方案

直接读取 CBETA Bookcase 原始文件，在启动时解析到内存：
  - advance_nav.xhtml → 经藏目录树 + 经文元数据（经号、经名）【主数据源】
  - bulei_nav.xhtml   → 部类目录树（阿含部、般若部等）
  - catalog.txt       → 补充作者、部类信息
  - bookdata.txt      → 藏经代码→名称映射
  - toc/              → 品章目录 + 卷索引（按需加载）
"""

import re
import logging
from pathlib import Path

import lxml.etree as ET

log = logging.getLogger(__name__)


class CBETANav:
    """
    CBETA Bookcase 导航数据管理器。
    启动时解析 xhtml 导航文件构建目录树和经文索引。
    """

    # 大般若经子编号 → (全局起始卷偏移, 本部分卷数)
    # CBETA 将 T0220 拆分为 a~o 共 15 个子编号，但 toc/XML 只用 T0220
    _SUB_SUTRA_MAP = {
        'T0220a': (0, 200),      # 卷1-200
        'T0220b': (200, 200),    # 卷201-400
        'T0220c': (400, 137),    # 卷401-537
        'T0220d': (537, 28),     # 卷538-565
        'T0220e': (565, 8),      # 卷566-573
        'T0220f': (573, 2),      # 卷574-575
        'T0220g': (575, 1),      # 卷576
        'T0220h': (576, 1),      # 卷577
        'T0220i': (577, 1),      # 卷578
        'T0220j': (578, 5),      # 卷579-583
        'T0220k': (583, 5),      # 卷584-588
        'T0220l': (588, 1),      # 卷589
        'T0220m': (589, 1),      # 卷590
        'T0220n': (590, 2),      # 卷591-592
        'T0220o': (592, 8),      # 卷593-600
    }

    def __init__(self, cbeta_dir: str | Path):
        self.cbeta_dir = Path(cbeta_dir)
        self.xml_dir = self.cbeta_dir / "XML"
        self.toc_dir = self.cbeta_dir / "toc"

        # 内存数据
        self.catalog: dict[str, dict] = {}      # {sutra_id: {title, author, juan_count, ...}}
        self.canon_names: dict[str, str] = {}   # {canon_code: canon_name_zh}
        self.canon_tree: list[dict] = []        # 经藏目录树
        self.bulei_tree: list[dict] = []        # 部类目录树

        # 1. 加载藏经名称
        self._load_bookdata()

        # 2. 解析 xhtml 导航文件 → 目录树 + 经文索引（主数据源）
        self._load_canon_tree()
        self._load_bulei_tree()

        # 3. 从 xhtml 树中提取所有经文元数据到 catalog
        self._build_catalog_from_trees()

        # 4. 从 catalog.txt 补充作者和部类（可选）
        self._supplement_from_catalog_txt()

        log.info(f"CBETANav 初始化完成: {len(self.catalog)} 个经文, "
                 f"{len(self.canon_tree)} 个经藏, {len(self.bulei_tree)} 个部类")

    # ================================================================
    # 公开接口
    # ================================================================

    def get_sutra_info(self, sutra_id: str) -> dict | None:
        """查询经文元数据"""
        info = self.catalog.get(sutra_id)
        if info:
            return info
        # 子编号回退：T0220a → T0220
        base = self._strip_sub_letter(sutra_id)
        if base:
            return self.catalog.get(base)
        return None

    def get_total_juan(self, sutra_id: str) -> int:
        """查询经文总卷数（按需从 toc 加载）"""
        info = self.catalog.get(sutra_id)
        if not info:
            # 子编号映射表快速查找（如 T0220a → 200 卷）
            sub = self._SUB_SUTRA_MAP.get(sutra_id)
            if sub:
                return sub[1]
            return 1
        if info["juan_count"] == 0:
            # 子编号映射表优先
            sub = self._SUB_SUTRA_MAP.get(sutra_id)
            if sub:
                info["juan_count"] = sub[1]
            else:
                # 按需加载卷数
                canon = info.get("canon") or self._guess_canon(sutra_id)
                count = self._get_juan_count_from_toc(sutra_id, canon)
                # 子编号回退（如 T0220a → T0220）
                if count <= 1:
                    base_id = self._strip_sub_letter(sutra_id)
                    if base_id:
                        count2 = self._get_juan_count_from_toc(base_id, canon)
                        if count2 > count:
                            count = count2
                info["juan_count"] = count
        return info["juan_count"]

    def get_sutra_title(self, sutra_id: str) -> str:
        """查询经名"""
        info = self.catalog.get(sutra_id)
        if info:
            return info.get("title", sutra_id)
        # 子编号回退：T0220a → T0220
        base = self._strip_sub_letter(sutra_id)
        if base:
            base_info = self.catalog.get(base)
            if base_info:
                return base_info.get("title", sutra_id)
        return sutra_id

    @staticmethod
    def _strip_sub_letter(sutra_id: str) -> str | None:
        """
        去掉子编号后缀，如 T0220a → T0220。
        CBETA 大般若经等大经被拆成 T0220a~T0220o，但 toc/XML 文件只用 T0220。
        仅当末尾是小写字母且前面是数字时才剥离。
        """
        if sutra_id and sutra_id[-1].islower() and len(sutra_id) > 2 and sutra_id[-2].isdigit():
            return sutra_id[:-1]
        return None

    def resolve_scroll_path(self, sutra_id: str, juan: int) -> Path | None:
        """
        根据经号和卷号定位 XML 文件路径。
        优先 toc 精确查找，回退到目录扫描。
        对 T0220a 等子编号，先将 local_juan 偏移为全局卷号，
        再用基础编号 T0220 查找。
        """
        # 子编号偏移处理：T0220a 的第 1 卷 → 全局第 1 卷，T0220b 的第 1 卷 → 全局第 201 卷
        sub = self._SUB_SUTRA_MAP.get(sutra_id)
        if sub:
            offset, total = sub
            global_juan = offset + juan
            base_id = self._strip_sub_letter(sutra_id)
            if base_id:
                path = self._resolve_from_toc(base_id, global_juan)
                if path and path.exists():
                    return path
                path = self._resolve_by_scan(base_id, global_juan)
                if path and path.exists():
                    return path
            # 如果偏移后找不到，不再回退，直接返回 None
            return None

        # 方法1: 从 toc 文件查找精确路径
        path = self._resolve_from_toc(sutra_id, juan)
        if path and path.exists():
            return path

        # 方法2: 目录扫描回退
        path = self._resolve_by_scan(sutra_id, juan)
        if path and path.exists():
            return path

        # 方法3: 子编号回退 — 去掉末尾字母重试（如 T0220a → T0220）
        base_id = self._strip_sub_letter(sutra_id)
        if base_id:
            path = self._resolve_from_toc(base_id, juan)
            if path and path.exists():
                return path
            path = self._resolve_by_scan(base_id, juan)
            if path and path.exists():
                return path

        return None

    def get_canon_tree(self) -> list[dict]:
        """返回经藏目录树"""
        return self.canon_tree

    def get_bulei_tree(self) -> list[dict]:
        """返回部类目录树"""
        return self.bulei_tree

    # ================================================================
    # 加载 bookdata.txt → 藏经代码映射
    # ================================================================

    def _load_bookdata(self):
        """解析 bookdata.txt"""
        path = self.cbeta_dir / "bookdata.txt"
        if not path.exists():
            log.warning(f"bookdata.txt 不存在: {path}")
            return

        for line in path.read_text(encoding="utf-16", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) >= 4:
                code = parts[0].strip()
                full_name = parts[3].strip()
                if code and full_name:
                    self.canon_names[code] = full_name

        log.info(f"  bookdata.txt: {len(self.canon_names)} 个藏经代码")

    # ================================================================
    # 解析 xhtml 导航文件 → 目录树
    # ================================================================

    def _load_canon_tree(self):
        """解析 advance_nav.xhtml 为经藏目录树"""
        path = self.cbeta_dir / "advance_nav.xhtml"
        if not path.exists():
            log.warning(f"advance_nav.xhtml 不存在: {path}")
            return
        self.canon_tree = self._parse_nav_xhtml(path)
        log.info(f"  advance_nav.xhtml: {len(self.canon_tree)} 个顶级节点")

    def _load_bulei_tree(self):
        """解析 bulei_nav.xhtml 为部类目录树"""
        path = self.cbeta_dir / "bulei_nav.xhtml"
        if not path.exists():
            log.warning(f"bulei_nav.xhtml 不存在: {path}")
            return
        self.bulei_tree = self._parse_nav_xhtml(path)
        log.info(f"  bulei_nav.xhtml: {len(self.bulei_tree)} 个顶级节点")

    @staticmethod
    def _extract_sutra_id(text: str) -> str | None:
        """
        从 cblink 文本中提取经号。
        支持：T0001、Ba001、JA042、GA0026、T0150A 等
        """
        m = re.match(r"^([A-Z]+[a-zA-Z]*\d+[a-zA-Z]*)\b", text)
        return m.group(1) if m else None

    @staticmethod
    def _extract_sutra_title(text: str) -> str:
        """
        从 cblink 文本中提取经名（去掉前面的经号）。
        'T0001 長阿含經' → '長阿含經'
        """
        m = re.match(r"^[A-Z]+[a-zA-Z]*\d+[a-zA-Z]*\s+(.+)", text)
        return m.group(1).strip() if m else text.strip()

    def _parse_nav_xhtml(self, file_path: Path) -> list[dict]:
        """
        解析 xhtml 导航文件为树形结构。
        返回: [{title, sutra_id, href, children: [...]}]
        """
        content = file_path.read_text(encoding="utf-8")
        parser = ET.XMLParser(recover=True)
        root = ET.fromstring(content.encode("utf-8"), parser=parser)

        navs = root.xpath("//*[local-name()='nav']")
        if not navs:
            log.error(f"未找到 <nav> 元素: {file_path}")
            return []

        nav = navs[0]
        result = []

        def get_text(elem) -> str:
            return "".join(elem.itertext()).strip()

        def parse_li(li_elem) -> dict | None:
            cblink = li_elem.find("cblink")
            span = li_elem.find("span")

            node = {"title": "", "sutra_id": None, "href": None, "children": []}

            if cblink is not None:
                text = get_text(cblink)
                node["title"] = text
                node["sutra_id"] = self._extract_sutra_id(text)
                node["href"] = cblink.get("href", None)
            elif span is not None:
                node["title"] = get_text(span)
            else:
                text = get_text(li_elem)
                if not text:
                    return None
                node["title"] = text
                node["sutra_id"] = self._extract_sutra_id(text)

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
                    "href": None,
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

    # ================================================================
    # 从目录树构建 catalog（主数据源）
    # ================================================================

    def _build_catalog_from_trees(self):
        """
        遍历 advance_nav + bulei_nav 目录树，提取所有叶子节点的经号和经名。
        bulei_nav 包含 T0220a~o 等子编号，advance_nav 中没有。
        卷数不在启动时加载（太慢），改为按需查 toc。
        """
        def walk_tree(nodes, canon_hint=""):
            for node in nodes:
                sid = node.get("sutra_id")
                if sid and sid not in self.catalog:
                    canon = self._guess_canon(sid)
                    title = self._extract_sutra_title(node["title"])

                    self.catalog[sid] = {
                        "sutra_id": sid,
                        "canon": canon,
                        "title": title,
                        "author": "",
                        "category": "",
                        "juan_count": 0,  # 0 = 未加载，按需查 toc
                    }

                title = node.get("title", "")
                child_canon = canon_hint
                if not node.get("sutra_id") and len(title) >= 1:
                    m = re.match(r"^([A-Z]+)\b", title)
                    if m:
                        child_canon = m.group(1)

                if node["children"]:
                    walk_tree(node["children"], child_canon)

        walk_tree(self.canon_tree)
        canon_count = len(self.catalog)
        # 同时遍历部类目录树，补充子编号（如 T0220a~o）
        walk_tree(self.bulei_tree)
        bulei_extra = len(self.catalog) - canon_count
        log.info(f"  从目录树提取: {canon_count} 个经文 (经藏) + {bulei_extra} 个补充 (部类)")

    @staticmethod
    def _guess_canon(sutra_id: str) -> str:
        """从经号推断 canon 代码：T0001→T, Ba001→B, JA042→J, GA0026→GA"""
        m = re.match(r"^([A-Z]+)", sutra_id)
        return m.group(1) if m else ""

    def _get_juan_count_from_toc(self, sutra_id: str, canon: str) -> int:
        """从 toc 文件获取卷数"""
        toc_path = self.toc_dir / canon / f"{sutra_id}.xml"
        if not toc_path.exists():
            return 1

        try:
            content = toc_path.read_text(encoding="utf-8")
            parser = ET.XMLParser(recover=True)
            root = ET.fromstring(content.encode("utf-8"), parser=parser)

            for nav_elem in root.xpath("//*[local-name()='nav']"):
                if nav_elem.get("type") == "juan":
                    count = 0
                    for ol in nav_elem.findall("ol"):
                        for li in ol.findall("li"):
                            if li.find("cblink") is not None:
                                count += 1
                    if count > 0:
                        return count
        except Exception as e:
            log.debug(f"toc 解析出错 {sutra_id}: {e}")

        return 1

    # ================================================================
    # 从 catalog.txt 补充作者和部类（可选增强）
    # ================================================================

    def _supplement_from_catalog_txt(self):
        """从 catalog.txt 补充 author 和 category 字段"""
        path = self.cbeta_dir / "catalog.txt"
        if not path.exists():
            return

        supplemented = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip().rstrip("\r")
            if not line:
                continue

            parts = [p.strip() for p in line.split(" , ")]
            if len(parts) < 7:
                continue

            canon = parts[0]
            category = parts[1]
            sutra_no = parts[4]
            author = parts[7] if len(parts) > 7 else ""

            sutra_id = f"{canon}{sutra_no}"

            if sutra_id in self.catalog:
                if not self.catalog[sutra_id]["author"] and author:
                    self.catalog[sutra_id]["author"] = author
                    supplemented += 1
                if not self.catalog[sutra_id]["category"] and category:
                    self.catalog[sutra_id]["category"] = category

        log.info(f"  catalog.txt 补充: {supplemented} 个作者信息")

    # ================================================================
    # 文件路径解析
    # ================================================================

    def _resolve_from_toc(self, sutra_id: str, juan: int) -> Path | None:
        """从 toc 文件查找卷对应的 XML 文件路径"""
        info = self.catalog.get(sutra_id)
        canon = info["canon"] if info else self._guess_canon(sutra_id)
        if not canon:
            return None

        toc_path = self.toc_dir / canon / f"{sutra_id}.xml"
        if not toc_path.exists():
            return None

        try:
            content = toc_path.read_text(encoding="utf-8")
            parser = ET.XMLParser(recover=True)
            root = ET.fromstring(content.encode("utf-8"), parser=parser)
        except Exception:
            return None

        # 找 <nav type="juan"> 中第 juan 个 cblink
        for nav_elem in root.xpath("//*[local-name()='nav']"):
            if nav_elem.get("type") == "juan":
                juan_num = 0
                for ol in nav_elem.findall("ol"):
                    for li in ol.findall("li"):
                        cblink = li.find("cblink")
                        if cblink is not None:
                            juan_num += 1
                            if juan_num == juan:
                                href = cblink.get("href", "")
                                file_ref = href.split("#")[0]
                                if file_ref:
                                    return self.cbeta_dir / file_ref

        return None

    def _resolve_by_scan(self, sutra_id: str, juan: int) -> Path | None:
        """通过扫描目录匹配文件（回退方案）"""
        canon = self._guess_canon(sutra_id)
        if not canon:
            return None

        no = sutra_id[len(canon):]
        # 针对诸如 J15nB005 这样的经号，文件名中往往只有 nB005_
        # 我们寻找 'n' 后面的部分作为实际要匹配的经号特征
        actual_no = no
        if 'n' in no.lower():
            actual_no = no.lower().split('n')[-1]

        juan_str = f"_{juan:03d}.xml"

        canon_dir = self.xml_dir / canon
        if not canon_dir.exists():
            return None

        for vol_dir in sorted(canon_dir.iterdir()):
            if not vol_dir.is_dir():
                continue
            for f in vol_dir.iterdir():
                if f.name.endswith(juan_str) and f"n{actual_no}_" in f.name.lower():
                    return f

        return None


# ================================================================
# 便捷的全局初始化函数
# ================================================================

_nav_instance: CBETANav | None = None


def get_nav(cbeta_dir: str | Path = None) -> CBETANav:
    """获取全局 CBETANav 实例（单例模式）"""
    global _nav_instance
    if _nav_instance is None:
        if cbeta_dir is None:
            # 从 config 模块获取 CBETA 数据路径
            import config
            cbeta_dir = config.CBETA_BASE
        _nav_instance = CBETANav(cbeta_dir)
    return _nav_instance
