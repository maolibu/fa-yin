"""
CBETA XML 直接解析器（v2 — 完整註釋系統）
將 TEI P5 XML 直接轉換為 HTML，支持：
- 有對象註釋（mod）：黃色下劃線 + 懸浮 + 尾註雙向跳轉
- 無對象註釋（add 等）：數字標記 + 懸浮 + 尾註雙向跳轉
- 夾註（inline）：行內小字括號
- 校勘異讀（app）：黃色下劃線 + 懸浮
- 交叉引用（cf）：正文靜默，尾註列出

兩階段架構：1) 遞歸渲染正文 + 收集註釋；2) 拼接尾註區

覆蓋全部 body 標籤（基於 21,960 個 XML 全量掃描）。
"""

import re
import json
from lxml import etree

# ============================================================
# 命名空間
# ============================================================
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NS_MAP = {
    'cb': CB_NS,
    'tei': TEI_NS,
}

# ============================================================
# 標籤分類
# ============================================================
SKIP_TAGS = {
    "rdg",         # 校勘異讀 — 僅在 app tooltip 中出現
    "back",        # 附錄
    "charDecl",    # 缺字聲明
    "teiHeader",   # 文件頭
    "char", "charProp", "localName", "value", "mapping", "charName",
    "milestone",   # 卷分隔標記
    "msDesc", "msIdentifier", "settlement", "repository",
}

# 需要跳過的 note type
# orig: 僅當後面緊跟同 n 的 mod 時跳過（否則作為獨立註釋保留）
SKIP_NOTE_TYPES = {"star", "K33"}

# 交叉引用 type 前綴（正文靜默，收入尾註）
CF_PREFIXES = ("cf1", "cf2", "cf3", "cf4", "cf5", "cf6", "cf.", "cf", "f1:")

# 行內顯示的 note（小字括號，不進尾註）
INLINE_PLACES = {"inline", "inline2", "interlinear"}
INLINE_TYPES = {"authorial"}

# 從 mod 註釋提取對象文字的正則
# 模式: "辨【大】＊，辯【宋】＊" → 提取 "辨"
MOD_OBJ_PATTERN = re.compile(r'^(.+?)【大】')


class CBETAParser:
    def __init__(self, cbeta_dir=None, gaiji_path=None, nav=None):
        # 從 config.py 讀取默認路徑（避免硬編碼）
        import config
        cbeta_dir = cbeta_dir or str(config.CBETA_BASE)
        gaiji_path = gaiji_path or str(config.GAIJI_PATH)

        self.cbeta_dir = cbeta_dir
        self.ns = NS_MAP

        with open(gaiji_path, 'r', encoding='utf-8') as f:
            self.gaiji_data = json.load(f)

        if nav is not None:
            self.nav = nav
        else:
            from core.cbeta_nav import CBETANav
            self.nav = CBETANav(cbeta_dir)

    def resolve_file(self, sutra_id, scroll_id):
        """根據經號和卷號查找 XML 文件路徑"""
        path = self.nav.resolve_scroll_path(sutra_id, scroll_id)
        if path is None:
            raise FileNotFoundError(
                f"經文 {sutra_id} 第{scroll_id}卷 未找到對應的 XML 文件"
            )
        return str(path)

    def parse_scroll(self, sutra_id, scroll_id):
        """
        解析一卷經文，返回正文 HTML + 尾註區 HTML。
        兩階段：先渲染正文（收集註釋），再生成尾註。
        """
        file_path = self.resolve_file(sutra_id, scroll_id)

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(file_path, parser)
        root = tree.getroot()

        body = root.xpath("//tei:body", namespaces=self.ns)
        if not body:
            return "<div>No body found</div>"

        # 重置每卷的註釋收集
        self._notes = []       # 註釋列表: [{idx, content, obj_text, orig_n}]
        self._note_idx = 0     # 遞增序號

        # 第一階段：渲染正文
        content_html = self._render(body[0])

        # 第二階段：生成尾註區
        endnotes_html = self._build_endnotes()

        return content_html + endnotes_html

    def parse_header(self, sutra_id, scroll_id=1):
        """
        解析 XML teiHeader，提取經文元數據。
        默認讀取第 1 卷的頭部（所有卷的頭部信息一致）。

        返回字典，字段為空則不包含，方便模板 {% if %} 判斷。
        """
        try:
            file_path = self.resolve_file(sutra_id, scroll_id)
        except FileNotFoundError:
            return {}

        ns = {"tei": TEI_NS, "cb": CB_NS}
        xml_ns = XML_NS

        try:
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(file_path, parser)
            root = tree.getroot()
        except Exception:
            return {}

        header = root.find(f"{{{TEI_NS}}}teiHeader")
        if header is None:
            return {}

        meta = {}

        # --- 標題 ---
        for t in header.findall(".//tei:titleStmt/tei:title", ns):
            level = t.get("level", "")
            lang = t.get(f"{{{xml_ns}}}lang", "")
            text = "".join(t.itertext()).strip()
            if not text:
                continue

            if level == "m" and "zh" in lang:
                meta["title_zh"] = text
            elif level == "s" and "zh" in lang:
                meta["canon_name_zh"] = text
            elif level == "s" and not lang:
                meta["canon_name_en"] = text

        # --- 作者/譯者 ---
        author_el = header.find(".//tei:titleStmt/tei:author", ns)
        if author_el is not None:
            author_text = "".join(author_el.itertext()).strip()
            if author_text:
                meta["author"] = author_text

        # --- 卷數 ---
        extent_el = header.find(".//tei:extent", ns)
        if extent_el is not None:
            meta["extent"] = (extent_el.text or "").strip()

        # --- 經藏/冊/經號 ---
        cbeta_idno = header.find(".//tei:publicationStmt/tei:idno[@type='CBETA']", ns)
        if cbeta_idno is not None:
            for sub in cbeta_idno.findall("tei:idno", ns):
                id_type = sub.get("type", "")
                val = (sub.text or "").strip()
                if id_type == "canon":
                    meta["canon_code"] = val
                elif id_type == "vol":
                    meta["vol"] = val
                elif id_type == "no":
                    meta["no"] = val

        # 組合冊號顯示文本：T.1.1
        parts = [meta.get("canon_code", ""), meta.get("vol", ""), meta.get("no", "")]
        ref_str = ".".join(p for p in parts if p)
        if ref_str:
            meta["canon_ref"] = ref_str

        # --- 底本來源 ---
        bibl_el = header.find(".//tei:sourceDesc/tei:bibl", ns)
        if bibl_el is not None:
            bibl_text = "".join(bibl_el.itertext()).strip()
            if bibl_text:
                meta["source"] = bibl_text

        # --- 手稿信息（稀有，約 1%） ---
        ms_p = header.find(".//tei:sourceDesc/tei:msDesc/tei:p", ns)
        if ms_p is not None:
            ms_text = "".join(ms_p.itertext()).strip()
            if ms_text:
                meta["ms_desc"] = ms_text

        # --- 數據貢獻者 ---
        for proj_p in header.findall(".//tei:projectDesc/tei:p", ns):
            lang = proj_p.get(f"{{{xml_ns}}}lang", "")
            if "zh" in lang:
                text = "".join(proj_p.itertext()).strip()
                if text:
                    meta["contributors"] = text
                break

        # --- 標點方式 ---
        punct_el = header.find(".//tei:editorialDecl/tei:punctuation/tei:p", ns)
        if punct_el is not None:
            meta["punctuation"] = (punct_el.text or "").strip()

        # --- 校勘版本（witness 列表） ---
        witnesses = []
        for w in header.findall(".//tei:tagsDecl//tei:witness", ns):
            w_text = (w.text or "").strip()
            if w_text:
                witnesses.append(w_text)
        if witnesses:
            meta["witnesses"] = " ".join(witnesses)

        # --- 涉及語言 ---
        languages = []
        for lang_el in header.findall(".//tei:langUsage/tei:language", ns):
            ident = lang_el.get("ident", "")
            name = (lang_el.text or "").strip()
            if name and ident != "zh-Hant":
                languages.append(name)
        if languages:
            meta["languages"] = "、".join(languages)

        # --- 版權聲明 ---
        avail_el = header.find(".//tei:availability/tei:p", ns)
        if avail_el is not None:
            meta["availability"] = (avail_el.text or "").strip()

        # --- 版本/版次 ---
        edition_el = header.find(".//tei:editionStmt/tei:edition", ns)
        if edition_el is not None:
            ed_text = (edition_el.text or "").strip()
            if ed_text:
                meta["edition"] = ed_text

        return meta

    # ============================================================
    # 工具方法
    # ============================================================
    def _local_tag(self, node):
        """獲取本地標籤名（去除命名空間）"""
        tag = node.tag
        if "}" in tag:
            return tag.split("}")[1]
        return tag

    def _qualified_tag(self, node):
        """獲取帶 cb: 前綴的標籤名"""
        tag = node.tag
        if "}" in tag:
            ns, name = tag.split("}")
            ns = ns[1:]
            if ns == CB_NS:
                return f"cb:{name}"
            return name
        return tag

    def _clean_text(self, text):
        """清理文本：將所有連續空白壓縮為單個空格"""
        if not text:
            return ""
        return " ".join(text.split())

    def _get_attr(self, node, attr, ns=None):
        """獲取屬性值"""
        if ns:
            return node.get(f"{{{ns}}}{attr}", "")
        return node.get(attr, "")

    def _resolve_gaiji(self, ref):
        """解析缺字引用（支持 SD- 悉曇字符 GIF 圖片）"""
        gid = ref.replace("#", "")
        # 悉曇字符：返回 GIF 圖片標籤
        if gid.startswith("SD-") and len(gid) >= 5:
            # SD-A5A9 → 子目錄 A5, 文件 SD-A5A9.gif
            subdir = gid[3:5]  # 取十六進制前綴
            return (f"<img src='/sd-gif/{subdir}/{gid}.gif' "
                    f"class='siddham-char' alt='{gid}' "
                    f"title='悉曇字 {gid}'>")
        ginfo = self.gaiji_data.get(gid)
        if ginfo:
            return ginfo.get('uni_char') or ginfo.get('composition') or gid
        return gid

    def _escape(self, text):
        """HTML 轉義（用於屬性值）"""
        if not text:
            return ""
        return (text.replace("&", "&amp;")
                    .replace("'", "&apos;")
                    .replace('"', "&quot;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

    def _next_note_idx(self):
        """獲取下一個註釋序號"""
        self._note_idx += 1
        return self._note_idx

    # ============================================================
    # 核心渲染引擎
    # ============================================================
    def _render(self, node, in_note=False):
        """
        遞歸渲染 XML 節點為 HTML。

        參數:
            node: lxml 元素
            in_note: 是否正在渲染註釋內部內容
                     （True 時註釋不生成標記，避免遞歸和重複）
        """
        qtag = self._qualified_tag(node)

        # ---- 校勘段 <app> ----
        if qtag == "app":
            return self._render_app(node)

        # ---- 跳過類標籤 ----
        if qtag in SKIP_TAGS:
            return self._clean_text(node.tail or "")

        # ---- 註釋 <note> ----
        if qtag == "note":
            return self._render_note(node, in_note)

        # ---- 按標籤分發 ----
        output = []
        open_tag = ""
        close_tag = ""

        # 行號/頁號標記
        if qtag == "lb":
            n = node.get("n", "")
            lb_type = node.get("type", "")
            if lb_type != "old":
                open_tag = f"<span class='lb-marker' data-n='{n}'></span>"

        elif qtag == "pb":
            page_id = node.get("n", "")
            ed = node.get("ed", "")
            xml_id = self._get_attr(node, "id", XML_NS)  # 如 T01.0001.0001a
            if page_id:
                # 用 span 而非 div — div 會令瀏覽器自動關閉外層 <p>，導致斷段
                open_tag = f"<span class='page-break' id='pb-{page_id}' data-ed='{ed}'>"
                # 僅首欄(a)顯示原版圖片鏈接圖標
                if page_id.endswith("a") and xml_id:
                    # xml:id 格式: T01.0001.0001a → canon=T, vol=01, page=0001
                    parts = xml_id.split(".")
                    if len(parts) >= 3:
                        canon_vol = parts[0]       # "T01"
                        canon = canon_vol[0]        # "T"
                        vol = canon_vol[1:]         # "01"
                        page_num = page_id[:-1]     # "0001" (去掉欄號)
                        dila_url = f"https://dia.dila.edu.tw/uv3/index.html?id={canon}v{vol}p{page_num}"
                        open_tag += (
                            f"<a class='page-img-link' href='{dila_url}' "
                            f"target='_blank' title='查看原版頁面 p.{page_num}'>"
                            f"📜</a>"
                        )
                open_tag += "</span>"

        # 空格/停頓
        elif qtag == "space":
            quantity = node.get("quantity", "1")
            try:
                n = int(quantity)
            except ValueError:
                n = 1
            open_tag = f"<span class='space'>{'　' * n}</span>"

        elif qtag == "caesura":
            open_tag = "<span class='caesura'></span>"

        # 缺字
        elif qtag == "g":
            ref = node.get("ref", "")
            char = self._resolve_gaiji(ref)
            output.append(f"<span class='gaiji'>{char}</span>")

        # 校勘底本
        elif qtag == "lem":
            wit = self._escape(node.get("wit", ""))
            open_tag = f"<span class='lem' data-wit='{wit}'>"
            close_tag = "</span>"

        # 段落
        elif qtag == "p":
            xml_id = self._get_attr(node, "id", XML_NS)
            cb_type = self._get_attr(node, "type", CB_NS)
            css_class = "dharani" if cb_type == "dharani" else "para-block"
            id_str = f" id='{xml_id}'" if xml_id else ""
            open_tag = f"<p class='{css_class}'{id_str}>"
            if xml_id:
                open_tag += f"<span class='para-id' data-id='{xml_id}'></span>"
            close_tag = "</p>"

        # 偈頌
        elif qtag == "lg":
            lg_type = node.get("type", "")
            open_tag = f"<div class='lg' data-type='{lg_type}'>"
            close_tag = "</div>"

        elif qtag == "l":
            open_tag = "<div class='l'>"
            close_tag = "</div>"

        # 卷標記
        elif qtag == "cb:juan":
            fun = node.get("fun", "")
            open_tag = f"<div class='juan' data-fun='{fun}'>"
            close_tag = "</div>"

        elif qtag == "cb:jhead":
            open_tag = "<span class='jhead'>"
            close_tag = "</span>"

        # 目錄標記
        elif qtag == "cb:mulu":
            mulu_type = node.get("type", "")
            mulu_n = node.get("n", "")
            title = self._get_plain_text(node) or mulu_n
            output.append(
                f"<span class='mulu' data-type='{mulu_type}' data-n='{mulu_n}' hidden>{title}</span>"
            )
            return "".join(output) + self._clean_text(node.tail or "")

        # 章節
        elif qtag == "cb:div":
            dtype = node.get("type", "unknown")
            open_tag = f"<div class='div-{dtype}' data-type='{dtype}'>"
            close_tag = "</div>"

        # 標題/署名/尾題
        elif qtag == "head":
            head_type = node.get("type", "")
            open_tag = f"<div class='head' data-type='{head_type}'>"
            close_tag = "</div>"

        elif qtag == "byline":
            cb_type = self._get_attr(node, "type", CB_NS)
            open_tag = f"<div class='byline' data-type='{cb_type}'>"
            close_tag = "</div>"

        elif qtag == "trailer":
            open_tag = "<p class='trailer'>"
            close_tag = "</p>"

        # 列表
        elif qtag == "list":
            rend = node.get("rend", "")
            open_tag = f"<ul class='list' data-rend='{rend}'>"
            close_tag = "</ul>"

        elif qtag == "item":
            n = node.get("n", "")
            n_str = f" data-n='{n}'" if n else ""
            open_tag = f"<li{n_str}>"
            close_tag = "</li>"

        # 表格
        elif qtag == "table":
            open_tag = "<table class='cbeta-table'>"
            close_tag = "</table>"

        elif qtag == "row":
            open_tag = "<tr>"
            close_tag = "</tr>"

        elif qtag == "cell":
            cols = node.get("cols", "")
            rows = node.get("rows", "")
            attr_str = ""
            if cols:
                attr_str += f" colspan='{cols}'"
            if rows:
                attr_str += f" rowspan='{rows}'"
            open_tag = f"<td{attr_str}>"
            close_tag = "</td>"

        # 引文
        elif qtag == "quote":
            q_type = node.get("type", "")
            source = self._escape(node.get("source", ""))
            open_tag = f"<blockquote class='quote' data-type='{q_type}' data-source='{source}'>"
            close_tag = "</blockquote>"

        # 模糊字
        elif qtag == "unclear":
            cert = node.get("cert", "")
            reason = node.get("reason", "")
            open_tag = f"<span class='unclear' data-cert='{cert}' data-reason='{reason}'>"
            close_tag = "</span>"

        # 外語（梵文等）
        elif qtag == "foreign":
            f_lang = self._get_attr(node, "lang", XML_NS) or node.get("lang", "")
            f_text = self._get_plain_text(node)
            open_tag = f"<span class='foreign' lang='{f_lang}' title='{self._escape(f_text)}'>"
            close_tag = "</span>"

        # 對話
        elif qtag == "sp":
            sp_type = self._get_attr(node, "type", CB_NS) or node.get("type", "")
            open_tag = f"<div class='speech' data-type='{sp_type}'>"
            close_tag = "</div>"

        elif qtag == "cb:dialog":
            d_type = node.get("type", "")
            open_tag = f"<div class='dialog' data-type='{d_type}'>"
            close_tag = "</div>"

        # 圖片
        elif qtag == "figure":
            open_tag = "<figure class='cbeta-figure'>"
            close_tag = "</figure>"

        elif qtag == "graphic":
            url = node.get("url", "")
            open_tag = f"<img src='{url}' class='cbeta-graphic' />"

        elif qtag == "figDesc":
            open_tag = "<figcaption>"
            close_tag = "</figcaption>"

        # 字典/詞條
        elif qtag == "entry":
            style = node.get("style", "")
            style_str = f" style='{style}'" if style else ""
            open_tag = f"<div class='dict-entry'{style_str}>"
            close_tag = "</div>"

        elif qtag == "form":
            open_tag = "<span class='dict-form'>"
            close_tag = "</span>"

        elif qtag == "cb:def":
            open_tag = "<span class='dict-def'>"
            close_tag = "</span>"

        elif qtag == "cb:sg":
            sg_type = node.get("type", "")
            open_tag = f"<span class='phonetic' data-type='{sg_type}'>"
            close_tag = "</span>"

        # 格式化
        elif qtag == "hi":
            rend = node.get("rend", "")
            style = node.get("style", "")
            if "bold" in rend:
                open_tag = "<b>"
                close_tag = "</b>"
            elif style:
                open_tag = f"<span style='{style}'>"
                close_tag = "</span>"
            else:
                open_tag = f"<span class='hi' data-rend='{rend}'>"
                close_tag = "</span>"

        elif qtag == "seg":
            rend = node.get("rend", "")
            open_tag = f"<span class='seg' data-rend='{rend}'>"
            close_tag = "</span>"

        # 術語
        elif qtag == "term":
            t_lang = self._get_attr(node, "lang", XML_NS) or ""
            open_tag = f"<span class='term' lang='{t_lang}'>"
            close_tag = "</span>"

        # 引用鏈接
        elif qtag == "ref":
            target = node.get("target", "")
            open_tag = f"<a class='ref' href='{target}'>"
            close_tag = "</a>"

        elif qtag == "ptr":
            target = node.get("target", "")
            open_tag = f"<a class='ptr' href='{target}'>[→]</a>"

        # 正則化/校正
        elif qtag == "choice":
            pass

        elif qtag in ("corr", "reg"):
            pass

        elif qtag == "sic":
            open_tag = "<span class='sic' hidden>"
            close_tag = "</span>"

        elif qtag == "orig":
            open_tag = "<span class='orig' hidden>"
            close_tag = "</span>"

        # 編號/標籤
        elif qtag == "num":
            n = node.get("n", "")
            open_tag = f"<span class='num' data-n='{n}'>"
            close_tag = "</span>"

        elif qtag == "label":
            open_tag = "<span class='label'>"
            close_tag = "</span>"

        elif qtag == "formula":
            open_tag = "<span class='formula'>"
            close_tag = "</span>"

        elif qtag == "cb:docNumber":
            open_tag = "<span class='doc-number'>"
            close_tag = "</span>"

        # 嘉興藏
        elif qtag == "cb:jl_title":
            open_tag = "<span class='jl-title'>"
            close_tag = "</span>"

        elif qtag == "cb:jl_juan":
            open_tag = "<span class='jl-juan'>"
            close_tag = "</span>"

        elif qtag == "cb:jl_byline":
            jl_type = node.get("type", "")
            open_tag = f"<span class='jl-byline' data-type='{jl_type}'>"
            close_tag = "</span>"

        # 音義
        elif qtag in ("cb:yin", "cb:zi", "cb:fan"):
            tag_name = qtag.split(":")[1]
            open_tag = f"<span class='{tag_name}'>"
            close_tag = "</span>"

        # 引用來源
        elif qtag == "cit":
            open_tag = "<span class='citation'>"
            close_tag = "</span>"

        elif qtag == "bibl":
            open_tag = "<span class='bibl'>"
            close_tag = "</span>"

        elif qtag == "biblScope":
            open_tag = "<span class='biblscope'>"
            close_tag = "</span>"

        # 事件/日期
        elif qtag == "cb:event":
            open_tag = "<span class='event'>"
            close_tag = "</span>"

        elif qtag == "date":
            open_tag = "<span class='date'>"
            close_tag = "</span>"

        # 錨點
        elif qtag == "anchor":
            anchor_id = self._get_attr(node, "id", XML_NS)
            if anchor_id:
                open_tag = f"<a id='{anchor_id}' class='anchor'></a>"

        # 經名
        elif qtag == "title":
            open_tag = "<span class='title'>"
            close_tag = "</span>"

        # 編輯者
        elif qtag == "editor":
            open_tag = "<span class='editor'>"
            close_tag = "</span>"

        # cb:tt 中外對照組
        elif qtag == "cb:tt":
            tt_type = node.get("type", "")
            if tt_type == "app":
                # type="app" — 類似 <app>：中文顯示 + 外文tooltip + 關聯 mod 尾註
                return self._render_cb_tt_app(node)
            # 普通 cb:tt — 顯示中文 + 悉曇字符
            zh_parts = []
            sd_parts = []
            for child in node:
                child_qtag = self._qualified_tag(child)
                if child_qtag == "cb:t":
                    child_lang = self._get_attr(child, "lang", XML_NS) or child.get("lang", "")
                    if "zh" in child_lang:
                        child_text = self._render_children(child, in_note)
                        zh_parts.append(child_text)
                    elif "sa-Sidd" in child_lang or "Sidd" in child_lang:
                        # 悉曇梵字：渲染其中的 <g> 標籤（GIF 圖片）
                        child_text = self._render_children(child, in_note)
                        sd_parts.append(child_text)
            # 悉曇在前，中文注音在後（陀羅尼典型排列）
            parts = []
            if sd_parts:
                parts.append(f"<span class='siddham'>{''.join(sd_parts)}</span>")
            if zh_parts:
                parts.append("".join(zh_parts))
            res = "".join(parts)
            tail = self._clean_text(node.tail or "")
            return res + tail

        # cb:t 單獨出現
        elif qtag == "cb:t":
            child_lang = self._get_attr(node, "lang", XML_NS) or node.get("lang", "")
            if child_lang and "zh" not in child_lang:
                return self._clean_text(node.tail or "")

        # 未匹配標籤 → 透明遞歸

        # ---- 組裝 ----
        if node.text:
            output.append(self._clean_text(node.text))

        # 空/里程碑標籤 — 可能被 CSS 隱藏，不要把分頁標記注入其中
        _PB_SKIP_INJECT = {"lb", "anchor", "milestone", "cb:mulu", "space"}

        pending_pb = ""
        for child in node:
            child_qtag = self._qualified_tag(child)
            child_html = self._render(child, in_note)
            if child_qtag == "pb":
                # 緩衝分頁標記，稍後注入到下一個內容元素開頭
                pending_pb += child_html
            elif pending_pb and child_qtag not in _PB_SKIP_INJECT:
                # 將緩衝的分頁標記注入到此內容元素的 HTML 開頭
                gt_pos = child_html.find(">")
                if gt_pos >= 0 and child_html[0] == "<":
                    child_html = child_html[:gt_pos+1] + pending_pb + child_html[gt_pos+1:]
                else:
                    child_html = pending_pb + child_html
                pending_pb = ""
                output.append(child_html)
            else:
                output.append(child_html)
        # 尾部殘餘的分頁標記直接輸出
        if pending_pb:
            output.append(pending_pb)

        res = f"{open_tag}{''.join(output)}{close_tag}"

        if node.tail:
            res += self._clean_text(node.tail)

        return res

    # ============================================================
    # 校勘段 <app> 渲染 — 黃色下劃線 + tooltip
    # ============================================================
    def _render_app(self, node):
        """
        渲染校勘段：底本 <lem> 加黃色下劃線，異讀 <rdg> 放入懸浮 tooltip。
        如果有配對的 mod 註釋，使用 mod 內容作為 tooltip 並鏈接到尾註。
        """
        app_n = node.get("n", "")
        lem_node = node.find(f"{{{TEI_NS}}}lem")
        rdg_nodes = node.findall(f"{{{TEI_NS}}}rdg")

        lem_text = "???"
        if lem_node is not None:
            lem_text = self._render(lem_node, in_note=True)

        # 檢查是否有配對的 mod 註釋（已收入尾註）
        paired_note = self._find_paired_note(app_n) if app_n else None

        if paired_note:
            # 使用 mod 內容作為 tooltip，鏈接到尾註
            idx = paired_note["idx"]
            tooltip = paired_note["content"]
            res = (f"<span class='noted app-var' id='ref-{idx}' "
                   f"data-note-idx='{idx}' "
                   f"data-note-text='{self._escape(tooltip)}'>"
                   f"{lem_text}</span>")
        else:
            # 無配對 mod，使用 rdg 作為 tooltip（不進尾註）
            variants = []
            for rdg in rdg_nodes:
                wit = rdg.get("wit", "")
                r_text = self._render(rdg, in_note=True)
                if r_text.strip():
                    variants.append(f"{wit}: {r_text}")
                else:
                    variants.append(f"{wit}: (缺)")
            tooltip = " ｜ ".join(variants)
            if tooltip:
                res = f"<span class='noted app-var' title='{self._escape(tooltip)}'>{lem_text}</span>"
            else:
                res = lem_text

        if node.tail:
            res += self._clean_text(node.tail)
        return res

    def _find_paired_note(self, app_n):
        """查找是否有已收集的、與該 app 配對的 mod 註釋"""
        for note in self._notes:
            if note.get("app_n") == app_n:
                return note
        return None

    # ============================================================
    # cb:tt type="app" — 中外對照校勘（類似 <app>）
    # ============================================================
    def _render_cb_tt_app(self, node):
        """
        渲染 cb:tt type="app"：
        - 中文 cb:t 作為正文顯示
        - 外文 cb:t (place="foot") 作為 tooltip
        - 關聯配對的 mod 尾註（如有）
        """
        tt_n = node.get("n", "")

        # 收集中文和外文
        zh_text = ""
        foreign_parts = []
        for child in node:
            child_qtag = self._qualified_tag(child)
            if child_qtag != "cb:t":
                continue
            child_lang = self._get_attr(child, "lang", XML_NS) or child.get("lang", "")
            child_text = self._render_children(child, in_note=True)
            if "zh" in child_lang:
                zh_text = child_text
            else:
                # 外文：取語言名稱縮寫
                lang_label = child_lang.upper() if child_lang else "?"
                foreign_parts.append(f"{lang_label}: {child_text}")

        # 查找配對的 mod 尾註
        paired_note = self._find_paired_note(tt_n) if tt_n else None

        if paired_note:
            # 有配對 mod → 使用 mod 內容作為 tooltip，鏈接到尾註
            idx = paired_note["idx"]
            tooltip = paired_note["content"]
            # 如有外文，追加到 tooltip
            if foreign_parts:
                tooltip += " ｜ " + " ｜ ".join(foreign_parts)
            res = (f"<span class='noted app-var' id='ref-{idx}' "
                   f"data-note-idx='{idx}' "
                   f"data-note-text='{self._escape(tooltip)}'>"
                   f"{zh_text}</span>")
        elif foreign_parts:
            # 無配對 mod，但有外文 → 僅 tooltip（不進尾註）
            tooltip = " ｜ ".join(foreign_parts)
            res = f"<span class='noted app-var' title='{self._escape(tooltip)}'>{zh_text}</span>"
        else:
            # 既無配對也無外文 → 直接顯示中文
            res = zh_text

        tail = self._clean_text(node.tail or "")
        return res + tail

    # ============================================================
    # 註釋 <note> 渲染 — 完整分類處理
    # ============================================================
    def _render_note(self, node, in_note=False):
        """
        渲染註釋標籤，按類型分流：
        - orig / star → 跳過
        - cf* → 正文靜默，收入尾註
        - inline / interlinear / authorial → 行內小字括號
        - mod → 有對象註釋（黃色下劃線 + 懸浮 + 尾註）
        - add / rest / equivalent / 其他有n → 無對象註釋（數字 + 懸浮 + 尾註）
        - 嵌套在註釋內 (in_note=True) → 透明遞歸
        - 無 n 且無特殊類型 → 透明遞歸
        """
        n = node.get("n", "")
        place = node.get("place", "")
        note_type = node.get("type", "")
        tail = self._clean_text(node.tail or "")

        # 1. star 類型跳過
        if note_type in SKIP_NOTE_TYPES:
            return tail

        # 3. orig / mod — 無論是否嵌套都不應輸出原始文本
        #    （它們是 <app> 的元數據，app 自己會處理底本/異讀）
        if note_type == "orig":
            # 有配對 mod → 跳過；無配對 → 非嵌套時收入尾註
            next_sib = node.getnext()
            if (next_sib is not None and
                self._local_tag(next_sib) == "note" and
                next_sib.get("type") == "mod" and
                next_sib.get("n") == n):
                return tail
            else:
                if not in_note and n:
                    return self._render_numbered_note(node, n, tail)
                return tail

        if note_type == "mod":
            # 有配對 app/tt → 嵌套時只跳過，非嵌套時收入尾註
            next_sib = node.getnext()
            next_tag = self._local_tag(next_sib) if next_sib is not None else ""
            has_paired_app = (
                next_sib is not None and
                next_tag in ("app", "tt") and
                next_sib.get("n", "") == n
            )
            if in_note:
                # 嵌套時：有配對 app 就跳過（app 會顯示 lem），無配對也跳過文本
                return tail
            # 非嵌套時走原有邏輯（section 5）
            if has_paired_app:
                content = self._render_children(node, in_note=True)
                idx = self._next_note_idx()
                self._notes.append({
                    "idx": idx,
                    "content": content,
                    "obj_text": None,
                    "is_cf": False,
                    "app_n": n,
                })
                return tail
            else:
                return self._render_mod_note(node, n, tail)

        # 3b. 交叉引用 — 無論上下文都不在正文顯示
        #    （即使嵌套在 lem/app 內也不顯示 cf 定位碼）
        if note_type.startswith(CF_PREFIXES):
            if not in_note:
                inner = self._render_children(node, in_note=True)
                if inner.strip():
                    idx = self._next_note_idx()
                    self._notes.append({
                        "idx": idx,
                        "content": inner,
                        "obj_text": None,
                        "is_cf": True,
                    })
            return tail

        # 3c. 嵌套在註釋/校勘內 → 透明遞歸（orig/mod/cf 已處理）
        if in_note:
            inner = self._render_children(node, in_note=True)
            return f"{inner}{tail}"

        # 5. 行內註釋（夾註）→ 小字括號
        if place in INLINE_PLACES or note_type in INLINE_TYPES:
            inner = self._render_children(node, in_note=True)
            if inner.strip():
                return f"<span class='note-inline'>（{inner}）</span>{tail}"
            return tail

        # 6. 有 n 值的其他註釋（add, rest, equivalent, 空 type 等）
        #    檢查是否有配對的 <app>：有 → 只收入尾註（app 會負責下劃線）
        #    無配對 → 無對象註釋（上標數字）
        if n:
            next_sib = node.getnext()
            next_tag = self._local_tag(next_sib) if next_sib is not None else ""
            has_paired_app = (
                next_sib is not None and
                next_tag in ("app", "tt") and
                next_sib.get("n", "") == n
            )
            if has_paired_app:
                # add+app 配對：只收入尾註，由 <app> 顯示下劃線
                content = self._render_children(node, in_note=True)
                idx = self._next_note_idx()
                self._notes.append({
                    "idx": idx,
                    "content": content,
                    "obj_text": None,
                    "is_cf": False,
                    "app_n": n,
                })
                return tail
            return self._render_numbered_note(node, n, tail)

        # 7. 無 n 無特殊 type → 透明遞歸
        inner = self._render_children(node, in_note=True)
        return f"{inner}{tail}"

    def _render_mod_note(self, node, orig_n, tail):
        """
        渲染獨立 mod 註釋（無配對 app/cb:tt）：
        統一使用上標數字標記 [n]，因為獨立 mod 沒有 <lem> 包裹
        對象文字，空 span 在視覺上不可見。
        """
        content = self._render_children(node, in_note=True)
        plain_content = self._get_plain_text(node)

        # 提取對象文字（用於尾註顯示，不影響內聯標記）
        m = MOD_OBJ_PATTERN.match(plain_content)

        idx = self._next_note_idx()
        self._notes.append({
            "idx": idx,
            "content": content,
            "obj_text": m.group(1) if m else None,
            "is_cf": False,
        })

        # 統一使用數字上標（確保可見）
        return (f"<sup class='note-ref' id='ref-{idx}'>"
                f"<a href='#note-{idx}' data-note-idx='{idx}' "
                f"data-note-text='{self._escape(content)}'>"
                f"[{idx}]</a></sup>{tail}")

    def _render_numbered_note(self, node, orig_n, tail):
        """渲染無對象註釋：上標數字標記 + 懸浮 + 尾註"""
        content = self._render_children(node, in_note=True)

        idx = self._next_note_idx()
        self._notes.append({
            "idx": idx,
            "content": content,
            "obj_text": None,
            "is_cf": False,
        })

        return (f"<sup class='note-ref' id='ref-{idx}'>"
                f"<a href='#note-{idx}' data-note-idx='{idx}' "
                f"data-note-text='{self._escape(content)}'>"
                f"[{idx}]</a></sup>{tail}")

    # ============================================================
    # 尾註區生成
    # ============================================================
    def _build_endnotes(self):
        """根據收集到的註釋生成尾註區 HTML"""
        if not self._notes:
            return ""

        lines = []
        lines.append("<section class='endnotes'>")
        lines.append("<h3>註釋</h3>")
        lines.append("<ol>")

        for note in self._notes:
            idx = note["idx"]
            content = note["content"]
            is_cf = note.get("is_cf", False)

            # 交叉引用添加標籤
            cf_label = "<span class='cf-label'>參照</span> " if is_cf else ""

            lines.append(
                f"<li id='note-{idx}' data-note-idx='{idx}'>"
                f"<a class='note-back' href='#ref-{idx}' title='返回正文'>↩</a> "
                f"<span class='note-num'>[{idx}]</span> "
                f"{cf_label}{content}"
                f"</li>"
            )

        lines.append("</ol>")
        lines.append("</section>")

        return "\n".join(lines)

    # ============================================================
    # 輔助方法
    # ============================================================
    def _render_children(self, node, in_note=False):
        """渲染一個節點的所有子內容"""
        parts = []
        if node.text:
            parts.append(self._clean_text(node.text))
        for child in node:
            parts.append(self._render(child, in_note))
        return "".join(parts)

    def _get_plain_text(self, node):
        """遞歸提取純文本"""
        parts = []
        if node.text:
            parts.append(node.text)
        for child in node:
            tag = self._local_tag(child)
            if tag == "g":
                ref = child.get("ref", "")
                parts.append(self._resolve_gaiji(ref))
            elif tag in SKIP_TAGS:
                pass
            else:
                parts.append(self._get_plain_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts).strip()
