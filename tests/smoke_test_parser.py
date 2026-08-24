"""
烟雾测试 v3：直接解析 XML 文件（跳过慢速 CBETANav 查找）。
全部结果写入 smoke_test_report.txt。
"""

import argparse
import sys
import os
import re
import time
from pathlib import Path
from html import unescape
from lxml import etree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import config
from core.cbeta_ids import discover_bookcase_xml_files
from core.cbeta_parser import CBETAParser, TEI_NS

# ============================================================
# 配置
# ============================================================
DEFAULT_REPORT_PATH = Path(os.getenv(
    "TEST_OUTPUT_DIR", str(Path(__file__).parent)
)) / "smoke_test_report.txt"

# 去除 HTML 标签
TAG_RE = re.compile(r'<[^>]+>')
# 去除 tooltip/属性内容
ATTR_RE = re.compile(r"(?:data-note-text|title|data-wit)='[^']*'")

# 注释泄漏检测 pattern
LEAK_PATTERNS = [
    (re.compile(r'【大】＊'), '【大】＊'),
    (re.compile(r'【宋】＊'), '【宋】＊'),
    (re.compile(r'【元】＊'), '【元】＊'),
    (re.compile(r'【明】＊'), '【明】＊'),
    (re.compile(r'【三】＊'), '【三】＊'),
    (re.compile(r'＝.{1,8}【(?:宋|元|明|三|聖|甲|乙)】'), '校勘替换式'),
    (re.compile(r'〔.{1,6}〕－【(?:宋|元|明|三|聖)】'), '校勘删除式'),
    (re.compile(r'＋\(.{1,8}\)【(?:宋|元|明|三|聖)】'), '校勘增加式'),
]

# 未解析缺字
UNRESOLVED_GAIJI = re.compile(r'\[CB\d+\]')

NS_MAP = {'tei': TEI_NS}


def strip_html(html):
    """去除 HTML 标签和属性值，提取纯文本"""
    cleaned = ATTR_RE.sub('', html)
    return TAG_RE.sub('', unescape(cleaned))


def find_xml_files(xml_dir):
    """找到所有经文 XML 文件"""
    return discover_bookcase_xml_files(xml_dir)


def main():
    cli = argparse.ArgumentParser(description="全量 CBETA 阅读解析器回归")
    cli.add_argument(
        "--cbeta-base", type=Path, default=config.CBETA_BASE,
        help="Bookcase 根目录（包含 XML/）",
    )
    cli.add_argument(
        "--gaiji-path", type=Path, default=config.GAIJI_PATH,
        help="cbeta_gaiji.json 路径",
    )
    cli.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT_PATH,
        help="报告输出路径",
    )
    cli.add_argument("--expected-count", type=int, default=21960)
    args = cli.parse_args()

    # 初始化解析器（只加载 gaiji 数据）
    parser = CBETAParser(
        cbeta_dir=args.cbeta_base,
        gaiji_path=args.gaiji_path,
        nav=object(),
    )

    xml_files = find_xml_files(args.cbeta_base / "XML")
    total = len(xml_files)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    f = open(args.report, 'w', encoding='utf-8')
    f.write(f"CBETA 解析器烟雾测试报告\n")
    f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"总文件: {total}\n")
    f.write(f"{'='*60}\n\n")

    success = 0
    errors = 0
    leak_count = 0
    gaiji_count = 0
    start = time.time()

    xml_parser = etree.XMLParser(recover=False, huge_tree=True)

    for i, xml_path in enumerate(xml_files):
        file_label = xml_path.stem  # 如 T03n0152_001

        try:
            # 直接解析 XML 文件（跳过 CBETANav）
            tree = etree.parse(str(xml_path), xml_parser)
            root = tree.getroot()
            body = root.xpath("//tei:body", namespaces=NS_MAP)
            if not body:
                f.write(f"[EMPTY] {file_label}: 无 <body>\n")
                errors += 1
                continue

            # 重置注释收集器
            parser._notes = []
            parser._note_idx = 0

            # 渲染
            html = parser._render(body[0])

            # 提取纯文本
            text = strip_html(html)

            # 检查注释泄漏
            found_leak = False
            for pat, label in LEAK_PATTERNS:
                m = pat.search(text)
                if m:
                    ctx_start = max(0, m.start() - 15)
                    ctx_end = min(len(text), m.end() + 15)
                    context = text[ctx_start:ctx_end].replace('\n', ' ')
                    f.write(f"[LEAK] {file_label}: {label} → ...{context}...\n")
                    leak_count += 1
                    found_leak = True
                    break

            # 检查未解析缺字
            gaiji = UNRESOLVED_GAIJI.findall(text)
            if gaiji:
                f.write(f"[GAIJI] {file_label}: {', '.join(gaiji[:3])}\n")
                gaiji_count += 1
            elif not found_leak:
                success += 1

        except Exception as e:
            f.write(f"[ERROR] {file_label}: {type(e).__name__}: {e}\n")
            errors += 1

        # 每 2000 个文件刷新一次
        if (i + 1) % 2000 == 0:
            f.flush()

    elapsed = time.time() - start

    f.write(f"\n{'='*60}\n")
    f.write(f"汇总\n")
    f.write(f"{'='*60}\n")
    f.write(f"耗时: {elapsed:.1f} 秒 ({total/max(elapsed,0.1):.0f} 文件/秒)\n")
    f.write(f"通过: {success}\n")
    f.write(f"注释泄漏: {leak_count}\n")
    f.write(f"缺字问题: {gaiji_count}\n")
    f.write(f"解析错误: {errors}\n")
    f.close()

    failures = []
    if total != args.expected_count:
        failures.append(f"文件数 {total} != {args.expected_count}")
    if errors:
        failures.append(f"解析错误 {errors}")
    if leak_count:
        failures.append(f"注释泄漏 {leak_count}")
    if gaiji_count:
        failures.append(f"未解析缺字 {gaiji_count}")
    print(f"Done. {total} files in {elapsed:.1f}s. Report: {args.report}")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
