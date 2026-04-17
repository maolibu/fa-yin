"""
Gaiji（缺字）映射模塊
用於將 CBETA 的 CB 編號（如 CB00178）解析為對應的 Unicode 字符或組字式回退文本。
"""

import json
import os
from pathlib import Path

# 全局緩存，避免重複讀取
_gaiji_map = None


def load_gaiji_map(json_path=None):
    """
    加載 cbeta_gaiji.json 映射表。
    
    參數:
        json_path: JSON 文件路徑，默認從 config.GAIJI_PATH 獲取
    
    返回:
        dict: CB 編號 → 字符信息的映射字典
    """
    global _gaiji_map
    if _gaiji_map is not None:
        return _gaiji_map

    if json_path is None:
        # 從 config 模塊獲取 gaiji 數據路徑
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import config
        json_path = config.GAIJI_PATH

    with open(json_path, "r", encoding="utf-8") as f:
        _gaiji_map = json.load(f)

    return _gaiji_map


def resolve(cb_id, gaiji_map=None):
    """
    將 CB 編號解析為可顯示的字符。
    
    優先級：
    1. uni_char（直接 Unicode 字符，CBETA 精確字形）
    2. norm_uni_char（標準化 Unicode，更通用的字形）
    3. norm_big5_char（Big5 範圍內的替代字符）
    4. composition（組字式，如 [口*爾]）
    5. 原始 CB 編號作為回退
    
    參數:
        cb_id: CBETA 缺字編號，如 'CB00178'（帶或不帶 # 前綴均可）
        gaiji_map: 預加載的映射字典，為 None 則自動加載
    
    返回:
        str: 解析後的字符或回退文本
    """
    # 清理編號（去除 # 前綴）
    cb_id = cb_id.lstrip("#")

    if gaiji_map is None:
        gaiji_map = load_gaiji_map()

    entry = gaiji_map.get(cb_id)
    if entry is None:
        return f"[{cb_id}]"

    # 優先返回精確 Unicode 字符
    if entry.get("uni_char"):
        return entry["uni_char"]

    # 其次返回標準化字符（更通用的字形）
    if entry.get("norm_uni_char"):
        return entry["norm_uni_char"]

    # 再次返回 Big5 範圍內的替代字符
    if entry.get("norm_big5_char"):
        return entry["norm_big5_char"]

    # 其次返回組字式
    if entry.get("composition"):
        return entry["composition"]

    # 最後用 CB 編號標記
    return f"[{cb_id}]"
