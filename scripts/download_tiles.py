"""
离线地图瓦片下载器

下载 CARTO 底图瓦片（亮色 + 暗色），用于离线运行祖师页面地图。
覆盖范围：
  - 全球 zoom 0-5（概览）
  - 亚洲 zoom 6-8（详细，覆盖中国、印度、日本、东南亚）

用法：
    python scripts/download_tiles.py

输出目录：data/tiles/light/ 和 data/tiles/dark/
"""

import os
import sys
import time
import math
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 配置 ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "tiles"

TILE_URLS = {
    "light": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "dark": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
}

SUBDOMAINS = ["a", "b", "c", "d"]

# 全球概览
GLOBAL_ZOOMS = range(0, 6)  # z0-z5

# 亚洲详细（纬度 -15~60，经度 25~155，覆盖印度→日本→东南亚）
ASIA_ZOOMS = range(6, 9)  # z6-z8
ASIA_BBOX = {
    "lat_min": -15,
    "lat_max": 60,
    "lon_min": 25,
    "lon_max": 155,
}

# 下载并发数（对公共服务礼貌一点）
MAX_WORKERS = 4
# 请求间隔（秒）
REQUEST_DELAY = 0.05


# ── 瓦片坐标计算 ──────────────────────────────────────────────
def lat_lon_to_tile(lat, lon, zoom):
    """将经纬度转换为瓦片坐标 (x, y)"""
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    x = max(0, min(x, n - 1))
    y = max(0, min(y, n - 1))
    return x, y


def get_tile_list():
    """生成所有需要下载的瓦片坐标列表"""
    tiles = []

    # 全球 z0-z5：所有瓦片
    for z in GLOBAL_ZOOMS:
        n = 2 ** z
        for x in range(n):
            for y in range(n):
                tiles.append((z, x, y))

    # 亚洲 z6-z8：限定区域
    bbox = ASIA_BBOX
    for z in ASIA_ZOOMS:
        x_min, y_max = lat_lon_to_tile(bbox["lat_min"], bbox["lon_min"], z)
        x_max, y_min = lat_lon_to_tile(bbox["lat_max"], bbox["lon_max"], z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tiles.append((z, x, y))

    return tiles


# ── 下载逻辑 ──────────────────────────────────────────────────
def download_tile(mode, z, x, y):
    """下载单个瓦片"""
    subdomain = SUBDOMAINS[(x + y) % len(SUBDOMAINS)]
    url = TILE_URLS[mode].replace("{s}", subdomain).replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))

    out_dir = BASE_DIR / mode / str(z) / str(x)
    out_file = out_dir / f"{y}.png"

    if out_file.exists():
        return "skip"

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "FaYinDuiZhao-OfflineTiles/1.0 (Buddhist DH Project)",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            out_file.write_bytes(data)
        return "ok"
    except Exception as e:
        return f"err:{e}"


def main():
    tiles = get_tile_list()
    total = len(tiles)
    print(f"瓦片总数: {total} × 2 模式 = {total * 2} 张")
    print(f"输出目录: {BASE_DIR}")
    print()

    for mode in ["light", "dark"]:
        print(f"═══ 下载 {mode} 模式底图 ═══")
        done = 0
        skipped = 0
        errors = 0
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {}
            for z, x, y in tiles:
                f = pool.submit(download_tile, mode, z, x, y)
                futures[f] = (z, x, y)
                time.sleep(REQUEST_DELAY)

            for f in as_completed(futures):
                result = f.result()
                z, x, y = futures[f]
                if result == "skip":
                    skipped += 1
                elif result == "ok":
                    done += 1
                else:
                    errors += 1
                    if errors <= 5:
                        print(f"  ✗ {mode}/{z}/{x}/{y}: {result}")

                total_processed = done + skipped + errors
                if total_processed % 200 == 0 or total_processed == total:
                    elapsed = time.time() - start_time
                    rate = total_processed / elapsed if elapsed > 0 else 0
                    print(f"  [{mode}] {total_processed}/{total}  "
                          f"新下载={done} 跳过={skipped} 错误={errors}  "
                          f"({rate:.0f} 张/秒)")

        elapsed = time.time() - start_time
        print(f"  {mode} 完成: 新下载={done}, 跳过={skipped}, 错误={errors}, 耗时={elapsed:.1f}秒")
        print()

    # 统计最终大小
    total_size = 0
    for p in BASE_DIR.rglob("*.png"):
        total_size += p.stat().st_size
    print(f"✅ 瓦片总大小: {total_size / 1024 / 1024:.1f} MB")
    print(f"   目录: {BASE_DIR}")


if __name__ == "__main__":
    main()
