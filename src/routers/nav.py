"""
导航目录 API — 贝阙区（全藏目录浏览）

将 cbeta_nav.py 的部类/经藏目录树暴露为 JSON API。
包含动态同部类注疏提取接口。
"""

import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/nav", tags=["导航"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 多层注疏检测配置
#
# 策略：基础关键词 + 扩展复合词 + ID 白名单
#     + 宽松关键词（仅注疏文件夹内且非原典经号）
#     + 黑名单排除
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 第1层：基础单字关键词（高精度，任何场景都启用）
_BASE_KEYWORDS = ("疏", "鈔", "註", "注", "箋", "抄", "科")

# 第2层：扩展复合词（高精度，任何场景都启用）
_COMPOUND_KEYWORDS = (
    # 疏类
    "義疏", "略疏", "新疏", "通疏", "正脈疏",
    # 解类
    "直解", "集解", "要解", "合解", "會解", "類解",
    "略解", "淺解", "正解", "易解", "論解",
    "句解", "節解",
    # 说类
    "直說", "郢說", "肤說", "闡說", "請益說",
    # 记类
    "述記", "義記", "翼記", "經記", "法記",
    "私記", "宗圓記", "復古記",
    # 义类
    "玄義", "會義", "義章", "通義",
    "如是經義", "分齊章",
    # 科类
    "科判", "科文", "科釋", "科註", "科節",
    # 注类
    "箋要", "箋註", "集註", "集釋", "纂註",
    # 讲习类
    "講義", "講記", "講錄", "講述",
    # 论释类
    "釋論", "論釋",
    # 贊类
    "幽贊", "玄贊", "述贊", "通贊", "旨贊",
    # 述/抄类
    "還源述", "義述",
    # 音义/指南/纲要类
    "音義", "音釋", "懸談",
    "指南", "指歸", "綱要", "綱目",
    "宗通", "宗要", "會本",
    "提綱", "要旨", "文句",
    # 镜/览类
    "玄鏡", "懸鏡",
    "節要", "釋要", "纂要",
    "備覽", "要覽",
    # 大意/纶贯/直指/秘录类
    "大意", "綸貫", "直指", "秘錄",
    "撮要", "會元",
    # 口诀/演义/贯义/部旨等
    "口訣", "演義", "貫義", "部旨",
    "旨槩", "大略", "示珠指",
    # 自查发现的注疏体裁词
    "正眼", "發隱", "彙纂", "決疑",
    "采微", "添足", "指掌", "開度", "際決",
    "知音", "擊節", "大窾", "授手",
    "演古", "訂義", "備撿", "玄籤",
    "隨釋", "備釋",
    "傳弘決", "搜要",
    "發微錄", "顯性錄",
    "披雲集", "吞海集",
    # 用户第5轮确认
    "義解", "釋義", "關法",
    # 律部注释
    "毘婆沙", "事義",
)

# 第3层：宽松关键词（仅在注疏文件夹内且经号非原典区时生效）
# 「說」回归：有经号守卫保护，T0001-T1420 的「佛說X經」不会误匹配
_LOOSE_KEYWORDS = ("解", "釋", "論", "說", "述", "贊", "記", "談")

# 第4层：黑名单（即使其他层命中也强制排除）
_BLACKLIST = (
    "語錄", "全集", "詩集", "年譜", "行狀",
    "碑文", "塔銘", "造像記",
    "懺法", "懺儀", "禮懺", "禮讚",
)


def _is_likely_original(sid: str, title: str = "") -> bool:
    """判断是否可能是原典（非注疏），用于限制宽松关键词的生效范围。
    
    满足以下任一条件即视为原典：
    1. 大正藏经号在 T0001-T1420（经律原典区）
    2. 标题以「經」结尾（任何藏的经典通常如此）
    """
    # 条件1：大正藏原典区
    m = re.match(r"T(\d+)", sid)
    if m and int(m.group(1)) <= 1420:
        return True
    # 条件2：标题以經结尾
    clean = re.sub(r"[\(（].*?[\)）]", "", title).strip()
    if clean.endswith("經"):
        return True
    return False


def _is_whitelist_id(sid: str) -> bool:
    """判断经号是否在大正藏注疏/释论区。
    T1505-1535: 释经论 (大正藏卷25)
    T1693-1821: 经疏部+论疏部 (大正藏卷33-40)
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
    """判断文件夹标题是否标记为注疏类型（含疏/論/註等字）"""
    hints = ("疏", "論", "註", "注", "釋", "解", "科", "記", "贊", "鈔")
    return any(h in title for h in hints)


def _is_commentary(title: str, sid: str = "",
                    folder_is_commentary: bool = False) -> bool:
    """多层注疏检测。

    Args:
        title: 经文标题
        sid: 经文编号（如 T1700）
        folder_is_commentary: 该经文所在文件夹是否为注疏型
    """
    if not title:
        return False

    # 黑名单优先排除
    for bk in _BLACKLIST:
        if bk in title:
            return False

    # 判断标题是否以「經」结尾（经典而非注疏）
    clean_title = re.sub(r"[\(（].*?[\)）]", "", title).strip()
    title_ends_jing = clean_title.endswith("經")

    # 第1层：基础关键词（即使以經结尾也生效，如「注維摩詰經」）
    for kw in _BASE_KEYWORDS:
        if kw in title:
            return True

    # 以經结尾的标题：跳过复合词和宽松词（防止「大意經」「決疑經」误判）
    # 只允许基础关键词和 ID 白名单命中
    if title_ends_jing:
        return _is_whitelist_id(sid)

    # 第2层：扩展复合词
    for kw in _COMPOUND_KEYWORDS:
        if kw in title:
            return True

    # 第3层：ID 白名单（大正藏注疏区经号）
    if _is_whitelist_id(sid):
        return True

    # 第4层：宽松关键词（仅在注疏文件夹内 + 非原典时生效）
    if folder_is_commentary and not _is_likely_original(sid, title):
        for kw in _LOOSE_KEYWORDS:
            if kw in title:
                return True

    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 树遍历工具函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_all_sutra_ids(node: dict) -> list[str]:
    """递归提取节点下所有 sutra_id"""
    results = []
    sid = node.get("sutra_id")
    if sid:
        results.append(sid)
    for child in node.get("children", []):
        results.extend(_extract_all_sutra_ids(child))
    return results


def _find_with_ancestors(nodes: list[dict], target_id: str, ancestors=None):
    """查找 target_id，同时记录祖先路径"""
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
    """从父节点中提取注疏列表（多层检测）"""
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
# API 端点
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/canon")
async def get_canon_tree(request: Request):
    """经藏目录树（T大正藏 → X卍续藏 → …）"""
    nav = request.app.state.nav
    if not nav:
        return JSONResponse([], status_code=200)
    return nav.get_canon_tree()


@router.get("/bulei")
async def get_bulei_tree(request: Request):
    """部类目录树（阿含部 → 般若部 → …）"""
    nav = request.app.state.nav
    if not nav:
        return JSONResponse([], status_code=200)
    return nav.get_bulei_tree()


@router.get("/bulei_siblings/{sutra_id}")
async def get_bulei_siblings(request: Request, sutra_id: str):
    """
    获取经文的同部类注疏列表。

    多层检测算法：
    1. 基础关键词（疏/鈔/註 等）→ 无条件生效
    2. 扩展复合词（義疏/玄義/文句 等）→ 无条件生效
    3. ID 白名单（T1505-1535, T1693-1821 等）→ 无条件生效
    4. 宽松关键词（解/釋/論 等）→ 仅注疏文件夹内 + 非原典经号
    5. 黑名单排除（語錄/全集 等）→ 优先排除
    6. 向上回退：直接父级无注疏时搜索祖父节点
    """
    nav = request.app.state.nav
    if not nav:
        return JSONResponse({
            "sutra_id": sutra_id,
            "group_title": "",
            "commentaries": [],
        })

    # 查找父节点及祖先链
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

    # 如果直接父级无注疏，尝试向上一层（祖父节点）再搜索
    # 处理金刚经、法华经、心经等"译本子文件夹"情况
    if not commentaries and ancestors:
        grandparent = ancestors[-1]
        group_title = grandparent.get("title", "")
        commentaries = _get_commentaries(nav, sutra_id, grandparent)

    return JSONResponse({
        "sutra_id": sutra_id,
        "group_title": group_title,
        "commentaries": commentaries,
    })
