import json
from pathlib import Path
from collections import defaultdict

DIR = Path('/data/fjlsc/60_ready/tools/sutra_commentary_map')

with open(DIR / 'work_title_cache.json', encoding='utf-8') as f:
    titles = json.load(f)

with open(DIR / 'cf_tags_raw.json', encoding='utf-8') as f:
    cf_data = json.load(f)

# Optional: keywords that typically indicate a commentary
# COMM_KEYWORDS = ["疏", "註", "解", "記", "鈔", "贊", "讚", "論", "義", "科", "釋", "演"]

results = []

for source_id, targets in cf_data.items():
    source_title = titles.get(source_id, "")
    if not source_title:
        continue
        
    # Find unique target IDs
    target_ids = set([t['target_id'] for t in targets])
    
    for target_id in target_ids:
        # Avoid self-references or missing titles
        if target_id == source_id:
            continue
            
        target_title = titles.get(target_id, "")
        if not target_title:
            continue
            
        # Check if the target title (sutra) is fundamentally part of the source title (commentary)
        # e.g., target: "人本欲生經", source: "人本欲生經註"
        # We also strip trailing '經' sometimes to match better, but let's start strict
        clean_target = target_title.replace("佛說", "").replace("(第", "").split("(")[0]
        if clean_target in source_title and len(clean_target) >= 2:
            results.append({
                "sutra_id": target_id,
                "sutra_title": target_title,
                "commentary_id": source_id,
                "commentary_title": source_title
            })
        elif target_title in source_title and len(target_title) >= 2:
            results.append({
                "sutra_id": target_id,
                "sutra_title": target_title,
                "commentary_id": source_id,
                "commentary_title": source_title
            })
            
# Sort the results by sutra_id then commentary_id
results.sort(key=lambda x: (x['sutra_id'], x['commentary_id']))

# Deduplicate
unique_results = []
seen = set()
for r in results:
    key = (r['sutra_id'], r['commentary_id'])
    if key not in seen:
        seen.add(key)
        unique_results.append(r)

output_file = DIR / 'cf_sutra_commentary_pairs.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(unique_results, f, ensure_ascii=False, indent=2)

print(f"Found {len(unique_results)} strict sutra-commentary relations based on CF tags + Title matching.")
print(f"Saved to {output_file.name}")
