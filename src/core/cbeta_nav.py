"""
CBETA 導航數據解析模塊 — 零數據庫方案

直接讀取 CBETA Bookcase 原始文件，在啟動時解析到內存：
  - advance_nav.xhtml → 經藏目錄樹 + 經文元數據（經號、經名）【主數據源】
  - bulei_nav.xhtml   → 部類目錄樹（阿含部、般若部等）
  - catalog.txt       → 補充作者、部類信息
  - bookdata.txt      → 藏經代碼→名稱映射
  - toc/              → 品章目錄 + 卷索引（按需加載）
"""

import re
import logging
from pathlib import Path

import lxml.etree as ET

log = logging.getLogger(__name__)


class CBETANav:
    """
    CBETA Bookcase 導航數據管理器。
    啟動時解析 xhtml 導航文件構建目錄樹和經文索引。
    """

    # 大般若經子編號 → (全局起始卷偏移, 本部分卷數)
    # CBETA 將 T0220 拆分為 a~o 共 15 個子編號，但 toc/XML 只用 T0220
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

        # 內存數據
        self.catalog: dict[str, dict] = {}      # {sutra_id: {title, author, juan_count, ...}}
        self.canon_names: dict[str, str] = {}   # {canon_code: canon_name_zh}
        self.canon_tree: list[dict] = []        # 經藏目錄樹
        self.bulei_tree: list[dict] = []        # 部類目錄樹

        # 1. 加載藏經名稱
        self._load_bookdata()

        # 2. 解析 xhtml 導航文件 → 目錄樹 + 經文索引（主數據源）
        self._load_canon_tree()
        self._load_bulei_tree()

        # 3. 從 xhtml 樹中提取所有經文元數據到 catalog
        self._build_catalog_from_trees()

        # 4. 從 catalog.txt 補充作者和部類（可選）
        self._supplement_from_catalog_txt()

        log.info(f"CBETANav 初始化完成: {len(self.catalog)} 個經文, "
                 f"{len(self.canon_tree)} 個經藏, {len(self.bulei_tree)} 個部類")

    # ================================================================
    # 公開接口
    # ================================================================

    def get_sutra_info(self, sutra_id: str) -> dict | None:
        """查詢經文元數據"""
        info = self.catalog.get(sutra_id)
        if info:
            return info
        # 子編號回退：T0220a → T0220
        base = self._strip_sub_letter(sutra_id)
        if base:
            return self.catalog.get(base)
        return None

    def get_total_juan(self, sutra_id: str) -> int:
        """查詢經文總卷數（按需從 toc 加載）"""
        info = self.catalog.get(sutra_id)
        if not info:
            # 子編號映射錶快速查找（如 T0220a → 200 卷）
            sub = self._SUB_SUTRA_MAP.get(sutra_id)
            if sub:
                return sub[1]
            return 1
        if info["juan_count"] == 0:
            # 子編號映射表優先
            sub = self._SUB_SUTRA_MAP.get(sutra_id)
            if sub:
                info["juan_count"] = sub[1]
            else:
                # 按需加載卷數
                canon = info.get("canon") or self._guess_canon(sutra_id)
                count = self._get_juan_count_from_toc(sutra_id, canon)
                # 子編號回退（如 T0220a → T0220）
                if count <= 1:
                    base_id = self._strip_sub_letter(sutra_id)
                    if base_id:
                        count2 = self._get_juan_count_from_toc(base_id, canon)
                        if count2 > count:
                            count = count2
                info["juan_count"] = count
        return info["juan_count"]

    def get_sutra_title(self, sutra_id: str) -> str:
        """查詢經名"""
        info = self.catalog.get(sutra_id)
        if info:
            return info.get("title", sutra_id)
        # 子編號回退：T0220a → T0220
        base = self._strip_sub_letter(sutra_id)
        if base:
            base_info = self.catalog.get(base)
            if base_info:
                return base_info.get("title", sutra_id)
        return sutra_id

    @staticmethod
    def _strip_sub_letter(sutra_id: str) -> str | None:
        """
        去掉子編號後綴，如 T0220a → T0220。
        CBETA 大般若經等大經被拆成 T0220a~T0220o，但 toc/XML 文件只用 T0220。
        僅當末尾是小寫字母且前面是數字時才剝離。
        """
        if sutra_id and sutra_id[-1].islower() and len(sutra_id) > 2 and sutra_id[-2].isdigit():
            return sutra_id[:-1]
        return None

    def resolve_scroll_path(self, sutra_id: str, juan: int) -> Path | None:
        """
        根據經號和卷號定位 XML 文件路徑。
        優先 toc 精確查找，回退到目錄掃描。
        對 T0220a 等子編號，先將 local_juan 偏移為全局卷號，
        再用基礎編號 T0220 查找。
        """
        # 子編號偏移處理：T0220a 的第 1 卷 → 全局第 1 卷，T0220b 的第 1 卷 → 全局第 201 卷
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
            # 如果偏移後找不到，不再回退，直接返回 None
            return None

        # 方法1: 從 toc 文件查找精確路徑
        path = self._resolve_from_toc(sutra_id, juan)
        if path and path.exists():
            return path

        # 方法2: 目錄掃描回退
        path = self._resolve_by_scan(sutra_id, juan)
        if path and path.exists():
            return path

        # 方法3: 子編號回退 — 去掉末尾字母重試（如 T0220a → T0220）
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
        """返回經藏目錄樹"""
        return self.canon_tree

    def get_bulei_tree(self) -> list[dict]:
        """返回部類目錄樹"""
        return self.bulei_tree

    # ================================================================
    # 加載 bookdata.txt → 藏經代碼映射
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

        log.info(f"  bookdata.txt: {len(self.canon_names)} 個藏經代碼")

    # ================================================================
    # 解析 xhtml 導航文件 → 目錄樹
    # ================================================================

    def _load_canon_tree(self):
        """解析 advance_nav.xhtml 為經藏目錄樹"""
        path = self.cbeta_dir / "advance_nav.xhtml"
        if not path.exists():
            log.warning(f"advance_nav.xhtml 不存在: {path}")
            return
        self.canon_tree = self._parse_nav_xhtml(path)
        log.info(f"  advance_nav.xhtml: {len(self.canon_tree)} 個頂級節點")

    def _load_bulei_tree(self):
        """解析 bulei_nav.xhtml 為部類目錄樹"""
        path = self.cbeta_dir / "bulei_nav.xhtml"
        if not path.exists():
            log.warning(f"bulei_nav.xhtml 不存在: {path}")
            return
        self.bulei_tree = self._parse_nav_xhtml(path)
        log.info(f"  bulei_nav.xhtml: {len(self.bulei_tree)} 個頂級節點")

    @staticmethod
    def _extract_sutra_id(text: str) -> str | None:
        """
        從 cblink 文本中提取經號。
        支持：T0001、Ba001、JA042、GA0026、T0150A 等
        """
        m = re.match(r"^([A-Z]+[a-zA-Z]*\d+[a-zA-Z]*)\b", text)
        return m.group(1) if m else None

    @staticmethod
    def _extract_sutra_title(text: str) -> str:
        """
        從 cblink 文本中提取經名（去掉前面的經號）。
        'T0001 長阿含經' → '長阿含經'
        """
        m = re.match(r"^[A-Z]+[a-zA-Z]*\d+[a-zA-Z]*\s+(.+)", text)
        return m.group(1).strip() if m else text.strip()

    def _parse_nav_xhtml(self, file_path: Path) -> list[dict]:
        """
        解析 xhtml 導航文件為樹形結構。
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

            # 遞歸處理子 <ol>
            for ol in li_elem.findall("ol"):
                for li in ol.findall("li"):
                    child = parse_li(li)
                    if child:
                        node["children"].append(child)

            return node

        # 處理 <nav> 的直接子元素
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
    # 從目錄樹構建 catalog（主數據源）
    # ================================================================

    def _build_catalog_from_trees(self):
        """
        遍歷 advance_nav + bulei_nav 目錄樹，提取所有葉子節點的經號和經名。
        bulei_nav 包含 T0220a~o 等子編號，advance_nav 中沒有。
        卷數不在啟動時加載（太慢），改為按需查 toc。
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
                        "juan_count": 0,  # 0 = 未加載，按需查 toc
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
        # 同時遍歷部類目錄樹，補充子編號（如 T0220a~o）
        walk_tree(self.bulei_tree)
        bulei_extra = len(self.catalog) - canon_count
        log.info(f"  從目錄樹提取: {canon_count} 個經文 (經藏) + {bulei_extra} 個補充 (部類)")

    @staticmethod
    def _guess_canon(sutra_id: str) -> str:
        """從經號推斷 canon 代碼：T0001→T, Ba001→B, JA042→J, GA0026→GA"""
        m = re.match(r"^([A-Z]+)", sutra_id)
        return m.group(1) if m else ""

    def _get_juan_count_from_toc(self, sutra_id: str, canon: str) -> int:
        """從 toc 文件獲取卷數"""
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
            log.debug(f"toc 解析出錯 {sutra_id}: {e}")

        return 1

    # ================================================================
    # 從 catalog.txt 補充作者和部類（可選增強）
    # ================================================================

    def _supplement_from_catalog_txt(self):
        """從 catalog.txt 補充 author 和 category 字段"""
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

        log.info(f"  catalog.txt 補充: {supplemented} 個作者信息")

    # ================================================================
    # 文件路徑解析
    # ================================================================

    def _resolve_from_toc(self, sutra_id: str, juan: int) -> Path | None:
        """從 toc 文件查找卷對應的 XML 文件路徑"""
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

        # 找 <nav type="juan"> 中第 juan 個 cblink
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
        """通過掃描目錄匹配文件（回退方案）"""
        canon = self._guess_canon(sutra_id)
        if not canon:
            return None

        no = sutra_id[len(canon):]
        # 針對諸如 J15nB005 這樣的經號，文件名中往往只有 nB005_
        # 我們尋找 'n' 後面的部分作為實際要匹配的經號特徵
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
# 便捷的全局初始化函數
# ================================================================

_nav_instance: CBETANav | None = None


def get_nav(cbeta_dir: str | Path = None) -> CBETANav:
    """獲取全局 CBETANav 實例（單例模式）"""
    global _nav_instance
    if _nav_instance is None:
        if cbeta_dir is None:
            # 從 config 模塊獲取 CBETA 數據路徑
            import config
            cbeta_dir = config.CBETA_BASE
        _nav_instance = CBETANav(cbeta_dir)
    return _nav_instance
