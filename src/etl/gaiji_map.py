"""
Gaiji（缺字）映射模块
用于将 CBETA 的 CB 编号（如 CB00178）解析为对应的 Unicode 字符或组字式回退文本。
"""

import json
import os
from pathlib import Path

# 全局缓存，避免重复读取
_gaiji_map = None


def load_gaiji_map(json_path=None):
    """
    加载 cbeta_gaiji.json 映射表。
    
    参数:
        json_path: JSON 文件路径，默认从 config.GAIJI_PATH 获取
    
    返回:
        dict: CB 编号 → 字符信息的映射字典
    """
    global _gaiji_map
    if _gaiji_map is not None:
        return _gaiji_map

    if json_path is None:
        # 从 config 模块获取 gaiji 数据路径
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import config
        json_path = config.GAIJI_PATH

    with open(json_path, "r", encoding="utf-8") as f:
        _gaiji_map = json.load(f)

    return _gaiji_map


def resolve(cb_id, gaiji_map=None):
    """
    将 CB 编号解析为可显示的字符。
    
    优先级：
    1. uni_char（直接 Unicode 字符，CBETA 精确字形）
    2. norm_uni_char（标准化 Unicode，更通用的字形）
    3. norm_big5_char（Big5 范围内的替代字符）
    4. composition（组字式，如 [口*爾]）
    5. 原始 CB 编号作为回退
    
    参数:
        cb_id: CBETA 缺字编号，如 'CB00178'（带或不带 # 前缀均可）
        gaiji_map: 预加载的映射字典，为 None 则自动加载
    
    返回:
        str: 解析后的字符或回退文本
    """
    # 清理编号（去除 # 前缀）
    cb_id = cb_id.lstrip("#")

    if gaiji_map is None:
        gaiji_map = load_gaiji_map()

    entry = gaiji_map.get(cb_id)
    if entry is None:
        return f"[{cb_id}]"

    # 优先返回精确 Unicode 字符
    if entry.get("uni_char"):
        return entry["uni_char"]

    # 其次返回标准化字符（更通用的字形）
    if entry.get("norm_uni_char"):
        return entry["norm_uni_char"]

    # 再次返回 Big5 范围内的替代字符
    if entry.get("norm_big5_char"):
        return entry["norm_big5_char"]

    # 其次返回组字式
    if entry.get("composition"):
        return entry["composition"]

    # 最后用 CB 编号标记
    return f"[{cb_id}]"
