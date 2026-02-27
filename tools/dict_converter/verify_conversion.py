#!/usr/bin/env python3
"""
词典转换质量验证工具

检查项：
1. 词条数量对比（与原始元数据对比）。
2. 样本内容校验。
3. 空值或损坏词条检测。
4. 编码问题检测（如出现  字符）。
5. 核心词汇抽样检查。
"""

import json
import struct
from pathlib import Path
from collections import Counter


# Directories
OUTPUT_13 = Path(__file__).resolve().parent / "13dicts"
OUTPUT_28 = Path(__file__).resolve().parent / "28dicts"
RAW_28 = Path("/data/fjlsc/01_data_raw/dicts/fodict2_public-win32-j28/repo")

# Known terms that MUST exist (spot check)
# 13Dicts are mainly Traditional Chinese, 28Dicts are Simplified Chinese.
MUST_HAVE_TERMS_28 = [
    "阿赖耶识",  # Fundamental Buddhist concept
    "涅槃",      # Nirvana
    "般若",      # Prajna
    "菩萨",      # Bodhisattva
    "如来",      # Tathagata
]

MUST_HAVE_TERMS_13 = [
    "阿賴耶識",
    "涅槃",
    "般若",
    "菩薩",
    "如來",
]


def get_expected_count_28(dict_dir: Path) -> int:
    """Get expected entry count from fodict2 binary header.
    
    The first 4 bytes (big-endian uint32) represent the total index slots
    (including ROOT). Actual leaf entries = total_slots - 1 - parent_nodes.
    We return total_slots - 1 as an upper bound estimate.
    """
    bin_file = dict_dir / "fodict.bin"
    if not bin_file.exists():
        return -1
    
    with open(bin_file, "rb") as f:
        header = f.read(4)
    
    if len(header) >= 4:
        total_slots = struct.unpack(">I", header[0:4])[0]
        return total_slots - 1  # Subtract ROOT
    return -1


def verify_json_file(json_path: Path, must_terms: list[str] | None = None) -> dict:
    """Verify a single JSON dictionary file."""
    issues = []
    stats = {}
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "issues": [], "stats": {}}
    
    entries = data.get("entries", [])
    meta = data.get("meta", {})
    
    stats["entry_count"] = len(entries)
    stats["meta_count"] = meta.get("entry_count", 0)
    stats["name"] = meta.get("name", "Unknown")
    
    # Check 1: Entry count matches metadata
    if stats["entry_count"] != stats["meta_count"]:
        issues.append(f"Count mismatch: file has {stats['entry_count']}, meta says {stats['meta_count']}")
    
    # Check 2: Empty entries
    empty_terms = sum(1 for e in entries if not e.get("term", "").strip())
    empty_defs = sum(1 for e in entries if not e.get("definition", "").strip())
    
    if empty_terms > 0:
        issues.append(f"{empty_terms} entries with empty terms")
    if empty_defs > 0:
        issues.append(f"{empty_defs} entries with empty definitions")
    
    stats["empty_terms"] = empty_terms
    stats["empty_defs"] = empty_defs
    
    # Check 3: Suspiciously short definitions
    short_defs = sum(1 for e in entries if 0 < len(e.get("definition", "")) < 5)
    if short_defs > len(entries) * 0.1:  # More than 10% very short
        issues.append(f"{short_defs} entries with very short definitions (<5 chars)")
    
    stats["short_defs"] = short_defs
    
    # Check 4: Encoding issues (replacement character)
    encoding_issues = sum(1 for e in entries if "�" in e.get("term", "") + e.get("definition", ""))
    if encoding_issues > 0:
        issues.append(f"{encoding_issues} entries with encoding issues (replacement chars)")
    
    stats["encoding_issues"] = encoding_issues
    
    # Check 5: Definition length statistics
    def_lengths = [len(e.get("definition", "")) for e in entries]
    if def_lengths:
        stats["avg_def_length"] = sum(def_lengths) / len(def_lengths)
        stats["max_def_length"] = max(def_lengths)
        stats["min_def_length"] = min(def_lengths) if min(def_lengths) > 0 else "N/A (has empty)"
    
    # Check 6: Spot check for known terms (optional)
    if must_terms is not None:
        all_terms = {e.get("term", "") for e in entries}
        found_terms = [t for t in must_terms if t in all_terms]
        stats["known_terms_found"] = len(found_terms)
    
    return {"issues": issues, "stats": stats}


def verify_28dicts():
    """Verify all 28Dicts conversions."""
    print("\n" + "=" * 60)
    print("Verifying 28Dicts (fodict2)")
    print("=" * 60)
    
    json_files = sorted(OUTPUT_28.glob("*.json"))
    
    total_entries = 0
    total_issues = 0
    all_terms = set()
    
    for json_file in json_files:
        result = verify_json_file(json_file, must_terms=MUST_HAVE_TERMS_28)
        stats = result["stats"]
        issues = result["issues"]
        
        # Get expected count from source
        dict_id = json_file.stem
        source_dir = RAW_28 / dict_id
        expected = get_expected_count_28(source_dir)
        
        # Compare with expected
        actual = stats.get("entry_count", 0)
        total_entries += actual
        
        status = "✓" if not issues else "⚠"
        print(f"\n{status} {json_file.name}")
        print(f"   Entries: {actual:,}", end="")
        if expected > 0:
            diff = actual - expected
            if abs(diff) > 1:
                print(f" (expected ~{expected:,}, diff: {diff:+d})", end="")
                if diff < -10:
                    issues.append(f"Missing significant entries: expected ~{expected}, got {actual}")
        print()
        
        # Collect all terms for cross-file check
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            all_terms.update(e.get("term", "") for e in data.get("entries", []))
        
        if issues:
            total_issues += len(issues)
            for issue in issues:
                print(f"   ⚠ {issue}")
    
    # Check known terms across all dictionaries (Simplified)
    print(f"\n--- Spot Check: Known Terms (Simplified) ---")
    for term in MUST_HAVE_TERMS_28:
        found = "✓" if term in all_terms else "✗"
        print(f"   {found} {term}")
    
    print(f"\n--- Summary ---")
    print(f"   Total dictionaries: {len(json_files)}")
    print(f"   Total entries: {total_entries:,}")
    print(f"   Total issues: {total_issues}")


def verify_13dicts():
    """Verify all 13Dicts conversions."""
    print("\n" + "=" * 60)
    print("Verifying 13Dicts (DILA/DDBC)")
    print("=" * 60)
    
    json_files = sorted(OUTPUT_13.glob("*.json"))
    
    total_entries = 0
    total_issues = 0
    all_terms = set()
    
    for json_file in json_files:
        result = verify_json_file(json_file, must_terms=MUST_HAVE_TERMS_13)
        stats = result["stats"]
        issues = result["issues"]
        
        actual = stats.get("entry_count", 0)
        total_entries += actual
        
        status = "✓" if not issues else "⚠"
        print(f"\n{status} {json_file.name}")
        print(f"   Name: {stats.get('name', 'Unknown')}")
        print(f"   Entries: {actual:,}")
        print(f"   Avg definition length: {stats.get('avg_def_length', 0):.0f} chars")
        
        # Collect all terms
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            all_terms.update(e.get("term", "") for e in data.get("entries", []))
        
        if issues:
            total_issues += len(issues)
            for issue in issues:
                print(f"   ⚠ {issue}")
    
    # Check known terms (Traditional)
    print(f"\n--- Spot Check: Known Terms (Traditional) ---")
    for term in MUST_HAVE_TERMS_13:
        found = "✓" if term in all_terms else "✗"
        print(f"   {found} {term}")
    
    print(f"\n--- Summary ---")
    print(f"   Total dictionaries: {len(json_files)}")
    print(f"   Total entries: {total_entries:,}")
    print(f"   Total issues: {total_issues}")


def sample_comparison():
    """Show sample entries for manual spot-check."""
    print("\n" + "=" * 60)
    print("Sample Entries (for manual verification)")
    print("=" * 60)
    
    # Pick a few dictionaries to sample
    samples = [
        (OUTPUT_28 / "001.dfb-j.json", "丁福保 (28Dicts)"),
        (OUTPUT_13 / "babylon-dingfubao.dila.json", "丁福保 (13Dicts)"),
    ]
    
    for json_path, label in samples:
        if not json_path.exists():
            continue
        
        print(f"\n--- {label} ---")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        entries = data.get("entries", [])
        
        # Show first, middle, and last entry
        if entries:
            indices = [0, len(entries) // 2, -1]
            for idx in indices:
                e = entries[idx]
                term = e.get("term", "")
                defi = e.get("definition", "")[:100]
                print(f"   [{idx if idx >= 0 else len(entries)+idx}] {term}: {defi}...")


def main():
    print("=" * 60)
    print("Dictionary Conversion Verification")
    print("=" * 60)
    
    verify_28dicts()
    verify_13dicts()
    sample_comparison()
    
    print("\n" + "=" * 60)
    print("Verification Complete")
    print("=" * 60)
    print("\nRecommendation: If issues are minor (encoding, a few missing entries),")
    print("the conversion is acceptable. For critical entries, spot-check in the")
    print("original application if needed.")


if __name__ == "__main__":
    main()
