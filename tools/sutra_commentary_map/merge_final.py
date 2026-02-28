#!/usr/bin/env python3
"""
合并 V10 CSV + cbeta_cf_pairs.json 中的 cf 标签关系,
输出最终的 cbeta_sutra_commentary_map.json。

输入:
  1. sutra_commentary_pairs.csv  — V10 提取的部类目录经疏对
  2. cbeta_cf_pairs.json         — 独立的 CBETA cf 标签数据（51 条）

输出:
  - cbeta_sutra_commentary_map.json  — 合并后的完整映射
  - data/db/commentary_map.default.json — 部署用副本
"""
import csv
import json
from pathlib import Path
from collections import defaultdict

base = Path(__file__).parent

# ============ 加载数据 ============

# V10 CSV（UTF-8-BOM）
v10_pairs = set()
v10_titles = {}
with open(base / 'sutra_commentary_pairs.csv', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        sid, cid = row['sutra_id'], row['commentary_id']
        v10_pairs.add((sid, cid))
        v10_titles[sid] = row['sutra_title']
        v10_titles[cid] = row['commentary_title']

print(f"V10 CSV: {len(v10_pairs)} 对")

# CF 标签（独立文件）
cf_data = []
cf_path = base / 'cf_sutra_commentary_pairs.json'
if cf_path.exists():
    with open(cf_path, encoding='utf-8') as f:
        cf_data = json.load(f)
    print(f"CF 标签: {len(cf_data)} 条")
else:
    print(f"⚠️ 未找到 {cf_path}，跳过 cf 合并")

# 过滤 cf 中 V10 已有的
cf_new = []
for item in cf_data:
    key = (item['sutra_id'], item['commentary_id'])
    if key not in v10_pairs:
        cf_new.append(item)

print(f"CF 中 V10 没有的: {len(cf_new)} 条，全部补入")

# ============ 合并并输出 JSON ============

result = defaultdict(lambda: {'title': '', 'commentaries': []})

# 1. V10 数据
for sid, cid in v10_pairs:
    result[sid]['title'] = v10_titles.get(sid, '')
    result[sid]['commentaries'].append({
        'id': cid,
        'title': v10_titles.get(cid, ''),
        'match_type': 'bulei_catalog'
    })

# 2. 补入 cf 标签
for item in cf_new:
    sid = item['sutra_id']
    cid = item['commentary_id']
    existing_cids = {c['id'] for c in result[sid]['commentaries']}
    if cid not in existing_cids:
        if not result[sid]['title']:
            result[sid]['title'] = item['sutra_title']
        result[sid]['commentaries'].append({
            'id': cid,
            'title': item['commentary_title'],
            'match_type': 'xml_cf_tag'
        })

# 排序
sorted_result = {}
for sid in sorted(result.keys()):
    data = result[sid]
    data['commentaries'] = sorted(data['commentaries'], key=lambda x: x['id'])
    sorted_result[sid] = dict(data)

# 输出
output_path = base / 'cbeta_sutra_commentary_map.json'
deploy_path = base.parent.parent / 'data' / 'db' / 'commentary_map.default.json'

json_str = json.dumps(sorted_result, ensure_ascii=False, indent=2)
for p in [output_path, deploy_path]:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(json_str)

total_pairs = sum(len(d['commentaries']) for d in sorted_result.values())
print(f"\n{'='*60}")
print(f"✅ 最终 JSON:")
print(f"   经/论: {len(sorted_result)} 部")
print(f"   经→疏: {total_pairs} 对")
print(f"     bulei_catalog: {len(v10_pairs)}")
print(f"     xml_cf_tag:    {len(cf_new)}")
print(f"   输出: {output_path}")
print(f"   部署: {deploy_path}")
