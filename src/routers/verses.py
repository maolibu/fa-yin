"""
每日偈頌 API

提供偈頌列表查詢、用戶偈頌 CRUD、置頂設定等接口。
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.verses import (
    get_all_verses,
    get_daily_index,
    add_user_verse,
    delete_user_verse,
    get_user_prefs,
    save_user_prefs,
)

router = APIRouter(prefix="/api/verses", tags=["verses"])
log = logging.getLogger(__name__)


@router.get("", response_class=JSONResponse)
async def list_verses():
    """获取全部偈颂（内置 + 用户），以及今日索引"""
    all_v = get_all_verses()
    daily_idx = get_daily_index()
    prefs = get_user_prefs()
    return {
        "verses": all_v,
        "daily_index": daily_idx,
        "pinned_id": prefs.get("pinned_id"),
        "pinned_type": prefs.get("pinned_type"),
    }


@router.post("", response_class=JSONResponse)
async def create_verse(request: Request):
    """新增一条用户偈颂"""
    try:
        body = await request.json()
        lines = body.get("lines", [])
        source = body.get("source", "")

        if not lines or not source:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "detail": "偈頌正文和出處不可為空"}
            )

        # lines 如果是字符串，按换行拆分
        if isinstance(lines, str):
            lines = [l.strip() for l in lines.split("\n") if l.strip()]

        new_verse = add_user_verse(lines, source)
        return {"status": "ok", "verse": new_verse}
    except Exception as e:
        log.error(f"新增偈颂失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)}
        )


@router.delete("/{verse_id}", response_class=JSONResponse)
async def remove_verse(verse_id: int):
    """删除一条用户偈颂"""
    success = delete_user_verse(verse_id)
    if success:
        return {"status": "ok"}
    return JSONResponse(
        status_code=404,
        content={"status": "error", "detail": "偈頌不存在或非用戶自建"}
    )


@router.post("/pin", response_class=JSONResponse)
async def pin_verse(request: Request):
    """置顶一条偈颂为今日偈颂"""
    try:
        body = await request.json()
        verse_id = body.get("id")
        verse_type = body.get("type", "builtin")

        prefs = get_user_prefs()
        # 如果已经置顶的和请求的一样，则取消置顶
        if prefs.get("pinned_id") == verse_id and prefs.get("pinned_type") == verse_type:
            prefs.pop("pinned_id", None)
            prefs.pop("pinned_type", None)
            save_user_prefs(prefs)
            return {"status": "ok", "pinned": False}

        prefs["pinned_id"] = verse_id
        prefs["pinned_type"] = verse_type
        save_user_prefs(prefs)
        return {"status": "ok", "pinned": True}
    except Exception as e:
        log.error(f"置顶偈颂失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)}
        )
