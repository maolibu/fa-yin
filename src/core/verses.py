"""
法印對照 · 每日偈頌

從 JSON 文件加載偈頌庫（系統內置 + 用戶自建），
提供每日偈頌選取、翻頁、用戶 CRUD 功能。
"""

import json
import logging
from datetime import date
from pathlib import Path

import config

log = logging.getLogger(__name__)


def _load_json(path: Path) -> list:
    """安全加载 JSON 列表文件"""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        log.error(f"加载偈颂文件失败 {path}: {e}")
        return []


def _save_user_verses(verses: list):
    """保存用户偈颂到 JSON"""
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.USER_VERSES_PATH.write_text(
        json.dumps(verses, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_system_verses() -> list:
    """获取系统内置偈颂（从 data/db/verses.json）"""
    verses = _load_json(config.VERSES_PATH)
    for v in verses:
        v["type"] = "builtin"
    return verses


def get_user_verses() -> list:
    """获取用户自建偈颂"""
    verses = _load_json(config.USER_VERSES_PATH)
    for v in verses:
        v["type"] = "custom"
    return verses


def get_all_verses() -> list:
    """合并内置和用户偈颂，用户的排在末尾"""
    return get_system_verses() + get_user_verses()


def get_user_prefs() -> dict:
    """读取偈颂相关的用户偏好（置顶等）"""
    if not config.USER_VERSES_PATH.exists():
        return {}
    try:
        # 偏好存储在 user_verses.json 同级的 verse_prefs.json
        prefs_path = config.USER_DATA_DIR / "verse_prefs.json"
        if prefs_path.exists():
            return json.loads(prefs_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_user_prefs(prefs: dict):
    """保存偈颂偏好"""
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    prefs_path = config.USER_DATA_DIR / "verse_prefs.json"
    prefs_path.write_text(
        json.dumps(prefs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_daily_verse() -> dict:
    """
    每日一偈：按日期自动轮换。
    如果用户有置顶偈颂，优先返回置顶的。
    """
    all_verses = get_all_verses()
    if not all_verses:
        return {"id": 0, "lines": ["法門無量誓願學"], "source": "四弘誓願", "type": "builtin"}

    # 检查用户置顶
    prefs = get_user_prefs()
    pinned_id = prefs.get("pinned_id")
    pinned_type = prefs.get("pinned_type")

    if pinned_id is not None:
        for v in all_verses:
            if v.get("id") == pinned_id and v.get("type") == pinned_type:
                return v

    # 按年内天数轮换（1月1日=第1条，闰年12月31日回到第1条）
    index = (date.today().timetuple().tm_yday - 1) % len(all_verses)
    return all_verses[index]


def get_daily_index() -> int:
    """获取今日偈颂在合并列表中的索引"""
    all_verses = get_all_verses()
    if not all_verses:
        return 0

    prefs = get_user_prefs()
    pinned_id = prefs.get("pinned_id")
    pinned_type = prefs.get("pinned_type")

    if pinned_id is not None:
        for i, v in enumerate(all_verses):
            if v.get("id") == pinned_id and v.get("type") == pinned_type:
                return i

    # 按年内天数轮换（与 get_daily_verse 保持一致）
    return (date.today().timetuple().tm_yday - 1) % len(all_verses)


def add_user_verse(lines: list, source: str) -> dict:
    """添加一条用户偈颂，返回新偈颂"""
    user_verses = _load_json(config.USER_VERSES_PATH)
    # 生成 ID：从 10001 开始避免和系统偈颂冲突
    max_id = max((v.get("id", 10000) for v in user_verses), default=10000)
    new_verse = {
        "id": max_id + 1,
        "lines": lines,
        "source": source,
    }
    user_verses.append(new_verse)
    _save_user_verses(user_verses)
    new_verse["type"] = "custom"
    return new_verse


def delete_user_verse(verse_id: int) -> bool:
    """删除一条用户偈颂"""
    user_verses = _load_json(config.USER_VERSES_PATH)
    original_len = len(user_verses)
    user_verses = [v for v in user_verses if v.get("id") != verse_id]
    if len(user_verses) == original_len:
        return False
    _save_user_verses(user_verses)

    # 如果删除的偈颂正好是置顶的，取消置顶
    prefs = get_user_prefs()
    if prefs.get("pinned_id") == verse_id and prefs.get("pinned_type") == "custom":
        prefs.pop("pinned_id", None)
        prefs.pop("pinned_type", None)
        save_user_prefs(prefs)

    return True
