#!/usr/bin/env python3
"""
28Dicts (fodict2) 词典转换工具
解析 fodict.bin 二进制格式并提取词条内容。

核心逻辑：
1. 解析 128 字节的定长索引记录。
2. 根据偏移量提取 UTF-8 编码的词条定义。
3. 跳过仅包含子节点 ID 的目录节点（Parent Nodes）。

用法：
    python convert_28dicts.py
"""

import json
import re
import struct
from pathlib import Path


# Configuration
RAW_DIR = Path("/data/fjlsc/01_data_raw/dicts/fodict2_public-win32-j28/repo")
OUTPUT_DIR = Path(__file__).resolve().parent / "28dicts"

# Dictionary metadata (ID -> Chinese name)
DICT_NAMES = {
    "001.dfb-j": "佛学大辞典(丁福保 编)",
    "002.cyx-j": "佛学常见辞汇(陈义孝 编)",
    "003.zgfj-j": "中国佛教(中国佛教协会编)",
    "004.szfs-j": "三藏法数(明·一如等 撰)",
    "005.fymyj-j": "翻译名义集(南宋·法云 著)",
    "006.fxcdtb-j": "佛学次第统编(杨卓 编)",
    "007.ce-ec-ee-j": "英汉-汉英-英英佛学词汇(中华佛典宝库 编)",
    "008.theravada-j": "巴英南传佛教辞典(Nyanaponika 编)",
    "009.faxiang-j": "法相辞典(朱芾煌编)",
    "010.bkqszl-j": "中国大百科全书(摘录)",
    "011.fjrwz-j": "佛教人物传 V2.1(中华佛典宝库 编)",
    "012.weishi-j": "唯识名词白话新解(于凌波居士著)",
    "013.fajie-j": "法界次第初门(隋·智者大师 撰)",
    "014.famen-j": "法门名义集(唐·李师政 撰)",
    "015.syfy-j": "俗语佛源(中国佛教文化研究所编)",
    "016.tiantai-j": "天台教学辞典(释慧岳监修，释会旻主编)",
    "017.apdm-j": "阿毗达磨辞典(中华佛典宝库 编)",
    "018.chanzongyulu-j": "禅宗语录辞典 V1.3 (中华佛典宝库编)",
    "019.fjqiwu-j": "佛教器物简述(中华佛典宝库编)",
    "020.ztsy-j": "祖庭事苑(北宋·陈善卿 编)",
    "021.yzzj-j": "阅藏知津(蕅益大师著)",
    "022.ssyl-j": "释氏要览(北宋·释道诚集)",
    "023.zcfj-j": "藏传佛教辞典(中华佛典宝库编)",
    "024.chanlinxqj-j": "禅林象器笺(日·无著道忠撰)",
    "025.nanshanlv-j": "南山律学辞典",
    "026.fymydj-j": "翻译名言大集",
    "027.wyhbjy-j": "五译合璧集要",
    "028.fhchb-j": "梵汉词汇表",
}

RECORD_SIZE = 128
MAX_TERM_LEN = 108  # 128 - 20 bytes header = 108 bytes max for term


def parse_all_records(data: bytes) -> dict[int, dict]:
    """Parse all index records from the binary data into a dictionary.

    Uses the header value (first 4 bytes) to determine the index area size,
    then iterates through all record slots, skipping invalid ones.
    """
    records = {}
    file_size = len(data)

    # Header first 4 bytes = total index slots (including ROOT)
    total_slots = struct.unpack(">I", data[0:4])[0]
    index_end = total_slots * RECORD_SIZE
    skipped = 0

    for i in range(1, total_slots):  # Skip ROOT at slot 0
        offset = i * RECORD_SIZE
        if offset + RECORD_SIZE > file_size or offset + RECORD_SIZE > index_end:
            break

        record = data[offset:offset + RECORD_SIZE]

        # Skip empty slots (all zeros)
        if all(b == 0 for b in record):
            continue

        try:
            _, entry_id, parent_id, content_offset, term_len = struct.unpack(">IIIII", record[:20])
        except struct.error:
            skipped += 1
            continue

        # Validate fields — skip (not break) on invalid records
        if content_offset == 0 or content_offset >= file_size:
            skipped += 1
            continue

        if term_len == 0 or term_len > MAX_TERM_LEN:
            skipped += 1
            continue

        # Extract term
        term_bytes = record[20:20 + term_len]
        try:
            term = term_bytes.decode("utf-8").rstrip("\x00")
        except UnicodeDecodeError:
            skipped += 1
            continue

        if not term:
            skipped += 1
            continue

        records[entry_id] = {
            "parent": parent_id,
            "term": term,
            "content_offset": content_offset,
        }

    if skipped > 0:
        print(f"    Skipped {skipped} invalid record slots")

    return records


def extract_content(data: bytes, content_offset: int, is_parent: bool) -> str | None:
    """
    Extract content at the given offset.
    Returns None for parent nodes (whose content is a child ID list).
    """
    if content_offset + 4 > len(data):
        return None

    content_len = struct.unpack(">I", data[content_offset:content_offset + 4])[0]

    if content_len == 0:
        return None

    # Parent nodes store child ID lists, not text
    if is_parent:
        return None

    content_start = content_offset + 4
    content_end = min(content_start + content_len, len(data))

    content_bytes = data[content_start:content_end]

    try:
        content = content_bytes.decode("utf-8", errors="replace")
    except Exception:
        return None

    return content.strip()


def convert_dictionary(dict_dir: Path) -> dict | None:
    """Convert a single fodict2 dictionary to JSON structure."""
    dict_id = dict_dir.name
    dict_name = DICT_NAMES.get(dict_id, dict_id)
    
    bin_file = dict_dir / "fodict.bin"
    if not bin_file.exists():
        print(f"  Warning: {bin_file} not found")
        return None
    
    file_size = bin_file.stat().st_size
    print(f"  Reading {bin_file.name} ({file_size / 1024:.1f} KB)...")
    
    with open(bin_file, "rb") as f:
        data = f.read()
    
    # Parse all index records
    records = parse_all_records(data)
    print(f"    Parsed {len(records)} index records")

    if not records:
        return None

    # Identify parent nodes: entries whose IDs appear as another entry's parent_id
    parent_entry_ids = set()
    for info in records.values():
        pid = info["parent"]
        if pid != 0 and pid in records:
            parent_entry_ids.add(pid)

    # Extract content for each entry, skipping parent nodes
    entries = []
    skipped_parents = 0

    for entry_id, info in records.items():
        is_parent = entry_id in parent_entry_ids
        content = extract_content(data, info["content_offset"], is_parent)

        if content is None:
            if is_parent:
                skipped_parents += 1
            continue

        if not content:
            continue
        
        # Extract see_also references
        see_also = []
        if "<SEEALSO>" in content:
            see_also = re.findall(r"<SEEALSO>(.*?)</SEEALSO>", content)
            content = re.sub(r"<SEEALSO>.*?</SEEALSO>", "", content).strip()
        if not content and see_also:
            content = "参见：" + "；".join(see_also)
        if not content:
            continue
        
        entry = {
            "term": info["term"],
            "definition": content,
        }
        if see_also:
            entry["see_also"] = see_also
        
        entries.append(entry)
    
    print(f"    Extracted {len(entries)} entries (skipped {skipped_parents} parent nodes)")
    
    if not entries:
        return None
    
    return {
        "meta": {
            "id": dict_id,
            "name": dict_name,
            "source": "28Dicts (fodict2)",
            "entry_count": len(entries),
        },
        "entries": entries,
    }


def main():
    """Convert all 28 dictionaries to JSON."""
    print("=" * 60)
    print("28Dicts (fodict2) Converter")
    print("=" * 60)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find all dictionary directories
    dict_dirs = sorted([d for d in RAW_DIR.iterdir() if d.is_dir() and d.name[0].isdigit()])
    
    print(f"\nFound {len(dict_dirs)} dictionaries to convert.\n")
    
    total_entries = 0
    successful = 0
    
    for dict_dir in dict_dirs:
        print(f"Converting {dict_dir.name}...")
        
        try:
            result = convert_dictionary(dict_dir)
            
            if result and result["entries"]:
                output_file = OUTPUT_DIR / f"{dict_dir.name}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                entry_count = result["meta"]["entry_count"]
                total_entries += entry_count
                successful += 1
                print(f"  ✓ Saved {entry_count} entries to {output_file.name}")
            else:
                print(f"  ✗ No entries extracted")
        except Exception as e:
            import traceback
            print(f"  ✗ Error: {e}")
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"Conversion complete: {successful}/{len(dict_dirs)} dictionaries")
    print(f"Total entries: {total_entries:,}")
    print(f"Output directory: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
