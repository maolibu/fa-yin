#!/usr/bin/env python3
"""
法印对照 · 一键启动脚本

生命周期：
  Step 1  数据自检 — 检查 CBETA 原始 XML 是否存在
  Step 2  引导下载 — 若缺失则打印提示并等待用户操作
  Step 3  数据库构建 — 若搜索数据库不存在则自动运行 ETL
  Step 4  Obsidian Vault — 生成 Obsidian Markdown 文件
  Step 5  服务启动 — 启动 FastAPI 后端
  Step 6  终端贴士 — 打印访问地址与使用说明，自动打开浏览器

用法:
  python launcher.py              # 正常启动
  python launcher.py --check      # 仅运行自检，不启动服务
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
from pathlib import Path

# ─── 确保 src/ 在 Python 搜索路径中 ─────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


# ============================================================
# 终端显示辅助函数（中英文混排自动对齐）
# ============================================================

def display_width(text):
    """计算终端显示宽度（中文全角=2, 英文半角=1, 零宽字符=0）"""
    width = 0
    for c in text:
        cat = unicodedata.category(c)
        # 零宽字符：变体选择符(Mn)、格式字符(Cf)、组合标记等
        if cat in ('Mn', 'Me', 'Cf'):
            continue
        eaw = unicodedata.east_asian_width(c)
        if eaw in ('W', 'F'):
            width += 2
        else:
            width += 1
    return width


def box_center(content, inner_width, border="║"):
    """打印居中对齐的边框行"""
    w = display_width(content)
    pad = inner_width - w
    left = pad // 2
    right = pad - left
    print(f"  {border}{' ' * left}{content}{' ' * right}{border}")


def box_left(content, inner_width, border="│"):
    """打印左对齐的边框行"""
    w = display_width(content)
    pad = max(inner_width - w, 1)
    print(f"  {border}{content}{' ' * pad}{border}")


def box_empty(inner_width, border="│"):
    """打印空白边框行"""
    print(f"  {border}{' ' * inner_width}{border}")


def print_banner():
    """打印启动横幅"""
    W = 38  # ═ 号的数量 = 边框内部宽度
    print()
    print(f"  ╔{'═' * W}╗")
    box_center("法 印 对 照 · 阅 读 平 台", W)
    box_center("Fa-Yin Reading Platform  v1.0", W)
    print(f"  ╚{'═' * W}╝")
    print()


def print_step(step_num, title, status=""):
    """打印步骤状态"""
    icons = {1: "🔍", 2: "📥", 3: "🗄️", 4: "📖", 5: "🚀", 6: "📋"}
    icon = icons.get(step_num, "•")
    status_str = f"  {status}" if status else ""
    print(f"  {icon} Step {step_num}: {title}{status_str}")


def check_port_available(host, port):
    """检查端口是否可用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def wait_for_server(host, port, timeout=15):
    """等待服务器启动（最多 timeout 秒）"""
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
# Step 0: 数据解压（首次运行时从 tar.gz 解压词典/地图）
# ============================================================

# 2 个打包文件 → 解压目标路径（字体已直接提交到 src/static/fonts/）
_ARCHIVES = [
    ("data/dicts.tar.gz", "tools/dict_converter", "tools/dict_converter/13dicts", "词典"),
    ("data/tiles.tar.gz", "data", "data/tiles", "地图瓦片"),
]


def extract_archives():
    """检查并解压 tar.gz 数据包（仅在目标目录不存在时执行）"""
    import tarfile
    needed = []
    for arc, dest, check_dir, label in _ARCHIVES:
        arc_path = PROJECT_ROOT / arc
        check_path = PROJECT_ROOT / check_dir
        if not check_path.exists() and arc_path.exists():
            needed.append((arc_path, PROJECT_ROOT / dest, label))

    if not needed:
        return

    print("  📦 首次运行，解压数据包...")
    for arc_path, dest_path, label in needed:
        size_mb = arc_path.stat().st_size / (1024 * 1024)
        print(f"      ⏳ {label} ({size_mb:.0f}MB)...", end="", flush=True)
        dest_path.mkdir(parents=True, exist_ok=True)
        with tarfile.open(arc_path, "r:gz") as tf:
            tf.extractall(path=dest_path)
        print(" ✅")
    print()


# ============================================================
# Step 1: 数据自检
# ============================================================

def check_cbeta_data(cbeta_base):
    """
    检查 CBETA 原始数据是否存在且有效。
    返回: (ok: bool, xml_count: int)
    """
    xml_dir = cbeta_base / "XML"
    if not xml_dir.exists():
        return False, 0

    # 快速计数：查找 XML 子目录中是否有 .xml 文件
    xml_count = 0
    for canon_dir in sorted(xml_dir.iterdir()):
        if canon_dir.is_dir():
            for vol_dir in canon_dir.iterdir():
                if vol_dir.is_dir():
                    for f in vol_dir.iterdir():
                        if f.suffix == ".xml":
                            xml_count += 1
                            if xml_count >= 10:
                                # 找到足够多的文件，确认数据有效
                                return True, xml_count
    return xml_count > 0, xml_count


# ============================================================
# Step 2: 引导下载
# ============================================================

def guide_download(cbeta_base):
    """引导用户下载 CBETA 数据"""
    W = 49  # 边框内部宽度
    print()
    print(f"  ┌{'─' * W}┐")
    box_center("📖 首次使用 · 数据下载引导", W, "│")
    print(f"  ├{'─' * W}┤")
    box_empty(W)
    box_left("  本程序需要 CBETA 经文数据才能运行。", W)
    box_left("  请按以下步骤操作：", W)
    box_empty(W)
    box_left("  1. 访问 CBETA 官网下载指定的经文数据包：", W)
    box_left("     【CBETA CBReader 2X 經文資料檔】", W)
    box_left("     (注: 若官网有更新，请下载最新版本)", W)
    box_left("     https://www.cbeta.org/download", W)
    box_empty(W)
    box_left("  2. 下载后解压，将整个 cbeta 文件夹", W)
    box_left("     复制到以下目录（包含 XML/ 子目录）：", W)
    box_left(f"     {cbeta_base}/", W)
    box_empty(W)
    box_left("  3. 确保目录结构如下：", W)
    box_left("     data/raw/cbeta/", W)
    box_left("     ├── XML/           （经文 XML 文件）", W)
    box_left("     ├── toc/           （目录数据）", W)
    box_left("     ├── advance_nav.xhtml", W)
    box_left("     ├── bulei_nav.xhtml", W)
    box_left("     ├── catalog.txt", W)
    box_left("     └── bookdata.txt", W)
    box_empty(W)
    print(f"  └{'─' * W}┘")
    print()

    try:
        input("  ✋ 数据放好后，按 Enter 键继续...")
    except KeyboardInterrupt:
        print("\n\n  已取消。")
        sys.exit(0)


# ============================================================
# Step 3: 数据库构建
# ============================================================

def build_database(config):
    """检查并构建搜索数据库"""
    search_db = config.CBETA_SEARCH_DB

    if search_db.exists() and search_db.stat().st_size > 1024:
        print_step(3, "数据库构建", "✅ 搜索数据库已存在")
        return True

    print_step(3, "数据库构建", "⏳ 搜索数据库不存在，开始构建...")
    print("      （首次构建约需 5-15 分钟，取决于机器性能）")
    print()

    # 确保数据库目录存在
    config.DB_DIR.mkdir(parents=True, exist_ok=True)

    # 调用 ETL 脚本
    etl_script = config.SRC_DIR / "etl" / "etl_build_search.py"
    if not etl_script.exists():
        print(f"  ❌ ETL 脚本未找到: {etl_script}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(etl_script), "--all"],
            cwd=str(config.SRC_DIR),
            check=True,
        )
        if result.returncode == 0:
            print()
            print("      ✅ 搜索数据库构建完成！")
            return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 数据库构建失败: {e}")
        return False
    except KeyboardInterrupt:
        print("\n  ⚠️  构建已中断。下次启动时会重新尝试。")
        return False

    return False


# ============================================================
# Step 4: Obsidian Vault 生成
# ============================================================

def build_obsidian_vault():
    """检查并生成 Obsidian Markdown Vault"""
    vault_dir = PROJECT_ROOT / "obsidian_vault" / "output"
    marker = vault_dir / "首頁.md"

    if marker.exists():
        # 统计已有 MD 文件数
        md_count = sum(1 for _ in (vault_dir / "經文").rglob("*.md")) if (vault_dir / "經文").exists() else 0
        print_step(4, "Obsidian Vault", f"✅ 已存在 ({md_count} 部经典)")
        return True

    print_step(4, "Obsidian Vault", "⏳ 生成 Obsidian Markdown 文件...")
    print("      （首次生成约需 1-2 分钟）")
    print()

    md_script = PROJECT_ROOT / "obsidian_vault" / "xml_to_md.py"
    if not md_script.exists():
        print(f"  ⚠️ Obsidian 转换脚本未找到: {md_script}")
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
            print("      📂 输出目录: obsidian_vault/output/")
            return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Obsidian Vault 生成失败: {e}")
        return False
    except KeyboardInterrupt:
        print("\n  ⚠️  生成已中断。下次启动时会重新尝试。")
        return False

    return False


# ============================================================
# Step 5 & 6: 服务启动 + 终端贴士
# ============================================================

def print_tips(host, port):
    """打印使用说明"""
    # 自动换算显示地址（0.0.0.0 → localhost）
    display_host = "localhost" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"

    W = 49  # 边框内部宽度
    print()
    print(f"  ┌{'─' * W}┐")
    box_left(f"  🌐 访问地址: {url}", W)
    print(f"  ├{'─' * W}┤")
    box_left("  📖 使用提示:", W)
    box_left("    • 首页选择经文 → 点击卷号开始阅读", W)
    box_left("    • 阅读页右上角工具栏：字典、笔记、AI 释义", W)
    box_left("    • 支持划词查字典、选段 AI 释义", W)
    print(f"  ├{'─' * W}┤")
    box_left("  📚 词典扩展:", W)
    box_left("    内置 6 部精选词典", W)
    box_left("    用户词典目录: data/dicts/user/", W)
    box_left("    支持格式: .mdx（MDict）/ .json / .csv", W)
    box_left("    放入文件后重启即可自动加载", W)
    print(f"  ├{'─' * W}┤")
    box_left("  💾 数据备份:", W)
    box_left("    个人笔记保存在 data/user_data/notes/", W)
    box_left("    收藏保存在     data/user_data/favorites.json", W)
    box_left("    备份只需复制 data/user_data/ 整个文件夹即可", W)
    print(f"  ├{'─' * W}┤")
    box_left("  ⌨️  快捷操作:", W)
    box_left("    Ctrl+C  停止服务", W)
    print(f"  ├{'─' * W}┤")
    box_left("  🔗 项目主页:", W)
    box_left("    https://github.com/maolibu/fa-yin", W)
    print(f"  └{'─' * W}┘")
    print()


def open_browser_delayed(host, port):
    """在后台线程中延迟打开浏览器"""
    display_host = "localhost" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"

    if wait_for_server(display_host, port, timeout=15):
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 无图形环境（如 VPS）时静默忽略


def start_server(host, port):
    """启动 FastAPI 服务"""
    print_step(5, "服务启动", f"⏳ 正在启动服务于 {host}:{port}...")

    # 检查端口
    if not check_port_available(host, port):
        print(f"  ⚠️  端口 {port} 已被占用，尝试端口 {port + 1}...")
        port += 1
        if not check_port_available(host, port):
            print(f"  ❌ 端口 {port} 也被占用，请手动指定: python launcher.py --port <端口号>")
            sys.exit(1)

    # 后台线程打开浏览器
    browser_thread = threading.Thread(
        target=open_browser_delayed,
        args=(host, port),
        daemon=True,
    )
    browser_thread.start()

    # 打印贴士
    print_tips(host, port)

    # 启动 uvicorn（这会阻塞主线程）
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
        description="法印对照 (Fa-Yin) · 一键启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check", action="store_true",
        help="仅运行数据自检，不启动服务",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="指定服务端口（默认 8400）",
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="指定绑定地址（默认 0.0.0.0）",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="启动后不自动打开浏览器",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="跳过数据库构建步骤",
    )
    parser.add_argument(
        "--skip-obsidian", action="store_true",
        help="跳过 Obsidian Vault 生成",
    )
    args = parser.parse_args()

    # 横幅
    print_banner()

    # 加载配置
    import config
    host = args.host or config.DEV_HOST
    port = args.port or config.DEV_PORT

    # Step 0: 数据解压（首次运行时解压词典/地图）
    extract_archives()

    # Step 1: 数据自检
    print_step(1, "数据自检", "⏳ 检查 CBETA 数据...")
    ok, xml_count = check_cbeta_data(config.CBETA_BASE)

    if ok:
        print_step(1, "数据自检", f"✅ 已找到 CBETA 数据 ({xml_count}+ 个 XML 文件)")
    else:
        print_step(1, "数据自检", "❌ 未检测到 CBETA 原始数据")

        # Step 2: 引导下载
        print_step(2, "引导下载")
        guide_download(config.CBETA_BASE)

        # 重新检查
        ok, xml_count = check_cbeta_data(config.CBETA_BASE)
        if not ok:
            print("  ❌ 仍未检测到有效数据，请检查路径后重试。")
            sys.exit(1)
        print_step(1, "数据自检", f"✅ 已找到 CBETA 数据 ({xml_count}+ 个 XML 文件)")

    if args.check:
        # 仅自检模式
        print()
        config.print_config()
        print("\n  ✅ 自检完成。使用 `python launcher.py` 启动完整服务。")
        return

    # Step 3: 数据库构建
    if not args.skip_build:
        build_database(config)
    else:
        print_step(3, "数据库构建", "⏸️  已跳过（--skip-build）")

    # Step 3b: 词典数据库构建
    dicts_db = config.DICTS_DB
    if dicts_db.exists() and dicts_db.stat().st_size > 1024:
        print_step(3, "词典数据库", "✅ 已存在")
    else:
        print_step(3, "词典数据库", "⏳ 词典数据库不存在，开始构建...")
        dict_script = PROJECT_ROOT / "tools" / "dict_converter" / "build_dict_db.py"
        if dict_script.exists():
            try:
                result = subprocess.run(
                    [sys.executable, str(dict_script)],
                    cwd=str(dict_script.parent),
                    check=True,
                )
                if result.returncode == 0:
                    print("      ✅ 词典数据库构建完成！")
            except subprocess.CalledProcessError as e:
                print(f"  ⚠️  词典数据库构建失败: {e}")
            except KeyboardInterrupt:
                print("\n  ⚠️  构建已中断。")
        else:
            print(f"  ⚠️  词典构建脚本未找到: {dict_script}")

    # Step 4: Obsidian Vault 生成
    if not args.skip_obsidian:
        build_obsidian_vault()
    else:
        print_step(4, "Obsidian Vault", "⏸️  已跳过（--skip-obsidian）")

    # 确保用户数据目录存在
    config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    # 确保用户词典目录存在
    user_dict_dir = config.PROJECT_ROOT / "data" / "dicts" / "user"
    user_dict_dir.mkdir(parents=True, exist_ok=True)
    user_dict_count = sum(1 for f in user_dict_dir.iterdir()
                         if f.is_file() and f.suffix.lower() in ('.mdx', '.json', '.csv'))
    if user_dict_count:
        print(f"  📚 发现 {user_dict_count} 部用户词典")

    # 复制默认收藏（如果用户还未个性化）
    if not config.FAVORITES_PATH.exists() and config.FAVORITES_DEFAULT_PATH.exists():
        import shutil
        shutil.copy2(str(config.FAVORITES_DEFAULT_PATH), str(config.FAVORITES_PATH))
        print("  📋 已初始化默认收藏列表")

    # Step 5 & 6: 启动服务
    if args.no_browser:
        # 禁止自动打开浏览器时，直接启动不创建浏览器线程
        print_step(5, "服务启动", f"⏳ 正在启动服务于 {host}:{port}...")
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
