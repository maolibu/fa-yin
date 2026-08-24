#!/usr/bin/env python3
"""
将 TTF/OTF 字体转换为 WOFF2 格式

从 font/ 目录（或子目录）读取源文件，输出到 fonts_woff2/（扁平结构）。
支持增量转换——已存在的 WOFF2 文件会跳过，使用 --force 强制重新转换。

用法：
    python convert_to_woff2.py                  # 转换所有字体
    python convert_to_woff2.py --force           # 强制全部重新转换

依赖安装：pip install fonttools brotli  （或 conda install fonttools brotli-python）
"""

import argparse
import os
from pathlib import Path
from fontTools.ttLib import TTFont

# 配置路径
SCRIPT_DIR = Path(__file__).resolve().parent
FONT_DIR = SCRIPT_DIR / 'font'
OUTPUT_DIR = SCRIPT_DIR / 'fonts_woff2'

# 仅转换指定子文件夹中的字体文件
SUBDIR_WHITELIST = {'Jigmo', 'WenJinMincho', 'NanoOldSongA'}


def convert_to_woff2(input_path, output_path):
    """将单个字体文件转换为 WOFF2"""
    try:
        print(f"  🔄 转换: {Path(input_path).name}")
        font = TTFont(str(input_path))
        font.flavor = 'woff2'
        font.save(str(output_path))
        font.close()

        # 显示大小对比
        original_size = os.path.getsize(input_path) / 1024 / 1024
        woff2_size = os.path.getsize(output_path) / 1024 / 1024
        ratio = (1 - woff2_size / original_size) * 100
        print(f"    ✅ {original_size:.1f}MB → {woff2_size:.1f}MB (压缩 {ratio:.0f}%)")
        return True
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        return False


def get_output_name(filename):
    """生成输出文件名
    
    TTF → 去掉 .ttf 加 .woff2（如 Jigmo.ttf → Jigmo.woff2）
    OTF → 保留 .otf 加 .woff2（如 SourceHanSerif-VF.otf → SourceHanSerif-VF.otf.woff2）
    """
    p = Path(filename)
    if p.suffix.lower() == '.ttf':
        return p.stem + '.woff2'
    else:
        return filename + '.woff2'


def collect_font_files(font_dir, subdir_whitelist):
    """仅收集指定子文件夹下的 TTF/OTF 文件"""
    exts = {'.ttf', '.otf'}
    files = []
    for subdir in sorted(subdir_whitelist):
        sub_path = Path(font_dir) / subdir
        if not sub_path.exists() or not sub_path.is_dir():
            continue
        for root, _, filenames in os.walk(sub_path):
            for f in sorted(filenames):
                if Path(f).suffix.lower() in exts:
                    files.append(Path(root) / f)
    return files


def main():
    parser = argparse.ArgumentParser(description="TTF/OTF → WOFF2 批量转换")
    parser.add_argument('--force', action='store_true',
                        help="强制重新转换（即使输出文件已存在）")
    args = parser.parse_args()

    print("=" * 60)
    print("TTF/OTF → WOFF2 转换工具")
    print("=" * 60)

    if not FONT_DIR.exists():
        print(f"\n❌ 字体源目录不存在: {FONT_DIR}")
        print("   请将 TTF/OTF 字体文件放入 tools/font_tools/font/ 目录")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 收集指定子文件夹中的字体文件
    font_files = collect_font_files(FONT_DIR, SUBDIR_WHITELIST)

    if not font_files:
        print("\n⚠️  font/ 目录中没有找到 TTF/OTF 文件")
        return

    print(f"\n📁 源目录: {FONT_DIR}")
    print(f"📂 子目录白名单: {', '.join(sorted(SUBDIR_WHITELIST))}")
    print(f"📁 输出目录: {OUTPUT_DIR}")
    print(f"📦 发现 {len(font_files)} 个字体文件\n")

    total = 0
    success = 0
    skipped = 0

    for font_path in font_files:
        out_name = get_output_name(font_path.name)
        out_path = OUTPUT_DIR / out_name

        total += 1

        if out_path.exists() and not args.force:
            print(f"  ⏭️  跳过（已存在）: {out_name}")
            skipped += 1
            continue

        if convert_to_woff2(font_path, out_path):
            success += 1

    failed = total - success - skipped

    print("\n" + "=" * 60)
    print(f"完成: ✅ {success} 成功, ⏭️ {skipped} 跳过, ❌ {failed} 失败")

    # 列出输出目录中所有 WOFF2
    print("\n📋 当前 WOFF2 文件:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        if f.suffix == '.woff2':
            size = f.stat().st_size / 1024 / 1024
            print(f"  {f.name} ({size:.1f}MB)")


if __name__ == '__main__':
    main()
