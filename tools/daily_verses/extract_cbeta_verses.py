"""
从 CBETA 大藏经 Markdown 文件中提取精短偈颂
=============================================
扫描 60_ready/obsidian_vault/output/經文/ 下所有 .md 文件，
提取 blockquote（> ）格式的偈颂段落，筛选出：
  - 句式整齐（每句等长±1字）
  - 精短（4-12句，每句3-7字）
  - 有教理深度（排除过于叙事性的段落）
输出 CSV：偈颂, 出處
"""
import os
import re
import csv
import yaml
import sys
from pathlib import Path
from collections import Counter

BASE_DIR = Path("/data/fjlsc/60_ready/obsidian_vault/output/經文")
OUTPUT_CSV = Path("/data/fjlsc/60_ready/tools/大藏经偈颂.csv")

# 已有偈颂指纹（用于去重）
EXISTING_CSV = Path("/data/fjlsc/60_ready/tools/每日偈颂.csv")


def load_existing_fingerprints():
    """加载现有偈颂指纹"""
    fps = set()
    if not EXISTING_CSV.exists():
        return fps
    with open(EXISTING_CSV, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                t = re.sub(r'[，。、；：！？「」『』（）\s|·　]', '', row[1])
                for n in [6, 10, 14]:
                    if len(t) >= n:
                        fps.add(t[:n])
    return fps


def parse_frontmatter(md_text):
    """解析YAML frontmatter"""
    if not md_text.startswith('---'):
        return {}
    end = md_text.find('---', 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(md_text[3:end]) or {}
    except:
        return {}


def extract_verse_blocks(md_text):
    """
    从Markdown中提取所有 blockquote 偈颂块。
    偈颂格式：以 > 开头的连续行，每行内以全角空格 　 分隔
    返回 list of str（每个元素是一块偈颂的完整文本）
    """
    lines = md_text.split('\n')
    blocks = []
    current_block = []
    
    for line in lines:
        if line.startswith('> '):
            # 提取 > 后面的内容，去掉行尾的两个空格换行
            content = line[2:].rstrip()
            if content.endswith('  '):
                content = content[:-2]
            current_block.append(content)
        else:
            if current_block:
                blocks.append('\n'.join(current_block))
                current_block = []
    
    if current_block:
        blocks.append('\n'.join(current_block))
    
    return blocks


def parse_verse_sentences(verse_text):
    """
    将偈颂文本分解为句子列表。
    偈颂格式：用全角空格 　 和换行分隔
    """
    # 合并为单行
    flat = verse_text.replace('\n', '　')
    # 以全角空格分句
    parts = re.split(r'[　，。；！？、\s]+', flat)
    # 清洗
    sentences = []
    for p in parts:
        p = p.strip()
        # 去除标点
        p = re.sub(r'[，。；！？、：「」『』（）\[\]""''…—·]', '', p)
        if p:
            sentences.append(p)
    return sentences


def score_verse(sentences):
    """
    评估一组偈颂句子的质量和教理深度。
    返回 (是否合格, 分数)
    """
    if len(sentences) < 4 or len(sentences) > 12:
        return False, 0
    
    lens = [len(s) for s in sentences]
    
    # 每句长度须在3-7字
    for l in lens:
        if l < 3 or l > 7:
            return False, 0
    
    # 句长一致性：用众数判断
    counter = Counter(lens)
    mode_len, mode_count = counter.most_common(1)[0]
    
    # 至少80%的句子与众数长度相差不超过1
    matching = sum(1 for l in lens if abs(l - mode_len) <= 1)
    if matching < len(lens) * 0.8:
        return False, 0
    
    # 完美匹配比例
    perfect = sum(1 for l in lens if l == mode_len)
    
    score = 0
    
    # 整齐度
    if perfect == len(lens):
        score += 40  # 完全整齐
    elif perfect >= len(lens) * 0.8:
        score += 30
    else:
        score += 20
    
    # 经典句式（五言、七言）
    if mode_len in (5, 7):
        score += 20
    elif mode_len in (4, 6):
        score += 15
    else:
        score += 10
    
    # 句数（4-8句最佳）
    if 4 <= len(sentences) <= 8:
        score += 20
    elif 8 < len(sentences) <= 12:
        score += 10
    
    # 有教理深度的关键词加分
    full_text = ''.join(sentences)
    depth_keywords = [
        '空', '無我', '涅槃', '菩提', '般若', '法性', '真如', '佛性',
        '無常', '苦', '業', '輪迴', '生死', '解脫', '禪', '定', '慧',
        '慈悲', '布施', '持戒', '忍辱', '精進', '正念', '正見',
        '煩惱', '無明', '覺悟', '菩薩', '如來', '法身', '實相',
        '緣起', '因果', '戒', '道', '修行', '觀', '心',
    ]
    depth_count = sum(1 for kw in depth_keywords if kw in full_text)
    if depth_count >= 3:
        score += 20
    elif depth_count >= 2:
        score += 15
    elif depth_count >= 1:
        score += 10
    
    # 排除叙事性（人名、地名、故事性标记）
    narrative_markers = ['爾時', '世尊', '如是', '佛告', '比丘', '善男子',
                         '汝等', '阿難', '舍利弗', '須菩提']
    narrative_count = sum(1 for m in narrative_markers if m in full_text)
    if narrative_count >= 2:
        score -= 15
    
    return score >= 50, score


def format_verse_for_csv(sentences, mode_len):
    """
    格式化偈颂为CSV格式。
    五言偈：四句一组，以逗号分隔，句号结束
    七言偈同理
    """
    result_parts = []
    for i, s in enumerate(sentences):
        if i > 0 and i % 2 == 0:
            result_parts.append('　')  # 每两句（一联）之间用全角空格
        result_parts.append(s)
        if (i + 1) % 2 == 0:
            result_parts.append('，')
        else:
            result_parts.append('，')
    
    # 简单处理：用逗号分隔每句，末尾句号
    text = '，'.join(sentences) + '。'
    
    # 如果句数是偶数，按两句一组的传统格式
    if len(sentences) % 2 == 0:
        pairs = []
        for i in range(0, len(sentences), 2):
            pairs.append(sentences[i] + '，' + sentences[i+1])
        text = '。'.join(pairs) + '。'
    
    return text


def is_duplicate(text, fingerprints):
    """检查是否与现有偈颂重复"""
    clean = re.sub(r'[，。、；：！？\s　]', '', text)
    for n in [6, 10, 14]:
        if len(clean) >= n and clean[:n] in fingerprints:
            return True
    return False


def process_file(md_path, fingerprints):
    """处理单个MD文件，返回提取到的偈颂列表"""
    results = []
    
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return results
    
    # 解析元信息
    meta = parse_frontmatter(content)
    title = meta.get('title', md_path.stem)
    author = meta.get('author', '')
    
    # 构造出处
    source = f"《{title}》"
    if author:
        # 提取朝代和译者
        source += f"／{author}"
    
    # 提取偈颂块
    blocks = extract_verse_blocks(content)
    
    for block in blocks:
        sentences = parse_verse_sentences(block)
        
        if not sentences:
            continue
        
        ok, score = score_verse(sentences)
        if not ok:
            continue
        
        # 格式化
        text = format_verse_for_csv(sentences, len(sentences[0]))
        
        # 去重
        if is_duplicate(text, fingerprints):
            continue
        
        # 加入指纹防止自身重复
        clean = re.sub(r'[，。、；：！？\s　]', '', text)
        for n in [6, 10, 14]:
            if len(clean) >= n:
                fingerprints.add(clean[:n])
        
        results.append({
            'text': text,
            'source': source,
            'score': score,
        })
    
    return results


def main():
    print("加载现有偈颂指纹...")
    fingerprints = load_existing_fingerprints()
    print(f"  已有 {len(fingerprints)} 条指纹")
    
    # 扫描所有MD文件
    md_files = list(BASE_DIR.rglob('*.md'))
    print(f"找到 {len(md_files)} 个MD文件")
    
    all_verses = []
    processed = 0
    
    for md_path in md_files:
        verses = process_file(md_path, fingerprints)
        all_verses.extend(verses)
        processed += 1
        
        if processed % 500 == 0:
            print(f"  已处理 {processed}/{len(md_files)} 文件，当前收集 {len(all_verses)} 条偈颂")
    
    print(f"处理完成：{processed} 个文件，共提取 {len(all_verses)} 条偈颂")
    
    # 按质量分排序
    all_verses.sort(key=lambda x: x['score'], reverse=True)
    
    # 输出CSV
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['偈颂', '出處'])
        for v in all_verses:
            writer.writerow([v['text'], v['source']])
    
    print(f"\n结果已保存到 {OUTPUT_CSV}")
    print(f"共 {len(all_verses)} 条偈颂")
    
    # 预览前30条
    print(f"\n{'='*60}")
    print("前30条偈颂预览：")
    print(f"{'='*60}")
    for i, v in enumerate(all_verses[:30], 1):
        t = v['text'][:70] + ('...' if len(v['text']) > 70 else '')
        print(f"  {i:2d}. [分={v['score']}] {t}")
        print(f"      ——{v['source']}")

if __name__ == '__main__':
    main()
