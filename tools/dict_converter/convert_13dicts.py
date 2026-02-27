#!/usr/bin/env python3
"""
13Dicts (DILA/DDBC) 词典转换工具
使用 PyGlossary 将 Babylon (.bgl) 和 StarDict 格式的词典转换为统一的 JSON 格式。

用法：
    python convert_13dicts.py
"""

import gzip
import json
import struct
import tempfile
from pathlib import Path

from pyglossary import Glossary


# Configuration
RAW_DIR = Path("/data/fjlsc/01_data_raw/dicts/13Dicts")
OUTPUT_DIR = Path(__file__).resolve().parent / "13dicts"

# Dictionary metadata mapping
DICT_NAMES = {
    "babylon-Abhisamacarika.ddbc": "比丘威儀法詞典",
    "babylon-dingfubao.dila": "丁福保佛學大辭典",
    "babylon-hopkins.ddbc": "Jeffrey Hopkins' Tibetan-Sanskrit-English Dictionary",
    "babylon-kumarajiva.ddbc": "妙法蓮華經詞典",
    "babylon-lokaksema.ddbc": "道行般若經詞典",
    "babylon-pali-chin.ddbc": "Pali-Chinese dictionary",
    "babylon-tibskrit.ddbc": "Tibskrit Philology",
    "dharmaraksa.ddbc": "正法華經詞典",
    "dzdl": "大智度論辭典",
    "ddbc.mahavyutpatti": "Mahāvyutpatti (翻譯名義大集)",
    "ddbc.nanshanlu": "南山律學辭典",
    "ddbc.soothill-hodous": "Soothill-Hodous Dictionary of Chinese Buddhist Terms",
    "stardict-pentaglot.ddbc": "Pentaglot Dictionary of Buddhist Terms",
}

# Initialize PyGlossary
Glossary.init()


def convert_with_pyglossary(input_path: Path) -> list[dict]:
    """Convert dictionary using PyGlossary."""
    entries = []
    
    glos = Glossary()
    
    # Determine format and actual path
    if input_path.suffix == ".bgl":
        input_format = "BabylonBgl"
        actual_path = input_path
    elif input_path.is_dir():
        input_format = "Stardict"
        # StarDict needs the .ifo file path
        ifo_files = list(input_path.glob("*.ifo"))
        if not ifo_files:
            print(f"    No .ifo file found in {input_path}")
            return entries
        actual_path = ifo_files[0]
    else:
        return entries
    
    try:
        # Read the dictionary
        glos.read(str(actual_path), format=input_format)
        
        # Extract entries
        for entry in glos:
            words = entry.l_word  # List of headwords
            defi = entry.defi     # Definition
            
            if words and defi:
                term = words[0] if isinstance(words, list) else words
                entry_data = {
                    "term": term,
                    "definition": defi.strip(),
                }
                # Preserve alternate headwords
                if isinstance(words, list) and len(words) > 1:
                    entry_data["alt_terms"] = words[1:]
                entries.append(entry_data)
        
        glos.clear()
        
    except Exception as e:
        print(f"    PyGlossary error: {e}")
    
    return entries


def convert_dictionary(item: Path) -> dict | None:
    """Convert a single dictionary (file or directory)."""
    
    if item.is_dir():
        dict_id = item.name
        # For stardict dirs, use the internal name
        ifo_files = list(item.glob("*.ifo"))
        if ifo_files:
            actual_id = ifo_files[0].stem
            dict_name = DICT_NAMES.get(actual_id, DICT_NAMES.get(dict_id, dict_id))
        else:
            dict_name = DICT_NAMES.get(dict_id, dict_id)
    else:
        dict_id = item.stem
        dict_name = DICT_NAMES.get(dict_id, dict_id)
    
    print(f"  Using PyGlossary to parse...")
    entries = convert_with_pyglossary(item)
    
    if not entries:
        return None
    
    return {
        "meta": {
            "id": dict_id,
            "name": dict_name,
            "source": "13Dicts (DILA/DDBC)",
            "entry_count": len(entries),
        },
        "entries": entries,
    }


def main():
    """Convert all 13 dictionaries to JSON."""
    print("=" * 60)
    print("13Dicts (DILA/DDBC) Converter")
    print("=" * 60)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find all dictionary items (files and directories)
    items = []
    for item in RAW_DIR.iterdir():
        if item.is_dir() and item.name.startswith("stardict"):
            items.append(item)
        elif item.suffix == ".bgl":
            items.append(item)
    
    items = sorted(items, key=lambda x: x.name)
    
    print(f"\nFound {len(items)} dictionaries to convert.\n")
    
    total_entries = 0
    successful = 0
    
    for item in items:
        print(f"Converting {item.name}...")
        
        try:
            result = convert_dictionary(item)
            
            if result and result["entries"]:
                output_name = item.stem if item.is_file() else item.name
                output_file = OUTPUT_DIR / f"{output_name}.json"
                
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
    print(f"Conversion complete: {successful}/{len(items)} dictionaries")
    print(f"Total entries: {total_entries:,}")
    print(f"Output directory: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
