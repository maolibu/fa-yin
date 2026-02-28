#!/usr/bin/env python3
"""
从 bulei_catalog_slim.md 提取经→疏对应关系 V10（综合修复版）。

- 栈式树解析：自动处理缩进层级
- 严格 classify_item 分类隔离（杜绝层级倒置）
- 评分取 max（杜绝 if-elif 短路导致的优先级错误）
- get_core_name 支持连续多前缀/后缀剥离
- 【V10】注疏之间全称匹配：同组内若注疏 A 的全称出现在
  注疏 B 的标题中，则额外产生 A→B 对应关系（疏之疏链条）
"""
import re
import csv
import sys
from pathlib import Path
from collections import Counter


# ============================================================
# 1. 文献学分类规则
# ============================================================

# 忽略项（非经非疏）
IGNORE_KW = [
    '禮懺', '懺法', '寶懺', '儀軌', '行法', '念誦', '消災',
    '獻供', '懺願', '日誦', '三昧行法', '科儀', '分門圖',
    '會譯', '異本', '授記經', '鈔經',
]
FORCE_SUTRA_IDS = {'T0226', 'T0840', 'T0841', 'CC0006'}

# 注疏后缀（用于 endswith 匹配）
COMM_SUFFIXES = [
    # 长复合后缀优先
    '玄義釋籤', '玄義文句', '疏義演', '疏鈔玄談', '述文贊',
    '掌中樞要', '了義燈', '筆削記', '裂網疏', '通玄鈔',
    '發源機要', '三德指歸', '妙宗鈔', '聞持記', '圓中鈔',
    '便蒙鈔', '開宗義記', '開宗義決', '隨聽疏決', '隨聽疏',
    '領要鈔', '顯幽鈔', '探玄記',
    # 标准注疏后缀
    '義疏', '玄義', '文句', '述記', '論疏', '釋論', '音義',
    '集解', '要解', '釋籤', '玄贊', '玄論', '遊意', '游意',
    '宗要', '義記', '略纂', '纂要', '科文', '科註', '科注',
    '疏鈔', '疏注', '疏科', '疏記', '演義', '科拾',
    '句解', '通義', '會義', '精解', '綸貫', '會解',
    '統論', '正眼', '觀心釋', '略談', '音釋', '淺解',
    '部旨', '演古', '直說', '心印疏', '訂義', '闡說',
    '心鏡', '近釋', '析義', '句釋', '類解', '集註',
    '集注', '直解', '纂註', '纂注', '捷要', '續疏',
    '會釋', '釋記', '補註', '補注', '宗通', '偈釋',
    '決疑', '采微', '銷釋', '入疏', '合論', '合註',
    '合注', '發隱', '問辯', '讀教記', '格言', '別抄',
    '義蘊', '學記', '俗詮', '證義', '搜玄', '綱目',
    '略策', '述贊', '寶窟', '照解', '順正記', '新記',
    '攝釋', '決擇記', '衷論', '融心解', '正觀記', '圖頌',
    '同異集', '開決記', '廣釋', '略述', '開蒙', '大意',
    '論義', '擊節', '卓解', '知音', '正訛', '正解',
    '石注', '郢說', '指掌', '指疏', '筆記', '通說',
    '纂釋', '淺說', '略說', '旨贊', '挾註', '順硃',
    '初津', '料簡', '約意', '要集', '補遺', '贅言',
    '規矩', '解義', '釋義', '釋疑', '簡註', '評林',
    '懸談', '懸示', '評註', '評注', '概論', '提綱',
    '釋要', '小談', '直談', '要論', '添足', '貫義',
    '際決', '開度', '斲輪解', '請益說', '經鎞',
    '淺註', '淺注', '略註', '略注', '彙纂', '如是經義',
    '如是解', '易解', '口訣', '破空論', '為為章',
    '膚說', '條箇', '會本', '私志', '游刃', '無我疏',
    '扶新論', '約論', '指南', '通贊', '玄疏', '略疏',
    '注解', '註解', '注釋', '論記', '私記',
    # 短后缀放最后（只 endswith 匹配）
    '疏', '鈔', '抄', '記', '解', '註', '注', '講', '述',
    '贊', '讚', '科', '釋',
]


def classify_item(title, item_id=''):
    """
    对单条目进行文献学分类。
    返回: 'original', 'commentary', 'ignore'
    """
    # 强制分类
    if item_id in FORCE_SUTRA_IDS:
        return 'original'

    # 忽略项
    for kw in IGNORE_KW:
        if kw in title:
            return 'ignore'

    # 预处理：去掉末尾卷数
    clean = re.sub(r'[（(].*?[）)]', '', title)  # 去括号内容
    clean = re.sub(r'(卷[上中下一二三四五六七八九十百\d]+)$', '', clean).strip()

    # 「頌」结尾 → 原论
    if clean.endswith('頌'):
        return 'original'

    # 后缀匹配（长后缀优先）
    for suf in COMM_SUFFIXES:
        if clean.endswith(suf):
            return 'commentary'

    # 经/律/论/戒本 结尾 → 原典
    if re.search(r'(經|律|論|戒本|羯磨|法門經)$', clean):
        return 'original'

    # 兜底：标题中间含注疏关键词
    mid_kw = [kw for kw in COMM_SUFFIXES if len(kw) >= 2]
    for kw in mid_kw:
        if kw in clean:
            return 'commentary'

    return 'original'


# ============================================================
# 2. 核心名提取与匹配
# ============================================================

def get_core_name(title):
    """提取经名核心部分，用于匹配"""
    t = re.sub(r'^(佛說|大乘|聖佛母|佛母|大方廣佛|大方廣|御注|新譯|佛垂|御註)', '', title)
    t = re.sub(r'(波羅蜜多經|波羅蜜經|波羅蜜多|波羅蜜|經|律|論|本願|功德|大明呪)$', '', t)
    return t.strip()


def match_commentary_to_sutras(c_title, sutras):
    """
    为一部注疏匹配最合适的原经。
    策略: 多种匹配方式取 max 分 → 取最高分
    """
    if len(sutras) == 1:
        return sutras

    c_core = get_core_name(c_title)
    scored = []

    for sid, stitle in sutras:
        s_core = get_core_name(stitle)
        candidates = []  # 收集各匹配策略的得分，取最高

        # 策略 1: 经名全称在注疏标题中（最精确，权重最高）
        if stitle in c_title:
            candidates.append(len(stitle) * 10)
        # 策略 2: 经名核心在注疏标题中
        if len(s_core) >= 2 and s_core in c_title:
            candidates.append(len(s_core) * 10)
        # 策略 3: 注疏核心在经名中
        if len(c_core) >= 2 and c_core in stitle:
            candidates.append(len(c_core) * 8)
        # 策略 4: 逐字截断匹配（至少需要匹配前 3 个字）
        core = stitle.replace('佛說', '').replace('佛说', '')
        for ln in range(min(len(core), 12), 2, -1):
            if core[:ln] in c_title:
                candidates.append(ln)
                break

        score = max(candidates) if candidates else 0
        if score > 0:
            scored.append((score, sid, stitle))

    # 如果完全没有匹配分数，绝对不能"瞎猜"，直接抛弃
    if not scored:
        return []

    # 取最高分的匹配项
    scored.sort(reverse=True)
    top = scored[0][0]
    return [(s[1], s[2]) for s in scored if s[0] == top]


# ============================================================
# 3. 栈式树解析（核心）
# ============================================================

ITEM_RE = re.compile(r'`([A-Za-z0-9]+)`\s+(.+)')
BOLD_RE = re.compile(r'^\s*-\s+\*\*(.+?)\*\*\s*$')


def parse_and_extract(filepath):
    """
    栈式解析 + classify_item 严格分类。

    遇到 📖 行 → 压栈新 group
    遇到 **bold** 行 → 压栈维护缩进层级（不影响分类决策）
    遇到 `ID` 行 → 由 classify_item 决定归类
    缩进变浅 → 自动弹出
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    groups = []
    # 栈元素: (缩进, group)
    stack = []

    for line in lines:
        if not line.strip():
            continue

        expanded = line.replace('\t', '    ')
        indent = len(expanded) - len(expanded.lstrip())
        content = line.strip()

        # 弹出缩进 >= 当前行的栈元素
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if '📖' in content:
            # 新的经疏组
            new_group = {
                'title': content,
                'originals': [],
                'commentaries': [],
            }
            groups.append(new_group)
            stack.append((indent, new_group))
        else:
            # 粗体子区标题 → 仅用于维护缩进层级
            bold_match = BOLD_RE.match(line)
            if bold_match and stack:
                parent_group = stack[-1][1]
                stack.append((indent, parent_group))
                continue

            # 检查是否为条目
            item_match = ITEM_RE.search(content)
            if item_match and stack:
                item_id = item_match.group(1)
                item_title = item_match.group(2).strip()
                current_group = stack[-1][1]

                # 严格执行 classify_item 分类隔离
                cls = classify_item(item_title, item_id)
                if cls == 'ignore':
                    continue
                if cls == 'original':
                    current_group['originals'].append((item_id, item_title))
                elif cls == 'commentary':
                    current_group['commentaries'].append((item_id, item_title))

    return groups


# ============================================================
# 4. 生成匹配关系
# ============================================================

def extract_relations(groups):
    """从组中提取 经→疏 对应，并补充疏之疏关系"""
    results = []

    for group in groups:
        originals = group['originals']
        comms = group['commentaries']

        if not originals or not comms:
            continue

        # 第一轮：经 → 疏 匹配
        for c_id, c_title in comms:
            matched = match_commentary_to_sutras(c_title, originals)
            for o_id, o_title in matched:
                results.append((o_id, o_title, c_id, c_title))

        # 第二轮：疏 → 疏 全称匹配（疏之疏链条）
        # 如果注疏 A 的全称出现在注疏 B 的标题中，则 A 是 B 的 base text
        if len(comms) >= 2:
            for a_id, a_title in comms:
                for b_id, b_title in comms:
                    if a_id == b_id:
                        continue
                    # A 的全称必须出现在 B 的标题中，
                    # 且 B 的标题要比 A 长（B 是对 A 的进一步注释）
                    if a_title in b_title and len(b_title) > len(a_title):
                        results.append((a_id, a_title, b_id, b_title))
                    else:
                        # 容错：A 标题可能有前缀（佛說/大乘等），剥离后再试
                        a_stripped = re.sub(
                            r'^(佛說|大乘|聖佛母|佛母|大方廣佛|大方廣|御注|新譯|佛垂|御註)',
                            '', a_title)
                        if a_stripped != a_title and a_stripped in b_title and len(b_title) > len(a_stripped):
                            results.append((a_id, a_title, b_id, b_title))

    # 去重 + 过滤已知误配
    seen = set()
    unique = []
    for r in results:
        key = (r[0], r[2])
        if key in seen:
            continue
        # 过滤：同名异版互指（如 T1567↔K1482 都叫「大乘中觀釋論」）
        if r[1] == r[3]:
            continue
        # 过滤：攝大乘論釋 → 攝大乘論釋論（釋不是釋論的 base text）
        if r[1].endswith('攝大乘論釋') and r[3] == '攝大乘論釋論':
            continue
        seen.add(key)
        unique.append(r)

    return unique


# ============================================================
# 5. 主函数
# ============================================================

def main():
    base = Path(__file__).parent
    catalog = base / 'bulei_catalog_slim.md'
    output = base / 'sutra_commentary_pairs.csv'

    if not catalog.exists():
        print(f"❌ 找不到 {catalog}")
        sys.exit(1)

    print(f"📄 解析: {catalog}")
    groups = parse_and_extract(catalog)

    valid_groups = [g for g in groups if g['originals'] and g['commentaries']]
    print(f"📖 找到 {len(valid_groups)} 个有效经疏组")

    for g in valid_groups:
        ns, nc = len(g['originals']), len(g['commentaries'])
        flag = ' ⚠️' if ns > 10 else ''
        # 只打印前 65 个字符以免过长
        print(f"  经{ns:3d} 疏{nc:3d}{flag} | {g['title'][:65]}")

    relations = extract_relations(groups)

    with open(output, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['sutra_id', 'sutra_title', 'commentary_id', 'commentary_title'])
        w.writerows(relations)

    # 统计
    s_ids = set(r[0] for r in relations)
    c_ids = set(r[2] for r in relations)
    c_count = Counter(r[2] for r in relations)
    print(f"\n{'='*50}")
    print(f"✅ 共 {len(relations)} 对经→疏")
    print(f"   原经/论: {len(s_ids)} 部, 注疏: {len(c_ids)} 部")

    dist = Counter(c_count.values())
    print(f"\n注疏对应经数分布:")
    for n in sorted(dist.keys()):
        print(f"  {n:2d}部经: {dist[n]:3d}部注疏")

    anomalies = [(cid, cnt) for cid, cnt in c_count.items() if cnt > 8]
    if anomalies:
        print(f"\n⚠️  对应 >8 部经 ({len(anomalies)} 部):")
        for cid, cnt in sorted(anomalies, key=lambda x: -x[1])[:10]:
            ct = [r[3] for r in relations if r[2] == cid][0][:35]
            sids = [r[0] for r in relations if r[2] == cid][:5]
            print(f"  {cid:8s} {ct:35s} → {cnt}部: {', '.join(sids)}")

    print(f"\n💾 输出: {output}")


if __name__ == '__main__':
    main()
