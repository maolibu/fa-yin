"""
法印對照 · FastAPI 主程序

整合經文閱讀、法脈圖譜、字典查詢的一站式佛經研習平臺。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import shutil

import config
from core.runtime_status import collect_runtime_health
from routers import search, favorites, reader, nav, lineage

# ─── 日誌 ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ─── 應用 ─────────────────────────────────────────────────────
app = FastAPI(title=config.APP_TITLE, version=config.APP_VERSION)

# 靜態文件和模板
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

# 悉曇 GIF 圖片（CBETA 梵文字符渲染）
if config.SD_GIF_DIR.exists():
    app.mount("/sd-gif", StaticFiles(directory=str(config.SD_GIF_DIR)), name="sd-gif")

# 離線地圖瓦片（可選）
if config.TILES_DIR.exists():
    app.mount("/tiles", StaticFiles(directory=str(config.TILES_DIR)), name="tiles")
    log.info(f"  離線地圖瓦片: {config.TILES_DIR} ✓")

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
templates.env.globals["app_name"] = config.APP_NAME
templates.env.globals["app_version"] = config.APP_VERSION
templates.env.globals["app_version_display"] = config.APP_VERSION_DISPLAY

# 將 templates 存儲到 app.state，供路由模塊訪問
app.state.templates = templates
app.state.runtime_health = collect_runtime_health()

# ─── 註冊路由 ─────────────────────────────────────────────────
app.include_router(search.router)
app.include_router(favorites.router)
app.include_router(reader.router)
app.include_router(nav.router)
app.include_router(lineage.router)

# 筆記 API
from routers import notes
app.include_router(notes.router)

# 用戶數據管理 API（導出）
from routers import user_data
app.include_router(user_data.router)

# 字典 API
from routers import dict_lookup
app.include_router(dict_lookup.router)

# AI 釋義 API
from routers import ai_assistant
app.include_router(ai_assistant.router)

# 每日偈頌 API
from routers import verses as verses_router
app.include_router(verses_router.router)

# 對照映射 API
from routers import commentary
app.include_router(commentary.router)


# ─── 數據遷移 ────────────────────────────────────────────────
@app.on_event("startup")
async def migrate_user_data():
    """遷移舊版數據到 user_data 目錄"""
    # 1. 遷移筆記 (exported_notes -> data/user_data/notes)
    old_notes_dir = config.SRC_DIR / "exported_notes"
    if old_notes_dir.exists() and old_notes_dir.is_dir():
        log.info(f"發現舊版筆記目錄 {old_notes_dir}，正在遷移至 {config.NOTES_DIR}...")
        config.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for item in old_notes_dir.iterdir():
            if item.is_file() and item.name.endswith(".md"):
                target = config.NOTES_DIR / item.name
                if not target.exists():
                    shutil.move(str(item), str(target))
                    count += 1
        log.info(f"成功遷移 {count} 個筆記文件")
        
        # 嘗試刪除空目錄
        try:
            # 檢查目錄是否為空（忽略 .DS_Store 等）
            has_files = False
            for f in old_notes_dir.iterdir():
                if f.name != ".DS_Store":
                    has_files = True
                    break
            if not has_files:
                shutil.rmtree(old_notes_dir)
                log.info("已刪除舊版筆記目錄")
        except Exception as e:
            log.warning(f"刪除舊版筆記目錄失敗: {e}")


# ─── 初始化核心模塊（在 startup 事件中執行，確保數據就緒） ────
app.state.nav = None
app.state.parser = None

@app.on_event("startup")
async def init_core_modules():
    """啟動時初始化 CBETA 核心模塊（實時檢查數據是否存在）"""
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
            log.info(f"CBETANav + CBETAParser 初始化成功，共 {len(nav_instance.catalog)} 部經文")
        except Exception as e:
            log.exception("核心模塊初始化失敗")
    else:
        log.warning(f"CBETA 數據未找到 ({config.CBETA_BASE})，搜索和閱讀功能不可用")


@app.on_event("startup")
async def refresh_runtime_health():
    """啟動後刷新運行時健康狀態"""
    app.state.runtime_health = collect_runtime_health(
        nav=app.state.nav,
        parser=app.state.parser,
    )


# ─── 頁面路由 ─────────────────────────────────────────────────

from core.verses import get_daily_verse, get_daily_index

RESOURCE_SECTIONS = [
    {
        "title": "漢傳經藏",
        "subtitle": "核對原文與頁欄行",
        "items": [
            {
                "name": "CBETA",
                "badge": "原文主用",
                "desc": "漢文大藏經全文與目錄，適合核對經號、卷次、藏別與全文。",
                "usage": "通讀原文、目錄定位",
                "url": "https://www.cbeta.org/",
            },
            {
                "name": "SAT 大藏經數據庫",
                "badge": "精確定位",
                "desc": "可按經號、頁欄行檢索，適合交叉核對與引用定位。",
                "usage": "查頁欄行、交叉檢索",
                "url": "https://21dzk.l.u-tokyo.ac.jp/SAT/",
            },
            {
                "name": "KABC 佛教學術院檔案（含高麗大藏經）",
                "badge": "底本校勘",
                "desc": "東國大學佛教學術院的統合大藏經平臺，可同時瀏覽與檢索高麗大藏經、韓文大藏經等佛教文獻。",
                "usage": "查高麗藏、校勘底本",
                "url": "https://kabc.dongguk.edu/",
            },
        ],
    },
    {
        "title": "跨語對照",
        "subtitle": "平行閱讀與補參",
        "items": [
            {
                "name": "SuttaCentral",
                "badge": "南傳/對照",
                "desc": "南傳與多語對照資源，適合阿含與尼柯耶平行閱讀。",
                "usage": "阿含對讀、英譯補參",
                "url": "https://suttacentral.net/",
            },
            {
                "name": "84000",
                "badge": "藏譯英譯",
                "desc": "藏傳經典英譯站，適合查看部分大乘經論的另一條傳承線。",
                "usage": "大乘補參、對照理解",
                "url": "https://84000.co/",
            },
            {
                "name": "莊春江讀經站",
                "badge": "阿含對讀",
                "desc": "莊春江居士整理的阿含與尼柯耶中文對讀資源，阿含研究者常用。",
                "usage": "阿含尼柯耶對讀",
                "url": "https://agama.buddhason.org/",
            },
        ],
    },
    {
        "title": "人物與術語",
        "subtitle": "核對異名與背景",
        "items": [
            {
                "name": "DILA 佛學規範資料庫",
                "badge": "人物專名",
                "desc": "查人物、書名、地名、異名與規範寫法，對讀註疏尤其有幫助。",
                "usage": "查譯師、異名、出處",
                "url": "https://authority.dila.edu.tw/",
            },
            {
                "name": "CBDB 中國歷代人物傳記資料庫",
                "badge": "歷史背景",
                "desc": "哈佛、中研院、北大合建的中國歷代人物數據庫，64 萬+ 傳記含譯師、僧侶、寺廟等佛教相關記錄。",
                "usage": "查譯師朝代、社會網絡、同時代背景",
                "url": "https://cbdb.hsites.harvard.edu/",
            },
        ],
    },
    {
        "title": "祖師道場",
        "subtitle": "古德開示與法彙",
        "items": [
            {
                "name": "鳳凰網·虛雲老和尚專題",
                "badge": "五宗法脈",
                "desc": "主流媒體整合的虛雲老和尚專題，含年譜、生平、禪修開示、紀念文集與詩偈。一身承禪宗五派法脈，近代禪門泰斗。",
                "usage": "查虛雲年譜、禪修開示",
                "url": "https://fo.ifeng.com/zhuanti/xuyun/",
            },
            {
                "name": "法界佛教總會在線閱讀",
                "badge": "宣化上人",
                "desc": "1948 年於廣東南華寺得虛雲老和尚傳法，為沩仰宗第九代傳人。1959 年在美國創立法界佛教總會。站內含開示錄、經典淺釋（楞嚴、法華、華嚴、金剛等）全文。",
                "usage": "查宣化上人講經、開示",
                "url": "http://www.drbachinese.org/online_reading/",
            },
        ],
    },
    {
        "title": "底本與影像",
        "subtitle": "回到底本源頭",
        "items": [
            {
                "name": "BDRC Library",
                "badge": "影像資料",
                "desc": "佛教文獻影像與目錄資源庫，適合回看底本、影像與館藏信息。",
                "usage": "查底本、看影像",
                "url": "https://library.bdrc.io/",
            },
            {
                "name": "中華古籍資源庫",
                "badge": "國圖權威",
                "desc": "中國國家圖書館古籍數字化平臺，含趙城金藏、永樂北藏等核心藏經影像與 25,000+ 條善本記錄。",
                "usage": "查趙城金藏、永樂北藏影像",
                "url": "http://read.nlc.cn/thematDataSearch/toGujiIndex",
            },
            {
                "name": "數字敦煌",
                "badge": "敦煌寫經",
                "desc": "敦煌研究院官方數字平臺，提供莫高窟壁畫高清影像、數字洞窟、敦煌寫經與素材庫。",
                "usage": "看敦煌寫經、石窟壁畫",
                "url": "https://www.e-dunhuang.com/",
            },
            {
                "name": "識典古籍",
                "badge": "古籍檢索",
                "desc": "北大與字節跳動合作 OCR 平臺，2.56 萬部古籍含佛教典籍，OCR 準確率 96-97%。",
                "usage": "補查冷門古籍、OCR 原文",
                "url": "https://www.shidianguji.com/",
            },
            {
                "name": "IDP 國際敦煌項目（中國站）",
                "badge": "海外寫經",
                "desc": "國家圖書館主辦的國際敦煌項目中國站，匯集英、法、俄、日等國收藏的敦煌寫經高清影像，為目前最大的敦煌文獻跨國數據庫。",
                "usage": "查海外流散敦煌寫經",
                "url": "http://idp.nlc.cn/",
            },
            {
                "name": "臺北故宮古籍輿圖檢索系統",
                "badge": "宮廷寫本",
                "desc": "國立故宮博物院善本古籍與輿圖檢索系統，含明清宮廷供奉漢藏佛典、梵筴寫本、貝葉經等珍貴影像，免登入瀏覽。",
                "usage": "查宮廷寫本、梵筴經",
                "url": "https://rarebooks-maps.npm.edu.tw/",
            },
        ],
    },
]

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首頁 — 三區域佈局"""
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


@app.get("/resources", response_class=HTMLResponse)
async def resources(request: Request):
    """外部資源導航頁"""
    return templates.TemplateResponse("resources.html", {
        "request": request,
        "resource_sections": RESOURCE_SECTIONS,
    })


@app.get("/api/health")
async def api_health():
    """返回運行時健康狀態，供自檢與部署排障使用"""
    app.state.runtime_health = collect_runtime_health(
        nav=app.state.nav,
        parser=app.state.parser,
    )
    return app.state.runtime_health


# ─── 入口 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.DEV_HOST,
        port=config.DEV_PORT,
        reload=True,
    )
