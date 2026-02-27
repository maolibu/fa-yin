"""
对照映射 API
管理经文-注疏的映射关系。
默认映射来自 data/db/commentary_map.default.json，
用户自定义覆盖保存在 data/user_data/commentary_map.json。
"""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config

router = APIRouter(prefix="/api", tags=["commentary"])
log = logging.getLogger(__name__)

# 缓存默认映射（只读，启动时加载一次）
_default_map_cache = None


def _load_default_map() -> dict:
    """加载默认映射（带缓存）"""
    global _default_map_cache
    if _default_map_cache is not None:
        return _default_map_cache
    if config.COMMENTARY_MAP_DEFAULT.exists():
        try:
            _default_map_cache = json.loads(
                config.COMMENTARY_MAP_DEFAULT.read_text(encoding="utf-8")
            )
            log.info(f"已加载默认对照映射：{len(_default_map_cache)} 条经文")
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"加载默认映射失败: {e}")
            _default_map_cache = {}
    else:
        _default_map_cache = {}
    return _default_map_cache


def _load_user_map() -> dict:
    """加载用户自定义映射"""
    if config.COMMENTARY_MAP_USER.exists():
        try:
            return json.loads(
                config.COMMENTARY_MAP_USER.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_user_map(data: dict):
    """保存用户自定义映射"""
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.COMMENTARY_MAP_USER.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.get("/commentary/{sutra_id}")
async def get_commentaries(sutra_id: str):
    """
    获取某经文的注疏列表。
    优先返回用户自定义版本，没有则返回默认映射。
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
    保存用户自定义注疏列表（仅覆盖该经文的部分）。
    请求体格式：{ "title": "...", "commentaries": [...] }
    """
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(
                {"ok": False, "error": "无效的数据格式"}, status_code=400
            )
        user_map = _load_user_map()
        user_map[sutra_id] = {
            "title": body.get("title", ""),
            "commentaries": body.get("commentaries", []),
        }
        _save_user_map(user_map)
        return {"ok": True, "source": "user"}
    except Exception as e:
        log.error(f"保存注疏失败: {e}")
        return JSONResponse(
            {"ok": False, "error": str(e)}, status_code=500
        )


@router.delete("/commentary/{sutra_id}")
async def reset_commentaries(sutra_id: str):
    """
    删除用户对该经文的自定义注疏，恢复为默认映射。
    """
    user_map = _load_user_map()
    if sutra_id in user_map:
        del user_map[sutra_id]
        if user_map:
            _save_user_map(user_map)
        else:
            # 用户映射为空，删除文件
            try:
                config.COMMENTARY_MAP_USER.unlink()
            except OSError:
                pass
        return {"ok": True, "restored": True}
    return {"ok": True, "restored": False}
