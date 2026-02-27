"""
用户数据管理 API
提供用户数据（收藏、笔记、设置、偏好）的导出与管理功能。
"""
import json
import shutil
import zipfile
import tempfile
import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
import config

router = APIRouter(prefix="/api/user_data", tags=["user_data"])

# 用户偏好文件路径
PREFERENCES_PATH = config.USER_DATA_DIR / "preferences.json"


def remove_file(path: str):
    try:
        os.remove(path)
    except Exception:
        pass


def _read_preferences() -> dict:
    """读取用户偏好文件"""
    if PREFERENCES_PATH.exists():
        try:
            return json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_preferences(data: dict):
    """写入用户偏好文件"""
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREFERENCES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============================================================
# 用户偏好 API
# ============================================================

@router.get("/preferences")
async def get_preferences():
    """
    获取用户偏好（阅读设置、AI 配置、对照经文配置）。
    返回完整的 preferences.json 内容。
    """
    return _read_preferences()


@router.put("/preferences")
async def save_preferences(request: Request):
    """
    保存用户偏好（全量覆盖）。
    前端发送完整的 preferences 对象。
    """
    body = await request.json()
    # 基本校验：只接受 dict 类型，限制大小（防滥用）
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "无效的数据格式"}, status_code=400)
    raw = json.dumps(body, ensure_ascii=False)
    if len(raw) > 1_000_000:  # 1MB 上限
        return JSONResponse({"ok": False, "error": "数据过大"}, status_code=400)
    _write_preferences(body)
    return {"ok": True}


@router.patch("/preferences")
async def patch_preferences(request: Request):
    """
    局部更新用户偏好（合并模式）。
    只更新传入的顶层 key，不影响其他 key。
    适合单独保存某一类设置，如只更新 compare 数据。
    """
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "无效的数据格式"}, status_code=400)
    current = _read_preferences()
    current.update(body)
    raw = json.dumps(current, ensure_ascii=False)
    if len(raw) > 1_000_000:
        return JSONResponse({"ok": False, "error": "数据过大"}, status_code=400)
    _write_preferences(current)
    return {"ok": True}


# ============================================================
# 数据导出 API
# ============================================================

@router.get("/export")
async def export_user_data(background_tasks: BackgroundTasks):
    """导出所有用户数据（打包下载 user_data 目录）"""

    # 确保 user_data 目录存在
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 创建临时 zip 文件
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    try:
        # 打包 user_data 目录
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(config.USER_DATA_DIR):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(config.USER_DATA_DIR)
                    zipf.write(file_path, arcname)

        filename = f"fjlsc_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        background_tasks.add_task(remove_file, temp_zip_path)

        return FileResponse(
            path=temp_zip_path,
            filename=filename,
            media_type="application/zip",
        )

    except Exception as e:
        remove_file(temp_zip_path)
        raise
