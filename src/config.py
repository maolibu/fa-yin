"""
法印对照 · 跨平台路径配置

所有路径均使用 pathlib 动态拼接，零硬编码。
支持 .env 文件覆盖默认路径。
"""

import os
from pathlib import Path

# 尝试加载 .env 文件（如果存在 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ─── 项目根目录（launcher.py 所在位置） ─────────────────────
# src/config.py → 上一级就是项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─── src 目录（源代码所在位置） ───────────────────────────────
SRC_DIR = Path(__file__).resolve().parent

# ─── CBETA 原始数据（用户需自行下载） ────────────────────────
# 默认位于 data/raw/cbeta/，可通过环境变量覆盖
CBETA_BASE = Path(os.getenv(
    "CBETA_BASE",
    str(PROJECT_ROOT / "data" / "raw" / "cbeta")
))

# ─── 悉昙 GIF 图片目录（CBETA 悉昙字符渲染） ────────────────
SD_GIF_DIR = Path(os.getenv(
    "SD_GIF_DIR",
    str(CBETA_BASE / "sd-gif")
))

# ─── 组字数据（gaiji） ──────────────────────────────────────
GAIJI_PATH = Path(os.getenv(
    "GAIJI_PATH",
    str(PROJECT_ROOT / "data" / "raw" / "cbeta_gaiji.json")
))

# ─── 数据库目录 ──────────────────────────────────────────────
DB_DIR = Path(os.getenv(
    "DB_DIR",
    str(PROJECT_ROOT / "data" / "db")
))

# ─── CBETA 搜索数据库（ETL 生成，含简体列 + FTS5） ──────────
CBETA_SEARCH_DB = Path(os.getenv(
    "CBETA_SEARCH_DB",
    str(DB_DIR / "cbeta_search.db")
))
cbeta_search_available = CBETA_SEARCH_DB.exists()

# ─── 字典数据库 ──────────────────────────────────────────────
DICTS_DB = Path(os.getenv(
    "DICTS_DB",
    str(DB_DIR / "dicts.db")
))

# ─── 佛教拼音数据 ───────────────────────────────────────────
BUDDHIST_PINYIN_PATH = Path(os.getenv(
    "BUDDHIST_PINYIN_PATH",
    str(DB_DIR / "buddhist_pinyin.json")
))

# ─── 祖师法脉数据库 ──────────────────────────────────────────
LINEAGE_DB = Path(os.getenv(
    "LINEAGE_DB",
    str(DB_DIR / "lineage.db")
))

# ─── 内置数据（兼容旧代码引用） ──────────────────────────────
DATA_DIR = DB_DIR

# ─── 离线地图瓦片（可选，由 scripts/download_tiles.py 生成） ──
TILES_DIR = Path(os.getenv(
    "TILES_DIR",
    str(PROJECT_ROOT / "data" / "tiles")
))

# ─── 用户数据（运行时生成/修改） ─────────────────────────────
USER_DATA_DIR = Path(os.getenv(
    "USER_DATA_DIR",
    str(PROJECT_ROOT / "data" / "user_data")
))
FAVORITES_PATH = USER_DATA_DIR / "favorites.json"
FAVORITES_DEFAULT_PATH = DB_DIR / "favorites.default.json"
PREFERENCES_PATH = USER_DATA_DIR / "preferences.json"

# ─── 对照映射（经-疏对应） ───────────────────────────────────
COMMENTARY_MAP_DEFAULT = DB_DIR / "commentary_map.default.json"
COMMENTARY_MAP_USER = USER_DATA_DIR / "commentary_map.json"

# ─── 每日偈颂 ────────────────────────────────────────────────
VERSES_PATH = Path(os.getenv(
    "VERSES_PATH",
    str(DB_DIR / "verses.json")
))
USER_VERSES_PATH = USER_DATA_DIR / "user_verses.json"

# ─── 笔记导出 ────────────────────────────────────────────────
NOTES_DIR = USER_DATA_DIR / "notes"
OBSIDIAN_INBOX = os.getenv("OBSIDIAN_INBOX_PATH", "")

# ─── 静态资源与模板 ──────────────────────────────────────────
STATIC_DIR = SRC_DIR / "static"
TEMPLATES_DIR = SRC_DIR / "templates"

# ─── 运行时检测 ──────────────────────────────────────────────
cbeta_available = CBETA_BASE.exists() and (CBETA_BASE / "XML").exists()

# ─── 开发服务器 ──────────────────────────────────────────────
DEV_HOST = os.getenv("DEV_HOST", "0.0.0.0")
DEV_PORT = int(os.getenv("DEV_PORT", "8400"))

# ─── AI 释义（多 LLM 提供商） ────────────────────────────────
AI_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "name": "通义千问",
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
        "name": "SiliconFlow（硅基流动）",
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
        "name": "自定义",
        "base_url": "",
        "default_model": "",
        "no_key": False,
    },
}
AI_DEFAULT_KEY = os.getenv("AI_API_KEY", "")
AI_DEFAULT_PROVIDER = os.getenv("AI_DEFAULT_PROVIDER", "deepseek")


# ─── 路径摘要（调试用） ──────────────────────────────────────
def print_config():
    """打印当前路径配置，用于调试"""
    print("=" * 50)
    print("法印对照 · 路径配置")
    print("=" * 50)
    print(f"  项目根目录:    {PROJECT_ROOT}")
    print(f"  源代码目录:    {SRC_DIR}")
    print(f"  CBETA 数据:    {CBETA_BASE}  {'✓' if cbeta_available else '✗'}")
    print(f"  组字数据:      {GAIJI_PATH}  {'✓' if GAIJI_PATH.exists() else '✗'}")
    print(f"  数据库目录:    {DB_DIR}")
    print(f"  搜索数据库:    {CBETA_SEARCH_DB}  {'✓' if cbeta_search_available else '✗'}")
    print(f"  字典数据库:    {DICTS_DB}  {'✓' if DICTS_DB.exists() else '✗'}")
    print(f"  用户数据:      {USER_DATA_DIR}")
    print(f"  服务地址:      http://{DEV_HOST}:{DEV_PORT}")
    print("=" * 50)


if __name__ == "__main__":
    print_config()
