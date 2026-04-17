"""
導航目錄 API — 貝闕區（全藏目錄瀏覽）

將 cbeta_nav.py 的部類/經藏目錄樹暴露為 JSON API。
包含動態同部類註疏提取接口。
"""

import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/nav", tags=["導航"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 多層註疏檢測配置
#
# 策略：基礎關鍵詞 + 擴展複合詞 + ID 白名單
#     + 寬鬆關鍵詞（僅註疏文件夾內且非原典經號）
#     + 黑名單排除
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 第1層：基礎單字關鍵詞（高精度，任何場景都啟用）
_BASE_KEYWORDS = ("疏", "鈔", "註", "注", "箋", "抄", "科")

# 第2層：擴展複合詞（高精度，任何場景都啟用）
_COMPOUND_KEYWORDS = (
    # 疏類
    "義疏", "略疏", "新疏", "通疏", "正脈疏",
    # 解類
    "直解", "集解", "要解", "合解", "會解", "類解",
    "略解", "淺解", "正解", "易解", "論解",
    "句解", "節解",
    # 說類
    "直說", "郢說", "膚說", "闡說", "請益說",
    # 記類
    "述記", "義記", "翼記", "經記", "法記",
    "私記", "宗圓記", "復古記",
    # 義類
    "玄義", "會義", "義章", "通義",
    "如是經義", "分齊章",
    # 科類
    "科判", "科文", "科釋", "科註", "科節",
    # 注類
    "箋要", "箋註", "集註", "集釋", "纂註",
    # 講習類
    "講義", "講記", "講錄", "講述",
    # 論釋類
    "釋論", "論釋",
    # 贊類
    "幽贊", "玄贊", "述贊", "通贊", "旨贊",
    # 述/抄類
    "還源述", "義述",
    # 音義/指南/綱要類
    "音義", "音釋", "懸談",
    "指南", "指歸", "綱要", "綱目",
    "宗通", "宗要", "會本",
    "提綱", "要旨", "文句",
    # 鏡/覽類
    "玄鏡", "懸鏡",
    "節要", "釋要", "纂要",
    "備覽", "要覽",
    # 大意/綸貫/直指/秘錄類
    "大意", "綸貫", "直指", "秘錄",
    "撮要", "會元",
    # 口訣/演義/貫義/部旨等
    "口訣", "演義", "貫義", "部旨",
    "旨槩", "大略", "示珠指",
    # 自查發現的註疏體裁詞
    "正眼", "發隱", "彙纂", "決疑",
    "採微", "添足", "指掌", "開度", "際決",
    "知音", "擊節", "大窾", "授手",
    "演古", "訂義", "備撿", "玄籤",
    "隨釋", "備釋",
    "傳弘決", "搜要",
    "發微錄", "顯性錄",
    "披雲集", "吞海集",
    # 用戶第5輪確認
    "義解", "釋義", "關法",
    # 律部註釋
    "毘婆沙", "事義",
)

# 第3層：寬鬆關鍵詞（僅在註疏文件夾內且經號非原典區時生效）
# 「說」迴歸：有經號守衛保護，T0001-T1420 的「佛說X經」不會誤匹配
_LOOSE_KEYWORDS = ("解", "釋", "論", "說", "述", "贊", "記", "談")

# 第4層：黑名單（即使其他層命中也強制排除）
_BLACKLIST = (
    "語錄", "全集", "詩集", "年譜", "行狀",
    "碑文", "塔銘", "造像記",
    "懺法", "懺儀", "禮懺", "禮讚",
)


def _is_likely_original(sid: str, title: str = "") -> bool:
    """判斷是否可能是原典（非註疏），用於限制寬鬆關鍵詞的生效範圍。
    
    滿足以下任一條件即視為原典：
    1. 大正藏經號在 T0001-T1420（經律原典區）
    2. 標題以「經」結尾（任何藏的經典通常如此）
    """
    # 條件1：大正藏原典區
    m = re.match(r"T(\d+)", sid)
    if m and int(m.group(1)) <= 1420:
        return True
    # 條件2：標題以經結尾
    clean = re.sub(r"[\(（].*?[\)）]", "", title).strip()
    if clean.endswith("經"):
        return True
    return False


def _is_whitelist_id(sid: str) -> bool:
    """判斷經號是否在大正藏註疏/釋論區。
    T1505-1535: 釋經論 (大正藏卷25)
    T1693-1821: 經疏部+論疏部 (大正藏卷33-40)
    T2732-2865: 古逸疏 (大正藏卷85)
    """
    m = re.match(r"T(\d+)", sid)
    if not m:
        return False
    num = int(m.group(1))
    return (1505 <= num <= 1535 or
            1693 <= num <= 1821 or
            2732 <= num <= 2865)


def _folder_is_commentary_type(title: str) -> bool:
    """判斷文件夾標題是否標記為註疏類型（含疏/論/註等字）"""
    hints = ("疏", "論", "註", "注", "釋", "解", "科", "記", "贊", "鈔")
    return any(h in title for h in hints)


def _is_commentary(title: str, sid: str = "",
                    folder_is_commentary: bool = False) -> bool:
    """多層註疏檢測。

    Args:
        title: 經文標題
        sid: 經文編號（如 T1700）
        folder_is_commentary: 該經文所在文件夾是否為註疏型
    """
    if not title:
        return False

    # 黑名單優先排除
    for bk in _BLACKLIST:
        if bk in title:
            return False

    # 判斷標題是否以「經」結尾（經典而非註疏）
    clean_title = re.sub(r"[\(（].*?[\)）]", "", title).strip()
    title_ends_jing = clean_title.endswith("經")

    # 第1層：基礎關鍵詞（即使以經結尾也生效，如「注維摩詰經」）
    for kw in _BASE_KEYWORDS:
        if kw in title:
            return True

    # 以經結尾的標題：跳過複合詞和寬鬆詞（防止「大意經」「決疑經」誤判）
    # 只允許基礎關鍵詞和 ID 白名單命中
    if title_ends_jing:
        return _is_whitelist_id(sid)

    # 第2層：擴展複合詞
    for kw in _COMPOUND_KEYWORDS:
        if kw in title:
            return True

    # 第3層：ID 白名單（大正藏註疏區經號）
    if _is_whitelist_id(sid):
        return True

    # 第4層：寬鬆關鍵詞（僅在註疏文件夾內 + 非原典時生效）
    if folder_is_commentary and not _is_likely_original(sid, title):
        for kw in _LOOSE_KEYWORDS:
            if kw in title:
                return True

    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 樹遍歷工具函數
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_all_sutra_ids(node: dict) -> list[str]:
    """遞歸提取節點下所有 sutra_id"""
    results = []
    sid = node.get("sutra_id")
    if sid:
        results.append(sid)
    for child in node.get("children", []):
        results.extend(_extract_all_sutra_ids(child))
    return results


def _find_with_ancestors(nodes: list[dict], target_id: str, ancestors=None):
    """查找 target_id，同時記錄祖先路徑"""
    if ancestors is None:
        ancestors = []
    for node in nodes:
        children = node.get("children", [])
        for child in children:
            if child.get("sutra_id") == target_id:
                return node, ancestors
        result = _find_with_ancestors(
            children, target_id, ancestors + [node]
        )
        if result:
            return result
    return None


def _get_commentaries(nav, sutra_id: str,
                      parent_node: dict) -> list[dict]:
    """從父節點中提取註疏列表（多層檢測）"""
    folder_title = parent_node.get("title", "")
    is_comm_folder = _folder_is_commentary_type(folder_title)

    all_sids = _extract_all_sutra_ids(parent_node)
    commentaries = []
    seen = set()
    for sid in all_sids:
        if sid == sutra_id or sid in seen:
            continue
        seen.add(sid)
        title = nav.catalog.get(sid, {}).get("title", "")
        if _is_commentary(title, sid, is_comm_folder):
            commentaries.append({"id": sid, "title": title})
    return commentaries


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API 端點
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/canon")
async def get_canon_tree(request: Request):
    """經藏目錄樹（T大正藏 → X卍續藏 → …）"""
    nav = request.app.state.nav
    if not nav:
        return JSONResponse([], status_code=200)
    return nav.get_canon_tree()


@router.get("/bulei")
async def get_bulei_tree(request: Request):
    """部類目錄樹（阿含部 → 般若部 → …）"""
    nav = request.app.state.nav
    if not nav:
        return JSONResponse([], status_code=200)
    return nav.get_bulei_tree()


@router.get("/bulei_siblings/{sutra_id}")
async def get_bulei_siblings(request: Request, sutra_id: str):
    """
    獲取經文的同部類註疏列表。

    多層檢測算法：
    1. 基礎關鍵詞（疏/鈔/註 等）→ 無條件生效
    2. 擴展複合詞（義疏/玄義/文句 等）→ 無條件生效
    3. ID 白名單（T1505-1535, T1693-1821 等）→ 無條件生效
    4. 寬鬆關鍵詞（解/釋/論 等）→ 僅註疏文件夾內 + 非原典經號
    5. 黑名單排除（語錄/全集 等）→ 優先排除
    6. 向上回退：直接父級無註疏時搜索祖父節點
    """
    nav = request.app.state.nav
    if not nav:
        return JSONResponse({
            "sutra_id": sutra_id,
            "group_title": "",
            "commentaries": [],
        })

    # 查找父節點及祖先鏈
    result = _find_with_ancestors(nav.bulei_tree, sutra_id)
    if not result:
        return JSONResponse({
            "sutra_id": sutra_id,
            "group_title": "",
            "commentaries": [],
        })

    parent, ancestors = result
    group_title = parent.get("title", "")
    commentaries = _get_commentaries(nav, sutra_id, parent)

    # 如果直接父級無註疏，嘗試向上一層（祖父節點）再搜索
    # 處理金剛經、法華經、心經等"譯本子文件夾"情況
    if not commentaries and ancestors:
        grandparent = ancestors[-1]
        group_title = grandparent.get("title", "")
        commentaries = _get_commentaries(nav, sutra_id, grandparent)

    return JSONResponse({
        "sutra_id": sutra_id,
        "group_title": group_title,
        "commentaries": commentaries,
    })
