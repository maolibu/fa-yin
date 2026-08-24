"""
每日偈颂 CSV → JSON 转换工具

将 "每日偈颂.csv" 转换为 data/db/verses.json，
供 FastAPI 后端读取。

用法：
    python tools/daily_verses/csv_to_verses_json.py
    python tools/daily_verses/csv_to_verses_json.py --output /tmp/verses.json

输入：tools/daily_verses/每日偈颂.csv
输出：data/db/verses.json
"""

import argparse
import csv
import json
import re
from pathlib import Path


def convert_csv_to_json(csv_path: Path, json_path: Path):
    """读取 CSV 偈颂文件，清洗后输出 JSON。"""
    verses = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # 跳过表头

        for idx, row in enumerate(reader, start=1):
            if len(row) < 2:
                continue

            verse_text = row[0].strip()
            source = row[1].strip()

            # 跳过空行
            if not verse_text:
                continue

            # 用全角 ｜ 或半角 | 分隔多行偈颂，统一清理空格
            raw_lines = re.split(r'\s*[｜|]\s*', verse_text)
            lines = [line.strip() for line in raw_lines if line.strip()]

            if not lines:
                continue

            verses.append({
                "id": idx,
                "lines": lines,
                "source": source,
            })

    # 确保输出目录存在
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verses, f, ensure_ascii=False, indent=2)

    print(f"✅ 转换完成：{len(verses)} 条偈颂")
    print(f"   输入：{csv_path}")
    print(f"   输出：{json_path}")

    # 打印预览
    for v in verses[:3]:
        print(f"\n   #{v['id']} {v['source']}")
        for line in v["lines"]:
            print(f"      {line}")
    if len(verses) > 3:
        print(f"\n   ... 共 {len(verses)} 条")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description="将每日偈颂 CSV 转换为 JSON")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parent / "每日偈颂.csv",
        help="偈颂 CSV 路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "data" / "db" / "verses.json",
        help="输出 JSON 路径",
    )
    args = parser.parse_args()

    convert_csv_to_json(args.input, args.output)
