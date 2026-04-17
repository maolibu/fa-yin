"""
收藏夾 CRUD API
管理 user_data/favorites.json，提供讀寫接口。
"""

import json
import shutil
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config

router = APIRouter(prefix="/api", tags=["favorites"])
log = logging.getLogger(__name__)


def _ensure_favorites():
    """確保 favorites.json 存在（首次啟動時從 default 複製）"""
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not config.FAVORITES_PATH.exists():
        if config.FAVORITES_DEFAULT_PATH.exists():
            shutil.copy2(config.FAVORITES_DEFAULT_PATH, config.FAVORITES_PATH)
            log.info("已從 favorites.default.json 初始化 favorites.json")
        else:
            # 連 default 都沒有，寫一個空數組
            config.FAVORITES_PATH.write_text("[]", encoding="utf-8")
            log.info("已創建空 favorites.json")


@router.get("/favorites", response_class=JSONResponse)
async def get_favorites():
    """讀取收藏夾"""
    _ensure_favorites()
    try:
        data = json.loads(config.FAVORITES_PATH.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        log.error(f"讀取 favorites.json 失敗: {e}")
        return []


@router.put("/favorites", response_class=JSONResponse)
async def save_favorites(request: Request):
    """保存收藏夾（全量替換）"""
    _ensure_favorites()
    try:
        data = await request.json()
        config.FAVORITES_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return {"status": "ok", "count": len(data)}
    except Exception as e:
        log.error(f"保存 favorites.json 失敗: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)}
        )


@router.post("/favorites/reset", response_class=JSONResponse)
async def reset_favorites():
    """重置收藏夾為默認配置"""
    try:
        if config.FAVORITES_DEFAULT_PATH.exists():
            shutil.copy2(config.FAVORITES_DEFAULT_PATH, config.FAVORITES_PATH)
            data = json.loads(config.FAVORITES_PATH.read_text(encoding="utf-8"))
            log.info("已重置收藏夾為默認配置")
            return {"status": "ok", "count": len(data)}
        else:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "detail": "默認配置文件不存在"}
            )
    except Exception as e:
        log.error(f"重置 favorites 失敗: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)}
        )
