#!/usr/bin/env python3
"""分析 CBETA XML 中偈颂行长度，以及每行字数（<lb> 标记间距）"""

import xml.etree.ElementTree as ET
import os
import re
from collections import Counter
from pathlib import Path

XML_DIR = Path(__file__).parent.parent / "data" / "raw" / "cbeta" / "XML"
NS = {'tei': 'http://www.tei-c.org/ns/1.0', 'cb': 'http://www.cbeta.org/ns/1.0'}

def text_of(el):
    """获取元素的纯文本（含子元素的 text+tail）"""
    return ''.join(el.itertext())

def analyze_files(max_files=200):
    verse_lengths = Counter()  # 偈颂单行字数分布
    lb_distances = Counter()   # <lb> 间的字数分布（即大藏经每行字数）
    verse_examples = {}        # 记录一些代表性的偈颂例子
    files_scanned = 0

    for root_dir, dirs, files in os.walk(XML_DIR):
        for fname in sorted(files):
            if not fname.endswith('.xml'):
                continue
            if files_scanned >= max_files:
                break
            fpath = os.path.join(root_dir, fname)
            try:
                tree = ET.parse(fpath)
            except Exception:
                continue
            
            root = tree.getroot()
            files_scanned += 1
            
            # 1. 分析偈颂 <l> 行长
            for lg_el in root.iter('{http://www.tei-c.org/ns/1.0}lg'):
                for l_el in lg_el.iter('{http://www.tei-c.org/ns/1.0}l'):
                    txt = text_of(l_el).strip()
                    # 去除标点和空格后的纯字数
                    pure = re.sub(r'[\s　。，、；：「」『』（）！？…—\.\,\;\:\!\?]', '', txt)
                    length = len(pure)
                    if length > 0:
                        verse_lengths[length] += 1
                        # 记录典型例子
                        if length not in verse_examples and len(txt) < 60:
                            verse_examples[length] = (fname, txt)

            # 2. 分析 <lb> 间距（大藏经原版每行字数）
            # 找到所有 <lb> 元素并计算它们之间的文本长度
            body = root.find('.//{http://www.tei-c.org/ns/1.0}body')
            if body is not None:
                all_text = text_of(body)
                # CBETA 的 <lb> 标记格式：n="0001a01" 等，每个代表原版一行
                lb_tags = list(body.iter('{http://www.tei-c.org/ns/1.0}lb'))
                for lb_tag in lb_tags:
                    n_attr = lb_tag.get('n', '')
                    if n_attr:
                        # 从 n 属性可以得知原版版面布局信息
                        pass
        if files_scanned >= max_files:
            break

    print("=" * 60)
    print(f"扫描文件数: {files_scanned}")
    print()

    print("═══ 偈颂单行字数分布 (top 20) ═══")
    print(f"{'字数':>6}  {'出现次数':>8}  {'占比':>8}")
    total_verses = sum(verse_lengths.values())
    for length, count in sorted(verse_lengths.items()):
        pct = count / total_verses * 100
        bar = '█' * int(pct)
        print(f"{length:>6}  {count:>8}  {pct:>7.1f}%  {bar}")
    
    print()
    print(f"总偈颂行数: {total_verses}")
    
    # 分析关键百分位
    sorted_lengths = []
    for length, count in sorted(verse_lengths.items()):
        sorted_lengths.extend([length] * count)
    
    if sorted_lengths:
        p50 = sorted_lengths[len(sorted_lengths) // 2]
        p90 = sorted_lengths[int(len(sorted_lengths) * 0.9)]
        p95 = sorted_lengths[int(len(sorted_lengths) * 0.95)]
        p99 = sorted_lengths[int(len(sorted_lengths) * 0.99)]
        max_len = max(sorted_lengths)
        
        print(f"\n中位数 (P50): {p50} 字")
        print(f"P90: {p90} 字")
        print(f"P95: {p95} 字")
        print(f"P99: {p99} 字")
        print(f"最大值: {max_len} 字")

    print()
    print("═══ 代表性偈颂例子 ═══")
    for length in sorted(verse_examples.keys()):
        fname, txt = verse_examples[length]
        print(f"  [{length}字] {txt}  ({fname})")

    # 3. 版心计算
    print()
    print("═══ 版心宽度计算 ═══")
    if sorted_lengths:
        # 偈颂最宽行 + 2字缩进 + 6字余量 = 版心最小字数
        longest_verse = p95  # 用 P95 避免极端值
        min_chars = longest_verse + 2 + 6  # 2字缩进 + 6字左右余量
        print(f"P95 偈颂行长: {longest_verse} 字")
        print(f"加缩进(2字) + 余量(6字) = {min_chars} 字")
        print(f"建议版心至少能容纳 {min_chars} 字/行")
        print()
        for font_size in [16, 18, 20, 22, 24, 28, 32]:
            width_px = min_chars * font_size
            print(f"  字号 {font_size}px → 版心 ≈ {width_px}px ({width_px/16:.0f}rem)")

if __name__ == '__main__':
    analyze_files(200)
