#!/usr/bin/env python3
"""
法印對照 · 一鍵啟動腳本

生命週期：
  Step 1  數據自檢 — 檢查 CBETA 原始 XML 是否存在
  Step 2  引導下載 — 若缺失則打印提示並等待用戶操作
  Step 3  數據庫構建 — 若搜索數據庫不存在則自動運行 ETL
  Step 4  Obsidian Vault — 生成 Obsidian Markdown 文件
  Step 5  服務啟動 — 啟動 FastAPI 後端
  Step 6  終端貼士 — 打印訪問地址與使用說明，自動打開瀏覽器

用法:
  python launcher.py              # 正常啟動
  python launcher.py --check      # 僅運行自檢，不啟動服務
  python launcher.py --port 8080  # 指定端口
"""

import sys
import os
import time
import argparse
import socket
import webbrowser
import subprocess
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

# ─── 確保 src/ 在 Python 搜索路徑中 ─────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import config
from core.runtime_status import check_dict_db, check_lineage_db, check_search_db


# ============================================================
# 終端顯示輔助函數（中英文混排自動對齊）
# ============================================================

def display_width(text):
    """計算終端顯示寬度（中文全角=2, 英文半角=1, 零寬字符=0）"""
    width = 0
    for c in text:
        cat = unicodedata.category(c)
        # 零寬字符：變體選擇符(Mn)、格式字符(Cf)、組合標記等
        if cat in ('Mn', 'Me', 'Cf'):
            continue
        eaw = unicodedata.east_asian_width(c)
        if eaw in ('W', 'F'):
            width += 2
        else:
            width += 1
    return width


def box_center(content, inner_width, border="║"):
    """打印居中對齊的邊框行"""
    w = display_width(content)
    pad = inner_width - w
    left = pad // 2
    right = pad - left
    print(f"  {border}{' ' * left}{content}{' ' * right}{border}")


def box_left(content, inner_width, border="│"):
    """打印左對齊的邊框行"""
    w = display_width(content)
    pad = max(inner_width - w, 1)
    print(f"  {border}{content}{' ' * pad}{border}")


def box_empty(inner_width, border="│"):
    """打印空白邊框行"""
    print(f"  {border}{' ' * inner_width}{border}")


def print_banner():
    """打印啟動橫幅"""
    W = 38  # ═ 號的數量 = 邊框內部寬度
    print()
    print(f"  ╔{'═' * W}╗")
    box_center("法 印 對 照 · 閱 讀 平 臺", W)
    box_center(f"Fa-Yin Reading Platform  {config.APP_VERSION_DISPLAY}", W)
    print(f"  ╚{'═' * W}╝")
    print()


def print_step(step_num, title, status=""):
    """打印步驟狀態"""
    icons = {1: "🔍", 2: "📥", 3: "🗄️", 4: "📖", 5: "🚀", 6: "📋"}
    icon = icons.get(step_num, "•")
    status_str = f"  {status}" if status else ""
    print(f"  {icon} Step {step_num}: {title}{status_str}")


def check_port_available(host, port):
    """檢查端口是否可用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def wait_for_server(host, port, timeout=15):
    """等待服務器啟動（最多 timeout 秒）"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect((host, port))
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


# ============================================================
# Step 0: 數據解壓（首次運行時從 tar.gz 解壓詞典/地圖）
# ============================================================

# 2 個打包文件 → 解壓目標路徑（字體已直接提交到 src/static/fonts/）
_ARCHIVES = [
    ("data/dicts.tar.gz", "tools/dict_converter", "tools/dict_converter/13dicts", "詞典"),
    ("data/tiles.tar.gz", "data", "data/tiles", "地圖瓦片"),
]


def extract_archives():
    """檢查並解壓 tar.gz 數據包（僅在目標目錄不存在時執行）"""
    import tarfile
    needed = []
    for arc, dest, check_dir, label in _ARCHIVES:
        arc_path = PROJECT_ROOT / arc
        check_path = PROJECT_ROOT / check_dir
        if not check_path.exists() and arc_path.exists():
            needed.append((arc_path, PROJECT_ROOT / dest, label))

    if not needed:
        return

    print("  📦 首次運行，解壓數據包...")
    for arc_path, dest_path, label in needed:
        size_mb = arc_path.stat().st_size / (1024 * 1024)
        print(f"      ⏳ {label} ({size_mb:.0f}MB)...", end="", flush=True)
        dest_path.mkdir(parents=True, exist_ok=True)
        with tarfile.open(arc_path, "r:gz") as tf:
            tf.extractall(path=dest_path)
        print(" ✅")
    print()


# ============================================================
# Step 1: 數據自檢
# ============================================================

def check_cbeta_data(cbeta_base):
    """
    檢查 CBETA 原始數據是否存在且有效。
    返回: (ok: bool, xml_count: int)
    """
    xml_dir = cbeta_base / "XML"
    if not xml_dir.exists():
        return False, 0

    # 快速計數：查找 XML 子目錄中是否有 .xml 文件
    xml_count = 0
    for canon_dir in sorted(xml_dir.iterdir()):
        if canon_dir.is_dir():
            for vol_dir in canon_dir.iterdir():
                if vol_dir.is_dir():
                    for f in vol_dir.iterdir():
                        if f.suffix == ".xml":
                            xml_count += 1
                            if xml_count >= 10:
                                # 找到足夠多的文件，確認數據有效
                                return True, xml_count
    return xml_count > 0, xml_count


# ============================================================
# Step 2: 引導下載
# ============================================================

def guide_download(cbeta_base):
    """引導用戶下載 CBETA 數據"""
    W = 49  # 邊框內部寬度
    print()
    print(f"  ┌{'─' * W}┐")
    box_center("📖 首次使用 · 數據下載引導", W, "│")
    print(f"  ├{'─' * W}┤")
    box_empty(W)
    box_left("  本程序需要 CBETA 經文數據才能運行。", W)
    box_left("  請按以下步驟操作：", W)
    box_empty(W)
    box_left("  1. 訪問 CBETA 官網下載指定的經文數據包：", W)
    box_left("     【CBETA CBReader 2X 經文資料檔】", W)
    box_left("     (注: 若官網有更新，請下載最新版本)", W)
    box_left("     https://www.cbeta.org/download", W)
    box_empty(W)
    box_left("  2. 下載後解壓，將文件夾重命名為小寫 cbeta", W)
    box_left("     放到以下目錄（包含 XML/ 子目錄）：", W)
    box_left(f"     {cbeta_base}/", W)
    box_empty(W)
    box_left("  3. 確保目錄結構如下：", W)
    box_left("     data/raw/cbeta/          （注意小寫）", W)
    box_left("     ├── XML/           （經文 XML 文件）", W)
    box_left("     ├── toc/           （目錄數據）", W)
    box_left("     ├── sd-gif/        （悉曇字圖片）", W)
    box_left("     ├── advance_nav.xhtml", W)
    box_left("     ├── bulei_nav.xhtml", W)
    box_left("     └── ...", W)
    box_empty(W)
    print(f"  └{'─' * W}┘")
    print()

    try:
        input("  ✋ 數據放好後，按 Enter 鍵繼續...")
    except KeyboardInterrupt:
        print("\n\n  已取消。")
        sys.exit(0)


# ============================================================
# Step 3: 數據庫構建
# ============================================================

def quarantine_sqlite_artifacts(db_path, label):
    """隔離可疑的 SQLite 主文件及其 wal/shm，避免重建時繼續踩壞庫。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    moved = []
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if not candidate.exists():
            continue
        backup = candidate.with_name(f"{candidate.name}.invalid-{stamp}")
        try:
            candidate.rename(backup)
            moved.append(backup)
        except OSError as exc:
            print(f"  ⚠️  無法隔離 {label} 文件 {candidate.name}: {exc}")
    if moved:
        print(f"      已隔離 {label}:")
        for item in moved:
            print(f"        - {item.name}")


def build_database(config):
    """檢查並構建搜索數據庫"""
    search_db = config.CBETA_SEARCH_DB
    status = check_search_db(search_db)

    if status["ok"]:
        print_step(3, "搜索數據庫", "✅ 已通過 schema 校驗")
        return True

    if status["reason"] == "missing":
        print_step(3, "搜索數據庫", "⏳ 數據庫不存在，開始構建...")
    else:
        print_step(3, "搜索數據庫", f"⚠️ {status['message']}，準備重建...")
        quarantine_sqlite_artifacts(search_db, "搜索數據庫")
    print("      （首次構建約需 5-15 分鐘，取決於機器性能）")
    print()

    # 確保數據庫目錄存在
    config.DB_DIR.mkdir(parents=True, exist_ok=True)

    # 調用 ETL 腳本
    etl_script = config.SRC_DIR / "etl" / "etl_build_search.py"
    if not etl_script.exists():
        print(f"  ❌ ETL 腳本未找到: {etl_script}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(etl_script), "--all"],
            cwd=str(config.SRC_DIR),
            check=True,
        )
        if result.returncode == 0:
            final_status = check_search_db(search_db)
            if final_status["ok"]:
                print()
                print("      ✅ 搜索數據庫構建完成並通過校驗！")
                return True
            print(f"  ⚠️  搜索數據庫構建後仍不可用: {final_status['message']}")
            if final_status["detail"]:
                print(f"      {final_status['detail']}")
            print("      將以標題檢索降級模式繼續啟動。")
            return False
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 數據庫構建失敗: {e}")
        print("      將以標題檢索降級模式繼續啟動。")
        return False
    except KeyboardInterrupt:
        print("\n  ⚠️  構建已中斷。下次啟動時會重新嘗試。")
        return False

    return False


def build_dict_database(config):
    """檢查並構建詞典數據庫"""
    dict_db = config.DICTS_DB
    status = check_dict_db(dict_db)

    if status["ok"]:
        print_step(3, "詞典數據庫", "✅ 已通過 schema 校驗")
        return True

    if status["reason"] == "missing":
        print_step(3, "詞典數據庫", "⏳ 數據庫不存在，開始構建...")
    else:
        print_step(3, "詞典數據庫", f"⚠️ {status['message']}，準備重建...")
        quarantine_sqlite_artifacts(dict_db, "詞典數據庫")

    dict_script = PROJECT_ROOT / "tools" / "dict_converter" / "build_dict_db.py"
    if not dict_script.exists():
        print(f"  ⚠️  詞典構建腳本未找到: {dict_script}")
        print("      將以用戶詞典降級模式繼續啟動。")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(dict_script)],
            cwd=str(dict_script.parent),
            check=True,
        )
        if result.returncode == 0:
            final_status = check_dict_db(dict_db)
            if final_status["ok"]:
                print("      ✅ 詞典數據庫構建完成並通過校驗！")
                return True
            print(f"  ⚠️  詞典數據庫構建後仍不可用: {final_status['message']}")
            if final_status["detail"]:
                print(f"      {final_status['detail']}")
            print("      將以用戶詞典降級模式繼續啟動。")
            return False
    except subprocess.CalledProcessError as e:
        print(f"  ⚠️  詞典數據庫構建失敗: {e}")
        print("      將以用戶詞典降級模式繼續啟動。")
        return False
    except KeyboardInterrupt:
        print("\n  ⚠️  構建已中斷。")
        return False

    return False


def report_lineage_database():
    """報告法脈數據庫狀態（可選依賴，不阻斷啟動）"""
    status = check_lineage_db(config.LINEAGE_DB)
    if status["ok"]:
        print_step(3, "法脈數據庫", "✅ 已通過 schema 校驗")
        return True

    print_step(3, "法脈數據庫", f"⚠️ {status['message']}")
    if status["detail"]:
        print(f"      {status['detail']}")
    print("      人物、法脈、地圖相關接口將返回 503，其他功能不受影響。")
    return False


# ============================================================
# Step 4: Obsidian Vault 生成
# ============================================================

def build_obsidian_vault():
    """檢查並生成 Obsidian Markdown Vault"""
    vault_dir = PROJECT_ROOT / "obsidian_vault" / "output"
    marker = vault_dir / "首頁.md"

    if marker.exists():
        # 統計已有 MD 文件數
        md_count = sum(1 for _ in (vault_dir / "經文").rglob("*.md")) if (vault_dir / "經文").exists() else 0
        print_step(4, "Obsidian Vault", f"✅ 已存在 ({md_count} 部經典)")
        return True

    print_step(4, "Obsidian Vault", "⏳ 生成 Obsidian Markdown 文件...")
    print("      （首次生成約需 1-2 分鐘）")
    print()

    md_script = PROJECT_ROOT / "obsidian_vault" / "xml_to_md.py"
    if not md_script.exists():
        print(f"  ⚠️ Obsidian 轉換腳本未找到: {md_script}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(md_script), "--all"],
            cwd=str(PROJECT_ROOT),
            check=True,
        )
        if result.returncode == 0:
            print()
            print("      ✅ Obsidian Vault 生成完成！")
            print("      📂 輸出目錄: obsidian_vault/output/")
            return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Obsidian Vault 生成失敗: {e}")
        return False
    except KeyboardInterrupt:
        print("\n  ⚠️  生成已中斷。下次啟動時會重新嘗試。")
        return False

    return False


# ============================================================
# Step 5 & 6: 服務啟動 + 終端貼士
# ============================================================

def print_tips(host, port):
    """打印使用說明"""
    # 自動換算顯示地址（0.0.0.0 → localhost）
    display_host = "localhost" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"

    W = 49  # 邊框內部寬度
    print()
    print(f"  ┌{'─' * W}┐")
    box_left(f"  🌐 訪問地址: {url}", W)
    print(f"  ├{'─' * W}┤")
    box_left("  📖 使用提示:", W)
    box_left("    • 首頁選擇經文 → 點擊卷號開始閱讀", W)
    box_left("    • 閱讀頁右上角工具欄：字典、筆記、AI 釋義", W)
    box_left("    • 支持劃詞查字典、選段 AI 釋義", W)
    print(f"  ├{'─' * W}┤")
    box_left("  📚 詞典擴展:", W)
    box_left("    內置 6 部精選詞典", W)
    box_left("    用戶詞典目錄: data/dicts/user/", W)
    box_left("    支持格式: .mdx（MDict）/ .json / .csv", W)
    box_left("    放入文件後重啟即可自動加載", W)
    print(f"  ├{'─' * W}┤")
    box_left("  💾 數據備份:", W)
    box_left("    個人筆記保存在 data/user_data/notes/", W)
    box_left("    收藏保存在     data/user_data/favorites.json", W)
    box_left("    備份只需複製 data/user_data/ 整個文件夾即可", W)
    print(f"  ├{'─' * W}┤")
    box_left("  ⌨️  快捷操作:", W)
    box_left("    Ctrl+C  停止服務", W)
    box_left(f"    健康檢查: {url}/api/health", W)
    print(f"  ├{'─' * W}┤")
    box_left("  🔗 項目主頁:", W)
    box_left("    https://github.com/maolibu/fa-yin", W)
    print(f"  └{'─' * W}┘")
    print()


def open_browser_delayed(host, port):
    """在後臺線程中延遲打開瀏覽器"""
    display_host = "localhost" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"

    if wait_for_server(display_host, port, timeout=15):
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 無圖形環境（如 VPS）時靜默忽略


def start_server(host, port):
    """啟動 FastAPI 服務"""
    print_step(5, "服務啟動", f"⏳ 正在啟動服務於 {host}:{port}...")

    # 檢查端口
    if not check_port_available(host, port):
        print(f"  ⚠️  端口 {port} 已被佔用，嘗試端口 {port + 1}...")
        port += 1
        if not check_port_available(host, port):
            print(f"  ❌ 端口 {port} 也被佔用，請手動指定: python launcher.py --port <端口號>")
            sys.exit(1)

    # 後臺線程打開瀏覽器
    browser_thread = threading.Thread(
        target=open_browser_delayed,
        args=(host, port),
        daemon=True,
    )
    browser_thread.start()

    # 打印貼士
    print_tips(host, port)

    # 啟動 uvicorn（這會阻塞主線程）
    import uvicorn
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        app_dir=str(SRC_DIR),
    )


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="法印對照 (Fa-Yin) · 一鍵啟動腳本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check", action="store_true",
        help="僅運行數據自檢，不啟動服務",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="指定服務端口（默認 8400）",
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="指定綁定地址（默認 0.0.0.0）",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="啟動後不自動打開瀏覽器",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="跳過數據庫構建步驟",
    )
    parser.add_argument(
        "--skip-obsidian", action="store_true",
        help="跳過 Obsidian Vault 生成",
    )
    args = parser.parse_args()

    # 橫幅
    print_banner()

    host = args.host or config.DEV_HOST
    port = args.port or config.DEV_PORT

    # Step 0: 數據解壓（首次運行時解壓詞典/地圖）
    extract_archives()

    # Step 1: 數據自檢
    print_step(1, "數據自檢", "⏳ 檢查 CBETA 數據...")
    ok, xml_count = check_cbeta_data(config.CBETA_BASE)

    if ok:
        print_step(1, "數據自檢", f"✅ 已找到 CBETA 數據 ({xml_count}+ 個 XML 文件)")
    else:
        print_step(1, "數據自檢", "❌ 未檢測到 CBETA 原始數據")

        # Step 2: 引導下載
        print_step(2, "引導下載")
        guide_download(config.CBETA_BASE)

        # 重新檢查
        ok, xml_count = check_cbeta_data(config.CBETA_BASE)
        if not ok:
            print("  ❌ 仍未檢測到有效數據，請檢查路徑後重試。")
            sys.exit(1)
        print_step(1, "數據自檢", f"✅ 已找到 CBETA 數據 ({xml_count}+ 個 XML 文件)")

    if args.check:
        # 僅自檢模式
        print()
        config.print_config()
        print("\n  ✅ 自檢完成。使用 `python launcher.py` 啟動完整服務。")
        return

    # Step 3: 數據庫構建
    if not args.skip_build:
        build_database(config)
    else:
        search_status = check_search_db(config.CBETA_SEARCH_DB)
        if search_status["ok"]:
            print_step(3, "搜索數據庫", "⏸️  已跳過構建（當前數據庫可用）")
        else:
            print_step(3, "搜索數據庫", f"⚠️ 已跳過構建，當前不可用：{search_status['message']}")
            print("      將以標題檢索降級模式繼續啟動。")

    # Step 3b: 詞典數據庫構建
    if not args.skip_build:
        build_dict_database(config)
    else:
        dict_status = check_dict_db(config.DICTS_DB)
        if dict_status["ok"]:
            print_step(3, "詞典數據庫", "⏸️  已跳過構建（當前數據庫可用）")
        else:
            print_step(3, "詞典數據庫", f"⚠️ 已跳過構建，當前不可用：{dict_status['message']}")
            print("      將以用戶詞典降級模式繼續啟動。")

    # Step 3c: 法脈數據庫狀態
    report_lineage_database()

    # Step 4: Obsidian Vault 生成
    if not args.skip_obsidian:
        build_obsidian_vault()
    else:
        print_step(4, "Obsidian Vault", "⏸️  已跳過（--skip-obsidian）")

    # 確保用戶數據目錄存在
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    # 確保用戶詞典目錄存在
    user_dict_dir = config.PROJECT_ROOT / "data" / "dicts" / "user"
    user_dict_dir.mkdir(parents=True, exist_ok=True)
    user_dict_count = sum(1 for f in user_dict_dir.iterdir()
                         if f.is_file() and f.suffix.lower() in ('.mdx', '.json', '.csv'))
    if user_dict_count:
        print(f"  📚 發現 {user_dict_count} 部用戶詞典")

    # 複製默認收藏（如果用戶還未個性化）
    if not config.FAVORITES_PATH.exists() and config.FAVORITES_DEFAULT_PATH.exists():
        import shutil
        shutil.copy2(str(config.FAVORITES_DEFAULT_PATH), str(config.FAVORITES_PATH))
        print("  📋 已初始化默認收藏列表")

    # Step 5 & 6: 啟動服務
    if args.no_browser:
        # 禁止自動打開瀏覽器時，直接啟動不創建瀏覽器線程
        print_step(5, "服務啟動", f"⏳ 正在啟動服務於 {host}:{port}...")
        print_tips(host, port)
        import uvicorn
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=False,
            log_level="info",
            app_dir=str(SRC_DIR),
        )
    else:
        start_server(host, port)


if __name__ == "__main__":
    main()
