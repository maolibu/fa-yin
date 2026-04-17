"""
用戶數據管理 API
提供用戶數據（收藏、筆記、設置、偏好）的導出與管理功能。
"""
import json
import zipfile
import tempfile
import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
import config

router = APIRouter(prefix="/api/user_data", tags=["user_data"])

# 用戶偏好文件路徑
PREFERENCES_PATH = config.USER_DATA_DIR / "preferences.json"


def _error(message: str, status_code: int = 400):
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


def remove_file(path: str):
    try:
        os.remove(path)
    except Exception:
        pass


def _read_preferences() -> dict:
    """讀取用戶偏好文件"""
    if PREFERENCES_PATH.exists():
        try:
            return json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_preferences(data: dict):
    """寫入用戶偏好文件"""
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREFERENCES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _read_json_body(request: Request):
    try:
        return await request.json()
    except Exception:
        return None


# ============================================================
# 用戶偏好 API
# ============================================================

@router.get("/preferences")
async def get_preferences():
    """
    獲取用戶偏好（閱讀設置、AI 配置、對照經文配置）。
    返回完整的 preferences.json 內容。
    """
    return _read_preferences()


@router.put("/preferences")
async def save_preferences(request: Request):
    """
    保存用戶偏好（全量覆蓋）。
    前端發送完整的 preferences 對象。
    """
    body = await _read_json_body(request)
    # 基本校驗：只接受 dict 類型，限制大小（防濫用）
    if not isinstance(body, dict):
        return _error("無效的數據格式")
    raw = json.dumps(body, ensure_ascii=False)
    if len(raw) > 1_000_000:  # 1MB 上限
        return _error("數據過大")
    try:
        _write_preferences(body)
    except OSError as exc:
        return _error(f"寫入偏好失敗：{exc}", status_code=500)
    return {"ok": True}


@router.patch("/preferences")
async def patch_preferences(request: Request):
    """
    局部更新用戶偏好（合併模式）。
    只更新傳入的頂層 key，不影響其他 key。
    適合單獨保存某一類設置，如只更新 compare 數據。
    """
    body = await _read_json_body(request)
    if not isinstance(body, dict):
        return _error("無效的數據格式")
    current = _read_preferences()
    current.update(body)
    raw = json.dumps(current, ensure_ascii=False)
    if len(raw) > 1_000_000:
        return _error("數據過大")
    try:
        _write_preferences(current)
    except OSError as exc:
        return _error(f"寫入偏好失敗：{exc}", status_code=500)
    return {"ok": True}


# ============================================================
# 數據導出 API
# ============================================================

@router.get("/export")
async def export_user_data(background_tasks: BackgroundTasks):
    """導出所有用戶數據（打包下載 user_data 目錄）"""

    # 確保 user_data 目錄存在
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 創建臨時 zip 文件
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    try:
        # 打包 user_data 目錄
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(config.USER_DATA_DIR):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(config.USER_DATA_DIR)
                    zipf.write(file_path, arcname)

        filename = f"fa_yin_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        background_tasks.add_task(remove_file, temp_zip_path)

        return FileResponse(
            path=temp_zip_path,
            filename=filename,
            media_type="application/zip",
        )

    except Exception as exc:
        remove_file(temp_zip_path)
        return _error(f"導出用戶數據失敗：{exc}", status_code=500)
