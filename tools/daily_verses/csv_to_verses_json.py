"""
每日偈颂 CSV → JSON 转换工具

将 "每日偈颂.csv" 转换为 data/db/verses.json，
供 FastAPI 后端读取。

用法：
    python tools/csv_to_verses_json.py

输入：tools/每日偈颂.csv
输出：data/db/verses.json
"""

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
    # 路径：相对于项目根目录 (60_ready/)
    project_root = Path(__file__).resolve().parent.parent.parent
    csv_path = Path(__file__).resolve().parent / "每日偈颂.csv"
    json_path = project_root / "data" / "db" / "verses.json"

    convert_csv_to_json(csv_path, json_path)
