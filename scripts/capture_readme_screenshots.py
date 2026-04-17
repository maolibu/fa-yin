#!/usr/bin/env python3
"""重拍 README 用的 12 张截图（暗 6 + 浅 6）。

文件命名遵循 README.md 当前引用：
  01.png 首页（顶部：法印对照 + 警策 + 案头）
  02.png 法脉（祖师面板）
  03.png 阅读器（横排单栏）
  04.png 阅读器（横排对照）
  05.png 阅读器（划词词典）
  06.png 阅读器（直排）
  11-16.png 同上但浅色主题

依赖与 capture_reader_screenshots.py 一致：websockets + 系统 Chrome。
依赖运行中的服务（默认 http://127.0.0.1:8400）。
截图保存到 docs/screenshots/，最后用 Pillow 做无损优化。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from capture_reader_screenshots import (
    CDPClient,
    METRICS_JS,
    close_target,
    create_target,
    ensure_service,
    find_free_port,
    launch_chrome,
    stabilize_page,
    wait_for,
)
import shutil
from contextlib import suppress

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_VIEWPORT = (1280, 820)
SPLIT_VIEWPORT = (1680, 820)
SUTRA_LEFT = "T0235"   # 金剛經
SUTRA_RIGHT = "T1698"  # 金剛般若經疏


HOME_READY_JS = r"""
(() => {
  const sec = document.getElementById('lineage-section');
  const chips = document.querySelectorAll('.lineage-search-chips .chip');
  return !!(sec && chips.length >= 10);
})()
"""

# 折叠首页所有 module 卡片（默认更整洁的视图）
# 同时阻断 save() 防止 headless 改动写回服务器
COLLAPSE_MODULES_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  if (!root || !window.Alpine) return false;
  const app = Alpine.$data(root);
  if (!app.modules) return false;
  if (typeof app.save === 'function') app.save = function () {};
  app.modules.forEach(m => { m.collapsed = true; });
  return true;
})()
"""

LINEAGE_READY_JS = r"""
(() => {
  const tl = document.getElementById('chronicle-container');
  const lin = document.getElementById('lineage-container');
  if (!tl || !lin) return false;
  return tl.querySelectorAll('.chr-dynasty').length > 0;
})()
"""

# 选择溈仰宗祖师（灵祐 A001984），展示完整法脉
SELECT_LINEAGE_FOUNDER_JS = r"""
(() => {
  if (typeof selectPerson !== 'function') return false;
  selectPerson('A001984');
  return true;
})()
"""

# 等待法脉图与人物详情都加载完成
LINEAGE_LOADED_JS = r"""
(() => {
  const detail = document.getElementById('detail-content');
  const linSvg = document.querySelector('#lineage-container svg');
  if (!detail || !linSvg) return false;
  if (detail.querySelector('.ln-empty-state')) return false;
  // 法脉图 svg 内必须有节点
  return linSvg.querySelectorAll('circle, .node, g').length > 5;
})()
"""

READER_READY_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  const left = document.getElementById('reader-content');
  if (!root || !left || !window.Alpine) return false;
  const txt = (left.innerText || '').replace(/\s+/g, '');
  return txt.length > 80 && !txt.includes('正在加載') && !txt.includes('正在加载');
})()
"""

SPLIT_READY_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  const right = document.getElementById('reader-right-content');
  if (!root || !right || !window.Alpine) return false;
  const app = Alpine.$data(root);
  if (!app.splitMode) return false;
  const txt = (right.innerText || '').replace(/\s+/g, '');
  return txt.length > 80;
})()
"""

DICT_READY_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  if (!root || !window.Alpine) return false;
  const app = Alpine.$data(root);
  if (app.activePanel !== 'dict') return false;
  return Array.isArray(app.dictResults) && app.dictResults.length > 0;
})()
"""

VERTICAL_READY_JS = r"""
(() => {
  const layout = document.getElementById('reader-layout');
  const left = document.getElementById('reader-content');
  if (!layout || !left) return false;
  if (!layout.classList.contains('writing-vertical')) return false;
  const txt = (left.innerText || '').replace(/\s+/g, '');
  return txt.length > 80;
})()
"""


def set_theme_js(mode: str) -> str:
    assert mode in ("dark", "light")
    return f"""
(() => {{
  localStorage.setItem('reader_theme', '{mode}');
  if ('{mode}' === 'light') {{
    document.documentElement.classList.add('theme-light');
    document.body.classList.add('theme-light');
  }} else {{
    document.documentElement.classList.remove('theme-light');
    document.body.classList.remove('theme-light');
  }}
  // 阅读器内的 Alpine state 也同步
  const root = document.querySelector('[x-data]');
  if (root && window.Alpine) {{
    const app = Alpine.$data(root);
    if (app && typeof app.setTheme === 'function') app.setTheme('{mode}');
  }}
  return true;
}})()
"""


SCROLL_TOP_JS = "window.scrollTo({top: 0, behavior: 'instant'}); true"

SCROLL_LINEAGE_JS = r"""
(() => {
  const sec = document.getElementById('lineage-section');
  if (!sec) return false;
  sec.scrollIntoView({block: 'start', behavior: 'instant'});
  // 留一点点上边距，让 section 标题有空气
  window.scrollBy({top: -8, behavior: 'instant'});
  return true;
})()
"""

# 阅读器所有 setup 都先跑这一段，避免服务端偏好覆盖主题、避免任何 sync 写回
def _reader_prelude(theme: str) -> str:
    return f"""
  const root = document.querySelector('[x-data]');
  if (!root || !window.Alpine) return false;
  const app = Alpine.$data(root);
  app._syncSettingsToServer = function () {{}};
  app._syncCompareToServer = function () {{}};
  app._syncAiToServer = function () {{}};
  app._syncCommentaryToServer = function () {{}};
  // 关键：禁用从服务端拉取偏好，否则会用 user_data/preferences.json 覆盖主题
  app._loadServerPreferences = function () {{ return Promise.resolve(); }};
  app.themeMode = '{theme}';
  app.setTheme('{theme}');
"""


def normalize_reader_js(theme: str) -> str:
    return f"""
(() => {{
{_reader_prelude(theme)}
  app.activePanel = null;
  if (app.splitMode) app.closeSplit();
  app.setWritingMode('horizontal');
  return true;
}})()
"""


def open_split_js(theme: str) -> str:
    return f"""
(() => {{
{_reader_prelude(theme)}
  app.activePanel = null;
  app.setWritingMode('horizontal');
  app.loadInRightPanel({{ id: '{SUTRA_RIGHT}', title: '金剛般若經疏' }});
  return true;
}})()
"""


def open_dict_js(theme: str) -> str:
    return f"""
(() => {{
{_reader_prelude(theme)}
  if (app.splitMode) app.closeSplit();
  app.activePanel = 'dict';
  app.dictQuery = '般若';
  app.lookupDict();
  return true;
}})()
"""


def open_vertical_js(theme: str) -> str:
    return f"""
(() => {{
{_reader_prelude(theme)}
  app.activePanel = null;
  if (app.splitMode) app.closeSplit();
  app.setWritingMode('vertical');
  return true;
}})()
"""


async def goto(client: CDPClient, url: str) -> None:
    await client.call("Page.navigate", {"url": url})


async def goto_with_theme(client: CDPClient, base_url: str, path: str, theme: str) -> None:
    """先访问任意页面拿到 origin，再设 localStorage，再导航到目标。
    这样 base.html 首屏 inline script 就能读到正确主题，
    地图等只在 init 时读主题的组件不会卡在错误模式。"""
    # 1. 先到一个轻量页面，建立同源 localStorage 上下文
    await client.call("Page.navigate", {"url": base_url + "/api/health"})
    await client.evaluate("document.readyState === 'complete' || true")
    # 2. 写 localStorage（在 base_url origin 下）
    await client.call("Page.navigate", {"url": base_url + "/"})
    await client.evaluate(f"localStorage.setItem('reader_theme', '{theme}')")
    # 3. 真正导航到目标
    await client.call("Page.navigate", {"url": base_url + path})


async def capture(
    client: CDPClient,
    out: Path,
    *,
    name: str,
    width: int,
    height: int,
    setup_js: str,
    ready_js: str,
    settle: float = 0.6,
) -> Path:
    await client.set_viewport(width, height)
    await client.evaluate(setup_js)
    await stabilize_page(client, ready_js)
    await asyncio.sleep(settle)
    path = out / f"{name}.png"
    await client.screenshot(path)
    print(f"  ✓ {name}.png  ({width}x{height})")
    return path


async def capture_theme(
    client: CDPClient,
    base_url: str,
    out: Path,
    *,
    theme: str,
    prefix: str,
) -> list[Path]:
    """完整跑一遍 6 张。prefix 决定文件名前缀（'0' 暗，'1' 浅）。"""
    print(f"\n[{theme}] 开始捕获 {prefix}1-{prefix}6")
    results: list[Path] = []

    # ── 首页两张 ──────────────────────────────────────────
    # 在导航前设主题，确保地图、图谱等只在 init 时读主题的组件能拿到正确值
    await goto_with_theme(client, base_url, "/", theme)
    await stabilize_page(client, "document.readyState === 'complete'")
    await stabilize_page(client, HOME_READY_JS)
    await asyncio.sleep(0.4)

    # 01: 折叠所有 module 卡片再回到顶部
    await client.evaluate(COLLAPSE_MODULES_JS)
    await asyncio.sleep(0.3)
    results.append(await capture(
        client, out,
        name=f"{prefix}1",
        width=DEFAULT_VIEWPORT[0], height=DEFAULT_VIEWPORT[1],
        setup_js=SCROLL_TOP_JS,
        ready_js=HOME_READY_JS,
    ))

    # 02: 滚动到法脉，选「溈仰」展示完整谱系
    await client.evaluate(SCROLL_LINEAGE_JS)
    await stabilize_page(client, LINEAGE_READY_JS)
    await client.evaluate(SELECT_LINEAGE_FOUNDER_JS)
    await stabilize_page(client, LINEAGE_LOADED_JS)
    await asyncio.sleep(1.2)  # 给地图飞入和法脉图布局充分时间
    results.append(await capture(
        client, out,
        name=f"{prefix}2",
        width=DEFAULT_VIEWPORT[0], height=DEFAULT_VIEWPORT[1],
        setup_js=SCROLL_LINEAGE_JS,
        ready_js=LINEAGE_LOADED_JS,
        settle=0.5,
    ))

    # ── 阅读器四张 ───────────────────────────────────────
    await goto_with_theme(client, base_url, f"/read/{SUTRA_LEFT}", theme)
    await stabilize_page(client, "document.readyState === 'complete'")
    await stabilize_page(client, READER_READY_JS)
    # 等 _loadServerPreferences 的 fetch 充分完成（即使会覆盖也无所谓，下一步 normalize 会强制覆回）
    await asyncio.sleep(0.8)
    await client.evaluate(normalize_reader_js(theme))
    await stabilize_page(client, READER_READY_JS)
    await asyncio.sleep(0.4)

    # 03 单栏横排
    results.append(await capture(
        client, out,
        name=f"{prefix}3",
        width=DEFAULT_VIEWPORT[0], height=DEFAULT_VIEWPORT[1],
        setup_js=normalize_reader_js(theme),
        ready_js=READER_READY_JS,
    ))

    # 04 双栏对照
    results.append(await capture(
        client, out,
        name=f"{prefix}4",
        width=SPLIT_VIEWPORT[0], height=SPLIT_VIEWPORT[1],
        setup_js=open_split_js(theme),
        ready_js=SPLIT_READY_JS,
        settle=1.2,
    ))

    # 05 词典浮层
    results.append(await capture(
        client, out,
        name=f"{prefix}5",
        width=DEFAULT_VIEWPORT[0], height=DEFAULT_VIEWPORT[1],
        setup_js=open_dict_js(theme),
        ready_js=DICT_READY_JS,
        settle=1.0,
    ))

    # 06 直排
    results.append(await capture(
        client, out,
        name=f"{prefix}6",
        width=DEFAULT_VIEWPORT[0], height=DEFAULT_VIEWPORT[1],
        setup_js=open_vertical_js(theme),
        ready_js=VERTICAL_READY_JS,
        settle=0.8,
    ))

    return results


async def run(args: argparse.Namespace) -> Path:
    base_url = args.base_url.rstrip("/")
    ensure_service(base_url)
    out = PROJECT_ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    debug_port = find_free_port()
    chrome_proc = None
    profile_dir = ""
    target = None
    try:
        chrome_proc, profile_dir = launch_chrome(args.chrome_path, debug_port, DEFAULT_VIEWPORT)
        target = create_target(debug_port, "about:blank")

        async with CDPClient(target["webSocketDebuggerUrl"]) as client:
            all_paths = []
            all_paths.extend(await capture_theme(client, base_url, out, theme="dark", prefix="0"))
            all_paths.extend(await capture_theme(client, base_url, out, theme="light", prefix="1"))

        # 优化：调用 oxipng / pngquant / Pillow 中可用的一种
        optimize_pngs(all_paths)
        return out
    finally:
        if target and target.get("id"):
            close_target(debug_port, target["id"])
        if chrome_proc is not None:
            chrome_proc.terminate()
            with suppress(Exception):
                chrome_proc.wait(timeout=5)
        if profile_dir and not args.keep_temp_profile:
            shutil.rmtree(profile_dir, ignore_errors=True)


def optimize_pngs(paths: list[Path]) -> None:
    """优先 pngquant（优秀的有损量化），否则 Pillow optimize。"""
    pngquant = shutil.which("pngquant")
    if pngquant:
        print("\n[优化] pngquant --speed 1 --quality 70-90")
        for p in paths:
            before = p.stat().st_size
            tmp = p.with_suffix(".png.opt")
            r = __import__("subprocess").run(
                [pngquant, "--speed", "1", "--quality=70-90", "--strip",
                 "--force", "--output", str(tmp), str(p)],
                capture_output=True,
            )
            if r.returncode == 0 and tmp.exists():
                tmp.replace(p)
            after = p.stat().st_size
            print(f"  {p.name}: {before//1024}KB → {after//1024}KB  (-{100*(before-after)//max(before,1)}%)")
        return

    print("\n[优化] Pillow optimize（pngquant 不存在，效果有限）")
    from PIL import Image
    for p in paths:
        before = p.stat().st_size
        with Image.open(p) as im:
            im.save(p, optimize=True)
        after = p.stat().st_size
        print(f"  {p.name}: {before//1024}KB → {after//1024}KB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--chrome-path", default="")
    parser.add_argument("--keep-temp-profile", action="store_true")
    args = parser.parse_args()
    try:
        out = asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"截图失败: {exc}", file=sys.stderr)
        import traceback; traceback.print_exc()
        return 1
    print(f"\n完成。输出目录: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
