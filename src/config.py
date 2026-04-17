"""
法印對照 · 跨平臺路徑配置

所有路徑均使用 pathlib 動態拼接，零硬編碼。
支持 .env 文件覆蓋默認路徑。
"""

import os
from pathlib import Path

# 嘗試加載 .env 文件（如果存在 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ─── 應用版本與標識 ───────────────────────────────────────────
APP_NAME = "法印對照"
APP_SUBTITLE = "整合閱讀平臺"
APP_TITLE = f"{APP_NAME} · {APP_SUBTITLE}"
APP_VERSION = os.getenv("APP_VERSION", "1.1.0")
APP_VERSION_DISPLAY = f"v{APP_VERSION}"

# ─── 項目根目錄（launcher.py 所在位置） ─────────────────────
# src/config.py → 上一級就是項目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─── src 目錄（源代碼所在位置） ───────────────────────────────
SRC_DIR = Path(__file__).resolve().parent

# ─── CBETA 原始數據（用戶需自行下載） ────────────────────────
# 默認位於 data/raw/cbeta/，可通過環境變量覆蓋
CBETA_BASE = Path(os.getenv(
    "CBETA_BASE",
    str(PROJECT_ROOT / "data" / "raw" / "cbeta")
))

# ─── 悉曇 GIF 圖片目錄（CBETA 悉曇字符渲染） ────────────────
SD_GIF_DIR = Path(os.getenv(
    "SD_GIF_DIR",
    str(CBETA_BASE / "sd-gif")
))

# ─── 組字數據（gaiji） ──────────────────────────────────────
GAIJI_PATH = Path(os.getenv(
    "GAIJI_PATH",
    str(PROJECT_ROOT / "data" / "raw" / "cbeta_gaiji.json")
))

# ─── 數據庫目錄 ──────────────────────────────────────────────
DB_DIR = Path(os.getenv(
    "DB_DIR",
    str(PROJECT_ROOT / "data" / "db")
))

# ─── CBETA 搜索數據庫（ETL 生成，含簡體列 + FTS5） ──────────
CBETA_SEARCH_DB = Path(os.getenv(
    "CBETA_SEARCH_DB",
    str(DB_DIR / "cbeta_search.db")
))
cbeta_search_available = CBETA_SEARCH_DB.exists()

# ─── 字典數據庫 ──────────────────────────────────────────────
DICTS_DB = Path(os.getenv(
    "DICTS_DB",
    str(DB_DIR / "dicts.db")
))

# ─── 佛教拼音數據 ───────────────────────────────────────────
BUDDHIST_PINYIN_PATH = Path(os.getenv(
    "BUDDHIST_PINYIN_PATH",
    str(DB_DIR / "buddhist_pinyin.json")
))

# ─── 祖師法脈數據庫 ──────────────────────────────────────────
LINEAGE_DB = Path(os.getenv(
    "LINEAGE_DB",
    str(DB_DIR / "lineage.db")
))

# ─── 內置數據（兼容舊代碼引用） ──────────────────────────────
DATA_DIR = DB_DIR

# ─── 離線地圖瓦片（可選，由 scripts/download_tiles.py 生成） ──
TILES_DIR = Path(os.getenv(
    "TILES_DIR",
    str(PROJECT_ROOT / "data" / "tiles")
))

# ─── 用戶數據（運行時生成/修改） ─────────────────────────────
USER_DATA_DIR = Path(os.getenv(
    "USER_DATA_DIR",
    str(PROJECT_ROOT / "data" / "user_data")
))
FAVORITES_PATH = USER_DATA_DIR / "favorites.json"
FAVORITES_DEFAULT_PATH = DB_DIR / "favorites.default.json"
PREFERENCES_PATH = USER_DATA_DIR / "preferences.json"

# ─── 對照映射（經-疏對應） ───────────────────────────────────
COMMENTARY_MAP_DEFAULT = DB_DIR / "commentary_map.default.json"
COMMENTARY_MAP_USER = USER_DATA_DIR / "commentary_map.json"

# ─── 每日偈頌 ────────────────────────────────────────────────
VERSES_PATH = Path(os.getenv(
    "VERSES_PATH",
    str(DB_DIR / "verses.json")
))
USER_VERSES_PATH = USER_DATA_DIR / "user_verses.json"

# ─── 筆記導出 ────────────────────────────────────────────────
NOTES_DIR = USER_DATA_DIR / "notes"
OBSIDIAN_INBOX = os.getenv("OBSIDIAN_INBOX_PATH", "")

# ─── 靜態資源與模板 ──────────────────────────────────────────
STATIC_DIR = SRC_DIR / "static"
TEMPLATES_DIR = SRC_DIR / "templates"

# ─── 運行時檢測 ──────────────────────────────────────────────
cbeta_available = CBETA_BASE.exists() and (CBETA_BASE / "XML").exists()

# ─── 開發服務器 ──────────────────────────────────────────────
DEV_HOST = os.getenv("DEV_HOST", "0.0.0.0")
DEV_PORT = int(os.getenv("DEV_PORT", "8400"))

# ─── AI 釋義（多 LLM 提供商） ────────────────────────────────
AI_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "name": "通義千問",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    "gemini": {
        "name": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
    },
    "claude": {
        "name": "Claude",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-latest",
    },
    "siliconflow": {
        "name": "SiliconFlow（硅基流動）",
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-70b-versatile",
    },
    "ollama": {
        "name": "Ollama（本地）",
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5",
        "no_key": True,
    },
    "custom": {
        "name": "自定義",
        "base_url": "",
        "default_model": "",
        "no_key": False,
    },
}
AI_DEFAULT_KEY = os.getenv("AI_API_KEY", "")
AI_DEFAULT_PROVIDER = os.getenv("AI_DEFAULT_PROVIDER", "deepseek")


# ─── 路徑摘要（調試用） ──────────────────────────────────────
def print_config():
    """打印當前路徑配置，用於調試"""
    from core.runtime_status import check_search_db, check_dict_db, check_lineage_db

    search_status = check_search_db(CBETA_SEARCH_DB)
    dict_status = check_dict_db(DICTS_DB)
    lineage_status = check_lineage_db(LINEAGE_DB)

    print("=" * 50)
    print(f"{APP_TITLE}  {APP_VERSION_DISPLAY}")
    print("=" * 50)
    print(f"  項目根目錄:    {PROJECT_ROOT}")
    print(f"  源代碼目錄:    {SRC_DIR}")
    print(f"  CBETA 數據:    {CBETA_BASE}  {'✓' if cbeta_available else '✗'}")
    print(f"  組字數據:      {GAIJI_PATH}  {'✓' if GAIJI_PATH.exists() else '✗'}")
    print(f"  數據庫目錄:    {DB_DIR}")
    print(f"  搜索數據庫:    {CBETA_SEARCH_DB}  {'✓' if search_status['ok'] else '✗'}")
    print(f"  字典數據庫:    {DICTS_DB}  {'✓' if dict_status['ok'] else '✗'}")
    print(f"  法脈數據庫:    {LINEAGE_DB}  {'✓' if lineage_status['ok'] else '✗'}")
    print(f"  用戶數據:      {USER_DATA_DIR}")
    print(f"  服務地址:      http://{DEV_HOST}:{DEV_PORT}")
    print("=" * 50)


if __name__ == "__main__":
    print_config()
