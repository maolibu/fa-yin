"""
从92617条CBETA偈颂中精选教理+警策偈颂
策略：
1. 排除近现代（民國）
2. 大幅优先经典偈颂集（法句经、四十二章经、佛遗教经等）
3. 教理深度为核心评分
4. 警策/劝修内容加分
5. 寺志题诗/密教仪轨降分
"""
import csv
import re
from collections import Counter

INPUT_CSV = '大藏经偈颂.csv'
OUTPUT_CSV = '精选教理偈颂.csv'
EXISTING_CSV = '每日偈颂.csv'


def load_existing_fps():
    fps = set()
    try:
        with open(EXISTING_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) >= 2 and row[1].strip():
                    c = re.sub(r'[，。、；：！？「」『』（）\s|·　]', '', row[1])
                    for n in [6, 10]:
                        if len(c) >= n:
                            fps.add(c[:n])
    except:
        pass
    return fps


# ====== 重点经典来源列表 ======
# 这些来源的偈颂直接获得优先权
PRIORITY_SOURCES = {
    # === 偈颂集 ===
    '法句經': 40,
    '法集要頌經': 40,
    '出曜經': 35,
    '法句譬喻經': 35,
    # === 教理纲要经 ===
    '四十二章經': 40,
    '佛遺教經': 40,
    '八大人覺經': 40,
    '佛說無常經': 35,
    '吉祥經': 35,
    '佛本行經': 30,
    '佛所行讚': 30,
    # === 核心大乘经 ===
    '金剛經': 30,
    '金剛般若': 30,
    '心經': 30,
    '般若心經': 30,
    '法華經': 30,
    '華嚴經': 25,
    '楞嚴經': 30,
    '楞伽經': 25,
    '圓覺經': 30,
    '維摩詰': 30,
    '維摩經': 30,
    '涅槃經': 25,
    '大般涅槃': 25,
    '地藏經': 25,
    '藥師經': 25,
    '無量壽經': 25,
    '阿彌陀經': 25,
    '大寶積經': 20,
    '雜阿含經': 20,
    '長阿含經': 20,
    '中阿含經': 20,
    '增一阿含': 20,
    # === 论部名著 ===
    '中論': 30,
    '大智度論': 30,
    '瑜伽師地論': 20,
    '成唯識論': 20,
    '起信論': 30,
    '寶性論': 25,
    '入菩薩行論': 30,
    '十住毘婆沙': 25,
    '大乘莊嚴經論': 25,
    '百法明門論': 25,
    # === 禅宗经典 ===
    '壇經': 40,
    '六祖壇經': 40,
    '信心銘': 40,
    '證道歌': 40,
    '永嘉證道歌': 40,
    '參同契': 35,
    '寶鏡三昧': 35,
    '碧巖錄': 30,
    '碧巖集': 30,
    '無門關': 30,
    '從容錄': 30,
    '傳燈錄': 25,
    '景德傳燈': 25,
    '五燈會元': 25,
    '五燈嚴統': 25,
    '禪林寶訓': 35,
    '叢林盛事': 25,
    '禪關策進': 35,
    '續傳燈錄': 20,
    # === 净土经典 ===
    '淨土十要': 25,
    '龍舒淨土文': 25,
    '觀經': 25,
    '觀無量壽': 25,
    # === 祖师名著 ===
    '費閒歌': 35, # 憨山
    '醒世歌': 35,
    '紫柏尊者全集': 25,
    '靈峯宗論': 30,  # 蕅益
    '竹窗隨筆': 30,  # 蓮池
    '夢遊集': 25,  # 憨山
    '傳心法要': 35,  # 黃檗
    '臨濟錄': 35,
    '趙州錄': 30,
    '指月錄': 25,
    '大慧語錄': 25,
    '大慧書': 25,
    '成佛之道': 25,
    # === 天台 ===
    '摩訶止觀': 20,
    '法華玄義': 20,
    '天台小止觀': 25,
}


def get_source_bonus(source):
    """根据来源给予优先加分"""
    bonus = 0
    for key, val in PRIORITY_SOURCES.items():
        if key in source:
            bonus = max(bonus, val)
    return bonus


def classify_source(source):
    if '民國' in source:
        return 'modern'
    if '日本' in source:
        return 'skip'
    
    translator_marks = ['譯', '鳩摩羅什', '玄奘', '不空', '義淨']
    sutra_kw = ['經》', '律》', '阿含', '般若', '法華', '華嚴',
                '涅槃', '寶積', '楞嚴', '楞伽', '圓覺', '維摩',
                '金剛', '法句', '地藏', '藥師', '觀音', '彌陀',
                '無量壽', '中論', '大智度論', '瑜伽', '唯識']
    
    if any(t in source for t in translator_marks) or any(k in source for k in sutra_kw):
        return 'sutra'
    
    master_kw = ['語錄', '禪師', '法師', '和尚', '大師', '壇經',
                 '傳燈', '五燈', '碧巖', '無門', '信心銘', '證道歌',
                 '禪林', '叢林', '寶訓', '宗鏡']
    if any(k in source for k in master_kw):
        return 'master'
    
    return 'other'


def score_verse(text, source):
    """教理+警策导向的评分"""
    score = 0
    text_len = len(text)
    
    # ====== 0. 硬排除 ======
    if text_len < 10 or text_len > 150:
        return -1
    
    # 寺志/山志/塔铭 降权
    if re.search(r'(寺志|山志|塔|碑|銘|圖|志略)', source):
        score -= 20
    
    # 密教仪轨 降权
    if re.search(r'(念誦|儀軌|真言|陀羅尼|灌頂|曼荼|密教|護摩|壇法)', source):
        score -= 15
    
    # ====== 1. 来源加分 ======
    score += get_source_bonus(source)
    
    # ====== 2. 简洁性 ======
    if text_len <= 30:
        score += 15
    elif text_len <= 50:
        score += 20  # 最佳
    elif text_len <= 70:
        score += 15
    elif text_len <= 100:
        score += 10
    else:
        score += 5
    
    # ====== 3. 句式整齐度 ======
    sents = re.split(r'[，。；！？]', text)
    sents = [s.strip() for s in sents if s.strip() and len(s.strip()) >= 2]
    
    if len(sents) < 2:
        return -1
    
    lens = [len(s) for s in sents]
    counter = Counter(lens)
    mode_len, mode_count = counter.most_common(1)[0]
    matching = sum(1 for l in lens if abs(l - mode_len) <= 1)
    ratio = matching / len(lens) if lens else 0
    
    if ratio >= 0.9 and mode_len in (5, 7):
        score += 20
    elif ratio >= 0.9 and mode_len in (4, 6):
        score += 18
    elif ratio >= 0.8:
        score += 14
    elif ratio >= 0.7:
        score += 8
    else:
        score += 3
    
    # ====== 4. 教理深度（核心权重最大）======
    full = text
    
    # 高权重佛教核心概念
    core_concepts = {
        '空': 4, '般若': 5, '涅槃': 5, '菩提': 5, '法性': 5,
        '真如': 5, '實相': 5, '無我': 5, '緣起': 5, '中道': 5,
        '法身': 4, '佛性': 5, '如來藏': 5, '解脫': 4, '覺悟': 4,
        '無生': 5, '寂滅': 4, '無住': 4, '不二': 5, '自性': 4,
        '唯心': 4, '唯識': 4, '圓覺': 5, '法界': 4, '三昧': 3,
        '輪迴': 4, '生死': 3, '無常': 4, '苦': 3, '無明': 4,
        '煩惱': 3, '業': 3, '因果': 4, '三毒': 4,
        '慈悲': 4, '布施': 3, '持戒': 3, '忍辱': 3,
        '精進': 3, '禪定': 4, '智慧': 4, '六度': 4,
        '正念': 3, '正見': 3, '八正道': 4, '四諦': 4,
        '十二因緣': 4, '三法印': 5, '五蘊': 3,
        '心': 2, '道': 2, '戒': 2, '定': 2, '慧': 2,
        '菩薩': 2, '如來': 2, '佛': 1, '修行': 2,
        '觀': 2, '念': 2, '悟': 3, '迷': 3,
    }
    
    depth_score = 0
    for concept, weight in core_concepts.items():
        if concept in full:
            depth_score += weight
    depth_score = min(depth_score, 35)  # 上限35
    score += depth_score
    
    # ====== 5. 警策/劝修内容 ======
    warning_kw = [
        '無常', '生死', '輪迴', '苦海', '火宅', '迷',
        '放逸', '懈怠', '精進', '勤', '莫', '當',
        '死', '老', '病', '惜', '慎', '戒',
        '惡', '善', '業', '報', '果', '因',
        '回頭', '警', '覺', '醒', '度', '救',
        '勿', '須', '急', '速', '難', '罕',
    ]
    w_count = sum(1 for w in warning_kw if w in full)
    score += min(w_count * 2, 15)
    
    # ====== 6. 惩罚项 ======
    # 注释标记
    if re.search(r'\[\d+\]', text):
        score -= 3
    
    # 叙事性
    narrative = ['爾時', '佛告', '善男子', '善女人', '須菩提', '舍利弗', '阿難']
    n_count = sum(1 for n in narrative if n in text)
    if n_count >= 2:
        score -= 12
    elif n_count >= 1:
        score -= 4
    
    # 纯文学意象但无教理（寺志题诗）—— 有意象但无教理概念则降分
    imagery_only = ['鐘', '鶴', '鷗', '帆', '潮', '渡', '寺', '塔', '殿', '閣']
    img_count = sum(1 for w in imagery_only if w in text)
    if img_count >= 3 and depth_score < 10:
        score -= 10
    
    return score


def main():
    existing_fps = load_existing_fps()
    print(f"已有 {len(existing_fps)} 条指纹")
    
    all_entries = []
    skipped = {'modern': 0, 'skip': 0, 'low': 0, 'dup': 0}
    
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) < 2 or not row[0].strip():
                continue
            text, source = row[0], row[1]
            
            cat = classify_source(source)
            if cat in ('modern', 'skip'):
                skipped[cat] += 1
                continue
            
            # 去重
            c = re.sub(r'[，。、；：！？\s　|]', '', text)
            is_dup = False
            for n in [6, 10]:
                if len(c) >= n and c[:n] in existing_fps:
                    is_dup = True
                    break
            if is_dup:
                skipped['dup'] += 1
                continue
            
            score = score_verse(text, source)
            if score < 35:
                skipped['low'] += 1
                continue
            
            all_entries.append({
                'text': text,
                'source': source,
                'score': score,
                'cat': cat,
            })
    
    print(f"跳过: 近现代={skipped['modern']}, 排除={skipped['skip']}, 低分={skipped['low']}, 重复={skipped['dup']}")
    print(f"达标: {len(all_entries)}")
    
    # 排序取 top
    all_entries.sort(key=lambda x: x['score'], reverse=True)
    
    # 去内部重复
    seen_fps = set()
    final = []
    for entry in all_entries:
        c = re.sub(r'[，。、；：！？\s　|]', '', entry['text'])
        fp = c[:12] if len(c) >= 12 else c
        if fp in seen_fps:
            continue
        seen_fps.add(fp)
        final.append(entry)
        if len(final) >= 2000:
            break
    
    # 统计来源分布
    source_counter = Counter()
    for entry in final:
        m = re.search(r'《([^》]+)》', entry['source'])
        if m:
            source_counter[m.group(1)] += 1
    
    # 输出CSV
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['偈颂', '出處', '分數'])
        for entry in final:
            writer.writerow([entry['text'], entry['source'], entry['score']])
    
    print(f"\n最终精选: {len(final)} 条")
    print(f"已保存到 {OUTPUT_CSV}")
    
    # 来源分布
    print(f"\n来源分布（前20）：")
    for src, cnt in source_counter.most_common(20):
        print(f"  {src}: {cnt}")
    
    # 预览
    print(f"\n{'='*60}")
    print("前30条预览：")
    print(f"{'='*60}")
    for i, e in enumerate(final[:30], 1):
        t = e['text'][:65] + ('...' if len(e['text']) > 65 else '')
        src = e['source'][:40]
        print(f"  {i:2d}. [分={e['score']}] {t}")
        print(f"      ——{src}")

if __name__ == '__main__':
    main()
