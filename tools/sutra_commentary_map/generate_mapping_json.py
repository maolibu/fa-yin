#!/usr/bin/env python3
"""
经文-疏钞映射生成脚本

使用两种可靠数据源建立映射：
  1. xml_cf_tag：CBETA XML 中的 <cf> 标签
  2. folder_hierarchy：bulei_nav.xhtml 目录分组中的经文 ID 范围

原方法③（strict_title_match，基于标题关键字后缀猜测）已移除。
"""
import json
import xml.etree.ElementTree as ET
import re

import os

# 文件路径（相对于脚本所在目录）
_DIR = os.path.dirname(os.path.abspath(__file__))
V3_NAV_FILE = os.path.join(_DIR, '../../../01_data_raw/cbeta/bulei_nav.xhtml')
CF_MAPPING_FILE = os.path.join(_DIR, 'cbeta_cf_mapping.json')
WORK_TITLE_CACHE_FILE = os.path.join(_DIR, 'work_title_cache.json')
MAPPING_OUTPUT_FILE = os.path.join(_DIR, 'cbeta_sutra_commentary_map.json')
NEEDS_REVIEW_FILE = os.path.join(_DIR, 'cbeta_mapping_needs_review.json')

# 注疏关键字（仅用于 CF 互指方向判断）
COMMENTARY_SUFFIX_RE = re.compile(
    r'(疏|解|註|注|記|講|述|贊|讚|抄|鈔|箋|演義|義記|口訣|貫義|直說|'
    r'科|科節|旨槩|大略|部旨|大意|綱目|綸貫|秘錄|撮要|會元|毘婆沙|事義|'
    r'玄義|文句|釋論|論疏|經疏|釋|頌|述記)$'
)


def load_title_cache():
    """加载 work_id -> 标题 的缓存"""
    try:
        with open(WORK_TITLE_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"警告: 无法加载标题缓存: {e}")
        return {}


def format_sutra_id(src_id):
    """将 cf 标签中的纯数字 ID 转为标准格式（如 '0001' -> 'T0001'）"""
    if src_id.isdigit():
        return f"T{src_id.zfill(4)}"
    return src_id


def parse_sutra_id_range(folder_name):
    """
    从目录名中解析经文 ID 范围。
    
    例如：
      'T0474-76 維摩詰經 T14' -> {'T0474', 'T0475', 'T0476'}
      'T0262-65 法華經'       -> {'T0262', 'T0263', 'T0264', 'T0265'}
      'T0279 華嚴經 80卷 T10' -> {'T0279'}
      'T1509 大智度論(100卷) T25' -> {'T1509'}
      '02 中品般若經(大般若經第2-3會) T07-08'  -> set()  (无具体 work_id)
    
    规则：四位数字（如 T0262）是 work_id，两位数字（如 T07）是卷号，忽略卷号。
    """
    sutra_ids = set()
    
    # 匹配模式：前缀字母 + 四位或更多位数字，可选带后缀 -数字
    # 例如 T0262-65, T1509, X0001
    pattern = re.compile(r'([A-Z]+)(\d{4,})(?:-(\d+))?')
    
    for m in pattern.finditer(folder_name):
        canon = m.group(1)      # 如 'T'
        start_num = m.group(2)  # 如 '0262'
        end_suffix = m.group(3) # 如 '65' 或 None
        
        start_id = f"{canon}{start_num}"
        sutra_ids.add(start_id)
        
        if end_suffix:
            # 处理范围：T0262-65 → T0262, T0263, T0264, T0265
            prefix_len = len(start_num) - len(end_suffix)
            prefix = start_num[:prefix_len]
            start_val = int(start_num[prefix_len:])
            end_val = int(end_suffix)
            
            for val in range(start_val + 1, end_val + 1):
                new_id = f"{canon}{prefix}{str(val).zfill(len(end_suffix))}"
                sutra_ids.add(new_id)
    
    return sutra_ids


def extract_direct_work_ids(li_elem):
    """从 <li> 元素中提取直接子节点的 work_id（不递归到子目录）。
    
    只取 li 的直接 cblink（本身就是一个 work），
    以及 li > ol > li > cblink（直属子列表的 work）。
    不会递归到子目录的 ol 中。
    """
    work_ids = []
    
    # 检查 li 本身是否有 cblink（顶层条目）
    cblink = li_elem.find('cblink')
    if cblink is not None and 'href' in cblink.attrib:
        wid = _parse_work_id_from_href(cblink.attrib['href'])
        if wid:
            work_ids.append(wid)
        return work_ids  # 如果li本身就是一个work，没有子目录
    
    # 检查 li > ol > li 的直属子条目
    ol = li_elem.find('ol')
    if ol is None:
        return work_ids
    
    for child_li in ol.findall('li'):
        # 如果子 li 有 span（即子目录），跳过——这些会被单独处理
        child_span = child_li.find('span')
        if child_span is not None:
            continue
        
        # 子 li 直接包含 cblink 的才是 work 条目
        child_cblink = child_li.find('cblink')
        if child_cblink is not None and 'href' in child_cblink.attrib:
            wid = _parse_work_id_from_href(child_cblink.attrib['href'])
            if wid:
                work_ids.append(wid)
    
    return work_ids


def _parse_work_id_from_href(href):
    """从 cblink href 中解析 work_id"""
    match = re.search(r'/([A-Z]+)\d+n([A-Z]?\d+[a-zA-Z]?)(?:_|\.)', href)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return None


def _has_child_slash_folders(li_elem):
    """检查 li 元素是否包含带「／」的子目录"""
    ol = li_elem.find('ol')
    if ol is None:
        return False
    for child_li in ol.findall('li'):
        child_span = child_li.find('span')
        if child_span is not None and child_span.text and '／' in child_span.text:
            return True
    return False


def build_mapping():
    """构建经文-疏钞映射"""
    title_cache = load_title_cache()
    mapping_data = {}
    needs_review = []
    stats = {'cf_tag': 0, 'cf_mutual_skipped': 0, 'folder': 0, 'folder_review': 0}

    # ============================================================
    # 方法 1：加载 CF 映射（最高优先级）
    # ============================================================
    try:
        with open(CF_MAPPING_FILE, 'r', encoding='utf-8') as f:
            cf_mappings = json.load(f)

        # 先检测互指对
        mutual_pairs = set()
        for comm_id, targets in cf_mappings.items():
            for t in targets:
                t_full = format_sutra_id(t)
                if t_full in cf_mappings:
                    for back_t in cf_mappings[t_full]:
                        back_full = format_sutra_id(back_t)
                        if back_full == comm_id:
                            mutual_pairs.add(tuple(sorted([comm_id, t_full])))

        # 对互指对，用标题关键字判断方向
        resolved_directions = {}  # {(a, b): (sutra_id, comm_id)}
        for pair in mutual_pairs:
            a, b = pair
            a_title = title_cache.get(a, '')
            b_title = title_cache.get(b, '')
            a_is_comm = bool(COMMENTARY_SUFFIX_RE.search(a_title))
            b_is_comm = bool(COMMENTARY_SUFFIX_RE.search(b_title))

            if a_is_comm and not b_is_comm:
                resolved_directions[pair] = (b, a)  # b 是经, a 是疏
            elif b_is_comm and not a_is_comm:
                resolved_directions[pair] = (a, b)  # a 是经, b 是疏
            else:
                # 两者都有或都没有注疏后缀，无法判断方向
                needs_review.append({
                    'type': 'cf_mutual_ambiguous',
                    'ids': list(pair),
                    'titles': [title_cache.get(pair[0], '?'), title_cache.get(pair[1], '?')],
                    'reason': '互指但无法通过标题判断方向'
                })
                stats['cf_mutual_skipped'] += 1

        # 处理所有 CF 映射
        for comm_id, targets in cf_mappings.items():
            for target in targets:
                target_id = format_sutra_id(target)
                pair_key = tuple(sorted([comm_id, target_id]))

                # 如果是互指对，使用已解析的方向
                if pair_key in mutual_pairs:
                    if pair_key in resolved_directions:
                        sutra_id, commentary_id = resolved_directions[pair_key]
                        # 只在正确方向时处理（避免双重添加）
                        if comm_id != commentary_id:
                            continue
                        target_id = sutra_id
                    else:
                        continue  # 无法判断方向，跳过

                # 添加映射：comm_id 是注疏，target_id 是经文
                if target_id not in mapping_data:
                    mapping_data[target_id] = {
                        'title': title_cache.get(target_id, "Unknown Title"),
                        'commentaries': []
                    }

                if not any(c['id'] == comm_id for c in mapping_data[target_id]['commentaries']):
                    mapping_data[target_id]['commentaries'].append({
                        'id': comm_id,
                        'title': title_cache.get(comm_id, "Unknown Title"),
                        'match_type': 'xml_cf_tag'
                    })
                    stats['cf_tag'] += 1

    except Exception as e:
        print(f"错误: 加载 CF 映射失败: {e}")

    # ============================================================
    # 方法 2：解析目录结构（只处理叶子级「／」目录）
    # ============================================================
    try:
        tree = ET.parse(V3_NAV_FILE)
        root = tree.getroot()

        for li in root.findall('.//li'):
            span = li.find('span')
            if span is None or span.text is None:
                continue
            folder_name = span.text.strip()

            # 只处理含「／」分隔符的目录
            if '／' not in folder_name:
                continue

            # 跳过有子「／」目录的父级——子目录会单独处理
            if _has_child_slash_folders(li):
                continue

            # 取「／」前的部分解析经文 ID 范围
            before_slash = folder_name.split('／')[0].strip()
            sutra_id_set = parse_sutra_id_range(before_slash)

            # 只取直属子节点的 work_id（不递归）
            all_work_ids = extract_direct_work_ids(li)

            if not all_work_ids:
                continue

            if not sutra_id_set:
                # 目录名没有具体经文 ID，标记为需审核
                needs_review.append({
                    'type': 'folder_no_sutra_ids',
                    'folder_name': folder_name,
                    'work_ids': list(set(all_work_ids)),
                    'reason': '目录名中无法提取具体经文 ID'
                })
                stats['folder_review'] += 1
                continue

            # 按 ID 范围区分经/疏，去重
            all_work_ids_unique = list(dict.fromkeys(all_work_ids))
            sutra_works = [w for w in all_work_ids_unique if w in sutra_id_set]
            commentary_works = [w for w in all_work_ids_unique if w not in sutra_id_set]

            if not sutra_works or not commentary_works:
                continue

            # 建立映射
            for s_id in sutra_works:
                if s_id not in mapping_data:
                    mapping_data[s_id] = {
                        'title': title_cache.get(s_id, "Unknown Title"),
                        'commentaries': []
                    }

                for c_id in commentary_works:
                    if not any(c['id'] == c_id for c in mapping_data[s_id]['commentaries']):
                        mapping_data[s_id]['commentaries'].append({
                            'id': c_id,
                            'title': title_cache.get(c_id, "Unknown Title"),
                            'match_type': 'folder_hierarchy'
                        })
                        stats['folder'] += 1

    except Exception as e:
        print(f"错误: 解析目录结构失败: {e}")

    # ============================================================
    # 输出结果
    # ============================================================
    with open(MAPPING_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapping_data, f, ensure_ascii=False, indent=2)

    if needs_review:
        with open(NEEDS_REVIEW_FILE, 'w', encoding='utf-8') as f:
            json.dump(needs_review, f, ensure_ascii=False, indent=2)

    # 统计报告
    total_comms = sum(len(v['commentaries']) for v in mapping_data.values())
    print("=" * 60)
    print("映射生成完成")
    print("=" * 60)
    print(f"  经文总数: {len(mapping_data)}")
    print(f"  注疏映射总数: {total_comms}")
    print(f"    - xml_cf_tag: {stats['cf_tag']}")
    print(f"    - folder_hierarchy: {stats['folder']}")
    print(f"  CF 互指已跳过（无法判断方向）: {stats['cf_mutual_skipped']}")
    print(f"  需审核条目: {stats['folder_review'] + stats['cf_mutual_skipped']}")
    print(f"  输出文件: {MAPPING_OUTPUT_FILE}")
    if needs_review:
        print(f"  需审核文件: {NEEDS_REVIEW_FILE}")


if __name__ == "__main__":
    build_mapping()
