"""
對照映射 API
管理經文-註疏的映射關係。
默認映射來自 data/db/commentary_map.default.json，
用戶自定義覆蓋保存在 data/user_data/commentary_map.json。
"""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config

router = APIRouter(prefix="/api", tags=["commentary"])
log = logging.getLogger(__name__)

# 緩存默認映射（只讀，啟動時加載一次）
_default_map_cache = None


def _load_default_map() -> dict:
    """加載默認映射（帶緩存）"""
    global _default_map_cache
    if _default_map_cache is not None:
        return _default_map_cache
    if config.COMMENTARY_MAP_DEFAULT.exists():
        try:
            _default_map_cache = json.loads(
                config.COMMENTARY_MAP_DEFAULT.read_text(encoding="utf-8")
            )
            log.info(f"已加載默認對照映射：{len(_default_map_cache)} 條經文")
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"加載默認映射失敗: {e}")
            _default_map_cache = {}
    else:
        _default_map_cache = {}
    return _default_map_cache


def _load_user_map() -> dict:
    """加載用戶自定義映射"""
    if config.COMMENTARY_MAP_USER.exists():
        try:
            return json.loads(
                config.COMMENTARY_MAP_USER.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_user_map(data: dict):
    """保存用戶自定義映射"""
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.COMMENTARY_MAP_USER.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.get("/commentary/{sutra_id}")
async def get_commentaries(sutra_id: str):
    """
    獲取某經文的註疏列表。
    優先返回用戶自定義版本，沒有則返回默認映射。
    """
    user_map = _load_user_map()
    if sutra_id in user_map:
        entry = user_map[sutra_id]
        return {
            "sutra_id": sutra_id,
            "title": entry.get("title", ""),
            "commentaries": entry.get("commentaries", []),
            "source": "user",
        }

    default_map = _load_default_map()
    if sutra_id in default_map:
        entry = default_map[sutra_id]
        return {
            "sutra_id": sutra_id,
            "title": entry.get("title", ""),
            "commentaries": entry.get("commentaries", []),
            "source": "default",
        }

    return {
        "sutra_id": sutra_id,
        "title": "",
        "commentaries": [],
        "source": "none",
    }


@router.put("/commentary/{sutra_id}")
async def save_commentaries(sutra_id: str, request: Request):
    """
    保存用戶自定義註疏列表（僅覆蓋該經文的部分）。
    請求體格式：{ "title": "...", "commentaries": [...] }
    """
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(
                {"ok": False, "error": "無效的數據格式"}, status_code=400
            )
        user_map = _load_user_map()
        user_map[sutra_id] = {
            "title": body.get("title", ""),
            "commentaries": body.get("commentaries", []),
        }
        _save_user_map(user_map)
        return {"ok": True, "source": "user"}
    except Exception as e:
        log.error(f"保存註疏失敗: {e}")
        return JSONResponse(
            {"ok": False, "error": str(e)}, status_code=500
        )


@router.delete("/commentary/{sutra_id}")
async def reset_commentaries(sutra_id: str):
    """
    刪除用戶對該經文的自定義註疏，恢復為默認映射。
    """
    user_map = _load_user_map()
    if sutra_id in user_map:
        del user_map[sutra_id]
        if user_map:
            _save_user_map(user_map)
        else:
            # 用戶映射為空，刪除文件
            try:
                config.COMMENTARY_MAP_USER.unlink()
            except OSError:
                pass
        return {"ok": True, "restored": True}
    return {"ok": True, "restored": False}
