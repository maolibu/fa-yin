"""
法印对照 · FastAPI 主程序

整合经文阅读、法脉图谱、字典查询的一站式佛经研习平台。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import shutil
import os

import config
from routers import search, favorites, reader, nav, lineage

# ─── 日志 ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ─── 应用 ─────────────────────────────────────────────────────
app = FastAPI(title="法印对照 · 整合阅读平台", version="0.1.0")

# 静态文件和模板
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

# 悉昙 GIF 图片（CBETA 梵文字符渲染）
if config.SD_GIF_DIR.exists():
    app.mount("/sd-gif", StaticFiles(directory=str(config.SD_GIF_DIR)), name="sd-gif")

# 离线地图瓦片（可选）
if config.TILES_DIR.exists():
    app.mount("/tiles", StaticFiles(directory=str(config.TILES_DIR)), name="tiles")
    log.info(f"  离线地图瓦片: {config.TILES_DIR} ✓")

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))

# 将 templates 存储到 app.state，供路由模块访问
app.state.templates = templates

# ─── 注册路由 ─────────────────────────────────────────────────
app.include_router(search.router)
app.include_router(favorites.router)
app.include_router(reader.router)
app.include_router(nav.router)
app.include_router(lineage.router)

# 笔记 API
from routers import notes
app.include_router(notes.router)

# 用户数据管理 API（导出）
from routers import user_data
app.include_router(user_data.router)

# 字典 API
from routers import dict_lookup
app.include_router(dict_lookup.router)

# AI 释义 API
from routers import ai_assistant
app.include_router(ai_assistant.router)

# 每日偈颂 API
from routers import verses as verses_router
app.include_router(verses_router.router)

# 对照映射 API
from routers import commentary
app.include_router(commentary.router)


# ─── 数据迁移 ────────────────────────────────────────────────
@app.on_event("startup")
async def migrate_user_data():
    """迁移旧版数据到 user_data 目录"""
    # 1. 迁移笔记 (exported_notes -> data/user_data/notes)
    old_notes_dir = config.SRC_DIR / "exported_notes"
    if old_notes_dir.exists() and old_notes_dir.is_dir():
        log.info(f"发现旧版笔记目录 {old_notes_dir}，正在迁移至 {config.NOTES_DIR}...")
        config.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for item in old_notes_dir.iterdir():
            if item.is_file() and item.name.endswith(".md"):
                target = config.NOTES_DIR / item.name
                if not target.exists():
                    shutil.move(str(item), str(target))
                    count += 1
        log.info(f"成功迁移 {count} 个笔记文件")
        
        # 尝试删除空目录
        try:
            # 检查目录是否为空（忽略 .DS_Store 等）
            has_files = False
            for f in old_notes_dir.iterdir():
                if f.name != ".DS_Store":
                    has_files = True
                    break
            if not has_files:
                shutil.rmtree(old_notes_dir)
                log.info("已删除旧版笔记目录")
        except Exception as e:
            log.warning(f"删除旧版笔记目录失败: {e}")


# ─── 初始化核心模块（在 startup 事件中执行，确保数据就绪） ────
app.state.nav = None
app.state.parser = None

@app.on_event("startup")
async def init_core_modules():
    """启动时初始化 CBETA 核心模块（实时检查数据是否存在）"""
    cbeta_ready = config.CBETA_BASE.exists() and (config.CBETA_BASE / "XML").exists()
    if cbeta_ready:
        try:
            from core.cbeta_nav import CBETANav
            from core.cbeta_parser import CBETAParser

            nav_instance = CBETANav(str(config.CBETA_BASE))
            parser_instance = CBETAParser(
                cbeta_dir=str(config.CBETA_BASE),
                gaiji_path=str(config.GAIJI_PATH),
                nav=nav_instance,
            )
            app.state.nav = nav_instance
            app.state.parser = parser_instance
            log.info(f"CBETANav + CBETAParser 初始化成功，共 {len(nav_instance.catalog)} 部经文")
        except Exception as e:
            log.error(f"核心模块初始化失败: {e}")
    else:
        log.warning(f"CBETA 数据未找到 ({config.CBETA_BASE})，搜索和阅读功能不可用")


# ─── 页面路由 ─────────────────────────────────────────────────

from core.verses import get_daily_verse, get_daily_index

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 — 三区域布局"""
    nav = app.state.nav
    daily_verse = get_daily_verse()
    daily_index = get_daily_index()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "cbeta_available": nav is not None,
        "catalog_count": len(nav.catalog) if nav else 0,
        "daily_verse": daily_verse,
        "daily_index": daily_index,
    })


# ─── 入口 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.DEV_HOST,
        port=config.DEV_PORT,
        reload=True,
    )
