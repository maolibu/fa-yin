#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import websockets


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import config


DEFAULT_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_VIEWPORT = (1440, 1200)
NARROW_VIEWPORT = (1100, 1200)
PREFERRED_SUTRA_ID = "T0001"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture reader screenshots with Chrome DevTools Protocol.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Running service base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--sutra-id",
        default="",
        help="Sutra ID to capture. If omitted, the script auto-picks one from cbeta_search.db.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Required output directory; use an isolated test-artifact path.",
    )
    parser.add_argument(
        "--chrome-path",
        default="",
        help="Optional Chrome binary path override.",
    )
    parser.add_argument(
        "--keep-temp-profile",
        action="store_true",
        help="Keep the temporary Chrome profile directory for debugging.",
    )
    return parser.parse_args()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_json(url: str, *, method: str = "GET") -> dict:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def wait_http_json(url: str, *, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return read_json(url)
        except Exception as exc:  # pragma: no cover - best effort polling
            last_error = exc
            time.sleep(0.2)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Timed out waiting for {url}")


def choose_sutra(db_path: Path) -> tuple[str, str, int]:
    if not db_path.exists():
        return PREFERRED_SUTRA_ID, PREFERRED_SUTRA_ID, 1

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row

        preferred = conn.execute(
            """
            SELECT sutra_id, title, total_juan
            FROM catalog
            WHERE sutra_id = ?
            LIMIT 1
            """,
            (PREFERRED_SUTRA_ID,),
        ).fetchone()
        if preferred:
            return (
                preferred["sutra_id"],
                preferred["title"] or preferred["sutra_id"],
                int(preferred["total_juan"] or 1),
            )

        row = conn.execute(
            """
            SELECT sutra_id, title, total_juan
            FROM catalog
            WHERE total_juan BETWEEN 2 AND 20
            ORDER BY total_juan DESC, sutra_id ASC
            LIMIT 1
            """
        ).fetchone()
        if row:
            return row["sutra_id"], row["title"] or row["sutra_id"], int(row["total_juan"] or 1)

        fallback = conn.execute(
            """
            SELECT sutra_id, title, total_juan
            FROM catalog
            ORDER BY sutra_id ASC
            LIMIT 1
            """
        ).fetchone()
        if fallback:
            return (
                fallback["sutra_id"],
                fallback["title"] or fallback["sutra_id"],
                int(fallback["total_juan"] or 1),
            )
    finally:
        conn.close()

    return PREFERRED_SUTRA_ID, PREFERRED_SUTRA_ID, 1


def ensure_service(base_url: str) -> dict:
    try:
        return wait_http_json(f"{base_url.rstrip('/')}/api/health", timeout=5)
    except Exception as exc:
        raise SystemExit(
            f"Service is not reachable at {base_url}. Start launcher.py first.\n{exc}"
        ) from exc


def create_output_dir(raw_output_dir: str) -> Path:
    if not raw_output_dir:
        raise SystemExit("--output-dir is required")
    path = Path(raw_output_dir).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def launch_chrome(chrome_path: str, debug_port: int, viewport: tuple[int, int]) -> tuple[subprocess.Popen[bytes], str]:
    binary = chrome_path or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        raise SystemExit("Chrome/Chromium not found. Use --chrome-path to specify one.")

    profile_dir = tempfile.mkdtemp(prefix="fa_yin_chrome_")
    width, height = viewport
    cmd = [
        binary,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={debug_port}",
        "about:blank",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_http_json(f"http://127.0.0.1:{debug_port}/json/version", timeout=10)
    except Exception:
        proc.terminate()
        with suppress(Exception):
            proc.wait(timeout=3)
        raise
    return proc, profile_dir


def create_target(debug_port: int, url: str) -> dict:
    encoded = urllib.parse.quote(url, safe="")
    target_url = f"http://127.0.0.1:{debug_port}/json/new?{encoded}"
    request = urllib.request.Request(target_url, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError:
        # Older Chrome builds may still accept GET here.
        with urllib.request.urlopen(target_url, timeout=10) as response:
            return json.load(response)


def close_target(debug_port: int, target_id: str) -> None:
    close_url = f"http://127.0.0.1:{debug_port}/json/close/{target_id}"
    with suppress(Exception):
        urllib.request.urlopen(close_url, timeout=5).read()


BLOCK_WRITE_REQUESTS_JS = r"""
(() => {
  if (window.__faYinScreenshotWritesBlocked) return true;
  window.__faYinScreenshotWritesBlocked = true;
  const safeMethods = new Set(['GET', 'HEAD', 'OPTIONS']);
  const methodOf = (input, init) => String(
    (init && init.method) || (input && input.method) || 'GET'
  ).toUpperCase();

  const originalFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const method = methodOf(input, init || {});
    if (!safeMethods.has(method)) {
      return Promise.resolve(new Response(
        JSON.stringify({ok: true, blocked_by_screenshot: true, method}),
        {status: 200, headers: {'Content-Type': 'application/json'}}
      ));
    }
    return originalFetch(input, init);
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, ...args) {
    this.__faYinMethod = String(method || 'GET').toUpperCase();
    return originalOpen.call(this, method, ...args);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    if (!safeMethods.has(this.__faYinMethod || 'GET')) {
      this.abort();
      return;
    }
    return originalSend.apply(this, args);
  };
  navigator.sendBeacon = function () { return true; };
  return true;
})()
"""


class CDPClient:
    def __init__(self, websocket_url: str):
        self.websocket_url = websocket_url
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self._message_id = 0

    async def __aenter__(self) -> "CDPClient":
        self.websocket = await websockets.connect(self.websocket_url, max_size=None)
        await self.call("Page.enable")
        await self.call("Runtime.enable")
        await self.call(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": BLOCK_WRITE_REQUESTS_JS},
        )
        await self.evaluate(BLOCK_WRITE_REQUESTS_JS)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None

    async def call(self, method: str, params: dict | None = None) -> dict:
        if self.websocket is None:
            raise RuntimeError("WebSocket is not connected")

        self._message_id += 1
        message_id = self._message_id
        payload = {
            "id": message_id,
            "method": method,
            "params": params or {},
        }
        await self.websocket.send(json.dumps(payload))

        while True:
            raw = await self.websocket.recv()
            data = json.loads(raw)
            if data.get("id") != message_id:
                continue
            if "error" in data:
                raise RuntimeError(f"{method} failed: {data['error']}")
            return data.get("result", {})

    async def evaluate(self, expression: str, *, return_by_value: bool = True):
        result = await self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": return_by_value,
                "userGesture": True,
                "includeCommandLineAPI": True,
            },
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JavaScript evaluation failed: {result['exceptionDetails']}")
        remote = result.get("result", {})
        if return_by_value:
            return remote.get("value")
        return remote

    async def set_viewport(self, width: int, height: int) -> None:
        await self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
                "screenWidth": width,
                "screenHeight": height,
            },
        )

    async def screenshot(self, path: Path) -> None:
        result = await self.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
            },
        )
        image = base64.b64decode(result["data"])
        path.write_bytes(image)


def reader_ready_js(
    *,
    require_split: bool = False,
    writing_mode: str = "",
    current_juan: int | None = None,
    split_juan: int | None = None,
) -> str:
    js_current_juan = "null" if current_juan is None else str(current_juan)
    js_split_juan = "null" if split_juan is None else str(split_juan)
    js_writing_mode = json.dumps(writing_mode or "")
    js_require_split = "true" if require_split else "false"
    return f"""
(() => {{
  const root = document.querySelector('[x-data]');
  const left = document.getElementById('reader-content');
  const right = document.getElementById('reader-right-content');
  if (!root || !left || !window.Alpine) return false;
  const app = Alpine.$data(root);
  const leftText = (left.innerText || '').replace(/\\s+/g, '');
  if (leftText.length < 80 || leftText.includes('正在加载经文')) return false;
  if ({js_writing_mode} && app.writingMode !== {js_writing_mode}) return false;
  if ({js_current_juan} !== null && Number(app.currentJuan) !== {js_current_juan}) return false;
  if ({js_require_split}) {{
    if (!app.splitMode || !right) return false;
    const rightText = (right.innerText || '').replace(/\\s+/g, '');
    if (rightText.length < 80 || rightText.includes('在对照工作台中选择经文')) return false;
    if ({js_split_juan} !== null && Number(app.splitJuan) !== {js_split_juan}) return false;
  }}
  return true;
}})()
"""


NORMALIZE_READER_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  if (!root || !window.Alpine) return { ok: false, reason: 'reader_not_ready' };
  const app = Alpine.$data(root);
  app._syncSettingsToServer = function () {};
  app._syncCompareToServer = function () {};
  app._syncAiToServer = function () {};
  app._syncCommentaryToServer = function () {};
  app.compareItems = [{ id: app.sutraId, title: app.sutraTitle, commentaries: [] }];
  app.activePanel = null;
  app.fontSize = '20';
  app.lineHeight = '2.0';
  app.textVariant = 'original';
  app.fontStyle = 'songti';
  app.themeMode = 'dark';
  document.body.classList.remove('theme-light');
  app.closeSplit();
  app.applySettings();
  app._applyFontStyle();
  app.setWritingMode('horizontal');
  return {
    ok: true,
    sutraId: app.sutraId,
    sutraTitle: app.sutraTitle,
    totalJuan: Number(app.totalJuan || 1)
  };
})()
"""


METRICS_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  const app = (root && window.Alpine) ? Alpine.$data(root) : null;
  const left = document.getElementById('reader-content');
  const right = document.getElementById('reader-right-content');
  const leftHeader = document.querySelector('.reader-sticky-top');
  const rightHeader = document.querySelector('.reader-right-header');
  const layout = document.getElementById('reader-layout');
  return {
    writingMode: app ? app.writingMode : null,
    splitMode: app ? app.splitMode : null,
    currentJuan: app ? Number(app.currentJuan) : null,
    splitJuan: app && app.splitMode ? Number(app.splitJuan) : null,
    leftHeaderHeight: leftHeader ? Math.round(leftHeader.getBoundingClientRect().height) : null,
    rightHeaderHeight: rightHeader ? Math.round(rightHeader.getBoundingClientRect().height) : null,
    leftScrollLeft: left ? left.scrollLeft : null,
    leftScrollTop: left ? left.scrollTop : null,
    leftClientWidth: left ? left.clientWidth : null,
    leftScrollWidth: left ? left.scrollWidth : null,
    rightScrollLeft: right ? right.scrollLeft : null,
    rightScrollTop: right ? right.scrollTop : null,
    rightClientWidth: right ? right.clientWidth : null,
    rightScrollWidth: right ? right.scrollWidth : null,
    layoutClasses: layout ? layout.className : null,
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight
    }
  };
})()
"""


HORIZONTAL_SINGLE_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  const app = Alpine.$data(root);
  app.activePanel = null;
  app.closeSplit();
  app.setWritingMode('horizontal');
  return { ok: true };
})()
"""


VERTICAL_SINGLE_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  const app = Alpine.$data(root);
  app.activePanel = null;
  app.closeSplit();
  app.setWritingMode('vertical');
  return { ok: true };
})()
"""


HORIZONTAL_SPLIT_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  const app = Alpine.$data(root);
  app.activePanel = null;
  app.setWritingMode('horizontal');
  app.loadInRightPanel({ id: app.sutraId, title: app.sutraTitle });
  return { ok: true };
})()
"""


VERTICAL_SPLIT_JS = r"""
(() => {
  const root = document.querySelector('[x-data]');
  const app = Alpine.$data(root);
  app.activePanel = null;
  if (!app.splitMode) {
    app.loadInRightPanel({ id: app.sutraId, title: app.sutraTitle });
  }
  app.setWritingMode('vertical');
  return { ok: true };
})()
"""


def juan_change_js(target_juan: int) -> str:
    return f"""
(() => {{
  const root = document.querySelector('[x-data]');
  const app = Alpine.$data(root);
  app.activePanel = null;
  if (Number(app.currentJuan) !== {target_juan}) {{
    app.currentJuan = {target_juan};
    app.loadJuan();
  }}
  if (app.splitMode && Number(app.splitJuan) !== {target_juan}) {{
    app.splitJuan = {target_juan};
    app.loadSplitJuan();
  }}
  return {{ ok: true, targetJuan: {target_juan} }};
}})()
"""


async def wait_for(client: CDPClient, expression: str, *, timeout: float = 15.0, interval: float = 0.2) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = await client.evaluate(expression)
        if value:
            return
        await asyncio.sleep(interval)
    raise TimeoutError("Timed out waiting for page state")


async def stabilize_page(client: CDPClient, ready_expression: str) -> None:
    await wait_for(client, "document.readyState === 'complete'", timeout=15)
    await client.evaluate("document.fonts ? document.fonts.ready.then(() => true) : true")
    await wait_for(client, ready_expression, timeout=20)
    await asyncio.sleep(0.6)
    await client.evaluate("document.fonts ? document.fonts.ready.then(() => true) : true")


async def capture_state(
    client: CDPClient,
    output_dir: Path,
    *,
    name: str,
    width: int,
    height: int,
    action_js: str,
    ready_js: str,
) -> dict:
    await client.set_viewport(width, height)
    await client.evaluate(action_js)
    await stabilize_page(client, ready_js)
    screenshot_path = output_dir / f"{name}.png"
    await client.screenshot(screenshot_path)
    metrics = await client.evaluate(METRICS_JS)
    return {
        "name": name,
        "file": screenshot_path.name,
        "viewport": {"width": width, "height": height},
        "metrics": metrics,
    }


async def run_capture(args: argparse.Namespace) -> Path:
    base_url = args.base_url.rstrip("/")
    health = ensure_service(base_url)
    output_dir = create_output_dir(args.output_dir)

    if args.sutra_id:
        sutra_id = args.sutra_id.strip()
        sutra_title = sutra_id
        total_juan = 1
    else:
        sutra_id, sutra_title, total_juan = choose_sutra(config.CBETA_SEARCH_DB)

    target_url = f"{base_url}/read/{urllib.parse.quote(sutra_id)}"
    debug_port = find_free_port()
    chrome_proc = None
    profile_dir = ""
    target = None

    try:
        chrome_proc, profile_dir = launch_chrome(args.chrome_path, debug_port, DEFAULT_VIEWPORT)
        target = create_target(debug_port, "about:blank")

        manifest = {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "base_url": base_url,
            "sutra": {
                "id": sutra_id,
                "title": sutra_title,
                "total_juan": total_juan,
                "url": target_url,
            },
            "health": health,
            "write_requests_blocked_before_navigation": True,
            "screenshots": [],
        }

        async with CDPClient(target["webSocketDebuggerUrl"]) as client:
            await client.call("Page.navigate", {"url": target_url})
            await stabilize_page(client, reader_ready_js())
            normalized = await client.evaluate(NORMALIZE_READER_JS)
            if not normalized or not normalized.get("ok"):
                raise RuntimeError(f"Failed to normalize reader state: {normalized}")
            await asyncio.sleep(1.0)
            normalized = await client.evaluate(NORMALIZE_READER_JS)
            if not normalized or not normalized.get("ok"):
                raise RuntimeError(f"Failed to re-normalize reader state: {normalized}")
            await stabilize_page(
                client,
                reader_ready_js(require_split=False, writing_mode="horizontal", current_juan=1),
            )

            manifest["sutra"]["title"] = normalized.get("sutraTitle") or manifest["sutra"]["title"]
            manifest["sutra"]["total_juan"] = int(normalized.get("totalJuan") or manifest["sutra"]["total_juan"])

            manifest["screenshots"].append(
                await capture_state(
                    client,
                    output_dir,
                    name="01_horizontal_single",
                    width=DEFAULT_VIEWPORT[0],
                    height=DEFAULT_VIEWPORT[1],
                    action_js=HORIZONTAL_SINGLE_JS,
                    ready_js=reader_ready_js(require_split=False, writing_mode="horizontal", current_juan=1),
                )
            )
            manifest["screenshots"].append(
                await capture_state(
                    client,
                    output_dir,
                    name="02_vertical_single",
                    width=DEFAULT_VIEWPORT[0],
                    height=DEFAULT_VIEWPORT[1],
                    action_js=VERTICAL_SINGLE_JS,
                    ready_js=reader_ready_js(require_split=False, writing_mode="vertical", current_juan=1),
                )
            )
            manifest["screenshots"].append(
                await capture_state(
                    client,
                    output_dir,
                    name="03_horizontal_split",
                    width=DEFAULT_VIEWPORT[0],
                    height=DEFAULT_VIEWPORT[1],
                    action_js=HORIZONTAL_SPLIT_JS,
                    ready_js=reader_ready_js(require_split=True, writing_mode="horizontal", current_juan=1, split_juan=1),
                )
            )
            manifest["screenshots"].append(
                await capture_state(
                    client,
                    output_dir,
                    name="04_vertical_split",
                    width=DEFAULT_VIEWPORT[0],
                    height=DEFAULT_VIEWPORT[1],
                    action_js=VERTICAL_SPLIT_JS,
                    ready_js=reader_ready_js(require_split=True, writing_mode="vertical", current_juan=1, split_juan=1),
                )
            )

            if manifest["sutra"]["total_juan"] > 1:
                manifest["screenshots"].append(
                    await capture_state(
                        client,
                        output_dir,
                        name="05_vertical_split_juan2",
                        width=DEFAULT_VIEWPORT[0],
                        height=DEFAULT_VIEWPORT[1],
                        action_js=juan_change_js(2),
                        ready_js=reader_ready_js(require_split=True, writing_mode="vertical", current_juan=2, split_juan=2),
                    )
                )

            manifest["screenshots"].append(
                await capture_state(
                    client,
                    output_dir,
                    name="06_vertical_split_narrow",
                    width=NARROW_VIEWPORT[0],
                    height=NARROW_VIEWPORT[1],
                    action_js=VERTICAL_SPLIT_JS,
                    ready_js=reader_ready_js(require_split=True, writing_mode="vertical"),
                )
            )

        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_dir
    finally:
        if target and target.get("id"):
            close_target(debug_port, target["id"])
        if chrome_proc is not None:
            chrome_proc.terminate()
            with suppress(Exception):
                chrome_proc.wait(timeout=5)
        if profile_dir and not args.keep_temp_profile:
            shutil.rmtree(profile_dir, ignore_errors=True)


def main() -> int:
    args = parse_args()
    try:
        output_dir = asyncio.run(run_capture(args))
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 1

    print(f"Saved screenshots to: {output_dir}")
    print(f"Manifest: {output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
