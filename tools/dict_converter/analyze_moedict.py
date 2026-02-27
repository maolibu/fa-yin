"""分析萌典内容，看有多少对佛经阅读有用"""
import json
from collections import Counter

print("加载萌典...")
data = json.load(open("萌典.json", encoding="utf-8"))
print(f"总条目: {len(data)}")

# 统计
single_char = 0       # 单字
two_char = 0          # 双字词
multi_char = 0        # 三字以上
has_bopomofo = 0      # 有注音的
has_definition = 0    # 有释义的
stroke_entries = 0    # 有笔画信息的（纯字典字头）
radical_count = Counter()

# 样本检查
samples = {"单字": [], "双字": [], "三字+": []}

for item in data:
    title = item.get("title", "")
    length = len(title)
    
    if length == 1:
        single_char += 1
        if len(samples["单字"]) < 5:
            samples["单字"].append(title)
    elif length == 2:
        two_char += 1
        if len(samples["双字"]) < 5:
            samples["双字"].append(title)
    else:
        multi_char += 1
        if len(samples["三字+"]) < 5:
            samples["三字+"].append(title)
    
    if item.get("stroke_count"):
        stroke_entries += 1
    
    if item.get("radical"):
        radical_count[item["radical"]] += 1
    
    hets = item.get("heteronyms", [])
    for h in hets:
        if h.get("bopomofo"):
            has_bopomofo += 1
            break
    for h in hets:
        defs = h.get("definitions", [])
        if any(d.get("def") for d in defs):
            has_definition += 1
            break

print(f"\n=== 词条长度分布 ===")
print(f"单字条目:  {single_char:,} ({single_char/len(data)*100:.1f}%)")
print(f"双字词条:  {two_char:,} ({two_char/len(data)*100:.1f}%)")
print(f"三字以上:  {multi_char:,} ({multi_char/len(data)*100:.1f}%)")
print(f"\n=== 内容质量 ===")
print(f"有注音:    {has_bopomofo:,} ({has_bopomofo/len(data)*100:.1f}%)")
print(f"有释义:    {has_definition:,} ({has_definition/len(data)*100:.1f}%)")
print(f"有笔画:    {stroke_entries:,}")
print(f"\n=== 样本 ===")
for k, v in samples.items():
    print(f"{k}: {v}")

# 检查有多少含特殊字符（可能是残缺条目）
weird = sum(1 for item in data if "{" in item.get("title", "") or "}" in item.get("title", ""))
print(f"\n含特殊字符(组字式): {weird:,}")
