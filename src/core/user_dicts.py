"""
用户词典适配器

支持用户自行放置的词典文件，自动扫描 data/dicts/user/ 目录。
支持格式: MDX, JSON, CSV

用法:
    from core.user_dicts import UserDictManager
    mgr = UserDictManager(Path("data/dicts/user"))
    results = mgr.lookup("般若")
"""

import csv
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── MDX 读取器 ──────────────────────────────────────────────────

class MdxDictionary:
    """MDict (.mdx) 词典读取器"""

    def __init__(self, mdx_path: Path):
        from mdict_utils import reader as mdict_reader
        self.path = mdx_path
        self.name = mdx_path.stem  # 文件名作为词典名
        self.dict_id = f"user.mdx.{self.name}"
        self._index: dict[str, list[str]] = {}  # term → [definition, ...]
        self._loaded = False
        self._entry_count = 0

    def _ensure_loaded(self):
        """延迟加载：首次查询时才构建索引"""
        if self._loaded:
            return
        start = time.time()
        try:
            from mdict_utils import reader as mdict_reader
            md = mdict_reader.MDX(str(self.path))
            items = md.items()
            for key_bytes, val_bytes in items:
                try:
                    key = key_bytes.decode("utf-8") if isinstance(key_bytes, bytes) else str(key_bytes)
                    val = val_bytes.decode("utf-8") if isinstance(val_bytes, bytes) else str(val_bytes)
                except (UnicodeDecodeError, AttributeError):
                    continue

                key = key.strip()
                if not key:
                    continue

                if key not in self._index:
                    self._index[key] = []
                self._index[key].append(val)

            self._entry_count = len(self._index)
            elapsed = time.time() - start
            log.info(f"  MDX 加载完成: {self.name} ({self._entry_count} 词条, {elapsed:.1f}秒)")
        except Exception as e:
            log.error(f"  MDX 加载失败: {self.path}: {e}")
        self._loaded = True

    def lookup(self, term: str) -> list[dict]:
        """查询词条，返回结果列表"""
        self._ensure_loaded()
        results = []
        definitions = self._index.get(term, [])
        for defn in definitions:
            results.append({
                "dict_id": self.dict_id,
                "dict_name": self.name,
                "char_type": "用户词典",
                "term": term,
                "definition": defn,
            })
        return results

    @property
    def info(self) -> dict:
        """词典信息"""
        self._ensure_loaded()
        return {
            "dict_id": self.dict_id,
            "name": self.name,
            "source": f"用户词典 (MDX): {self.path.name}",
            "entry_count": self._entry_count,
            "char_type": "用户词典",
        }


# ── JSON 读取器 ──────────────────────────────────────────────────

class JsonDictionary:
    """
    JSON 词典读取器

    支持多种格式:
    1. 对象格式: {"般若": "智慧", "涅槃": "寂灭"}
    2. 数组格式: [{"term": "般若", "definition": "智慧"}, ...]
    3. 萌典格式: [{"title": "般若", "heteronyms": [{"bopomofo": "...", "definitions": [{"def": "..."}]}]}, ...]
    4. 其他常见格式: word/headword/key + meaning/def/explanation 等字段名
    """

    # 常见的"词条"字段名
    TERM_FIELDS = ("term", "词条", "word", "headword", "key", "title", "entry")
    # 常见的"释义"字段名
    DEFN_FIELDS = ("definition", "释义", "解释", "meaning", "def", "explanation", "value", "content")

    def __init__(self, json_path: Path):
        self.path = json_path
        self.name = json_path.stem
        self.dict_id = f"user.json.{self.name}"
        self._index: dict[str, list[str]] = {}
        self._loaded = False
        self._entry_count = 0

    @staticmethod
    def _find_field(item: dict, candidates: tuple) -> str:
        """在字典中查找第一个匹配的字段名，返回其值"""
        for field in candidates:
            if field in item:
                return str(item[field]).strip()
        return ""

    @staticmethod
    def _flatten_moedict(item: dict) -> list[str]:
        """
        展平萌典格式的嵌套结构，提取所有读音+释义。
        返回格式: ["【ㄅㄛ ㄖㄜˇ】bō rě\n❶ 智慧...\n❷ ...", ...]
        """
        results = []
        heteronyms = item.get("heteronyms", [])
        if not isinstance(heteronyms, list):
            return results

        for het in heteronyms:
            if not isinstance(het, dict):
                continue
            parts = []
            # 提取读音（注音 + 拼音同时显示）
            bopomofo = het.get("bopomofo", "")
            pinyin = het.get("pinyin", "")
            reading_parts = []
            if bopomofo:
                reading_parts.append(bopomofo)
            if pinyin:
                reading_parts.append(pinyin)
            if reading_parts:
                parts.append("【" + " / ".join(reading_parts) + "】")

            # 提取释义
            definitions = het.get("definitions", [])
            if isinstance(definitions, list):
                circled = "❶❷❸❹❺❻❼❽❾❿"
                for i, d in enumerate(definitions):
                    if isinstance(d, dict):
                        defn = d.get("def", "")
                        if defn:
                            prefix = circled[i] if i < len(circled) else f"({i+1})"
                            entry = f"{prefix} {defn}"
                            # 附加引用出处
                            quote = d.get("quote", [])
                            if isinstance(quote, list):
                                for q in quote:
                                    entry += f"\n　　📖 {q}"
                            elif isinstance(quote, str) and quote:
                                entry += f"\n　　📖 {quote}"
                            # 附加例句
                            example = d.get("example", [])
                            if isinstance(example, list):
                                for ex in example:
                                    entry += f"\n　　例：{ex}"
                            elif isinstance(example, str) and example:
                                entry += f"\n　　例：{example}"
                            parts.append(entry)

            if parts:
                results.append("\n".join(parts))
        return results

    def _ensure_loaded(self):
        if self._loaded:
            return
        start = time.time()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))

            if isinstance(data, dict):
                # 对象格式: {"term": "definition"}
                for k, v in data.items():
                    k = str(k).strip()
                    if k:
                        if isinstance(v, str):
                            self._index[k] = [v]
                        elif isinstance(v, list):
                            self._index[k] = [str(item) for item in v]
                        else:
                            self._index[k] = [str(v)]

            elif isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue

                    # 提取词条名
                    term = self._find_field(item, self.TERM_FIELDS)
                    if not term:
                        continue

                    # 策略1: 萌典嵌套格式 (heteronyms)
                    if "heteronyms" in item:
                        defns = self._flatten_moedict(item)
                        if defns:
                            if term not in self._index:
                                self._index[term] = []
                            self._index[term].extend(defns)
                            continue

                    # 策略2: 简单字段格式
                    defn = self._find_field(item, self.DEFN_FIELDS)
                    if defn:
                        if term not in self._index:
                            self._index[term] = []
                        self._index[term].append(defn)

            self._entry_count = len(self._index)
            elapsed = time.time() - start
            log.info(f"  JSON 加载完成: {self.name} ({self._entry_count} 词条, {elapsed:.1f}秒)")
        except Exception as e:
            log.error(f"  JSON 加载失败: {self.path}: {e}")
        self._loaded = True

    def lookup(self, term: str) -> list[dict]:
        self._ensure_loaded()
        results = []
        definitions = self._index.get(term, [])
        for defn in definitions:
            results.append({
                "dict_id": self.dict_id,
                "dict_name": self.name,
                "char_type": "用户词典",
                "term": term,
                "definition": defn,
            })
        return results

    @property
    def info(self) -> dict:
        self._ensure_loaded()
        return {
            "dict_id": self.dict_id,
            "name": self.name,
            "source": f"用户词典 (JSON): {self.path.name}",
            "entry_count": self._entry_count,
            "char_type": "用户词典",
        }


# ── CSV 读取器 ──────────────────────────────────────────────────

class CsvDictionary:
    """
    CSV 词典读取器

    要求第一行为表头，必须包含 term/词条 和 definition/释义 列。
    示例:
        term,definition
        般若,智慧
    """

    def __init__(self, csv_path: Path):
        self.path = csv_path
        self.name = csv_path.stem
        self.dict_id = f"user.csv.{self.name}"
        self._index: dict[str, list[str]] = {}
        self._loaded = False
        self._entry_count = 0

    def _ensure_loaded(self):
        if self._loaded:
            return
        start = time.time()
        try:
            with open(self.path, encoding="utf-8", newline="") as f:
                reader_obj = csv.DictReader(f)
                if not reader_obj.fieldnames:
                    log.warning(f"  CSV 无表头: {self.path}")
                    self._loaded = True
                    return

                # 自动识别列名
                fields = reader_obj.fieldnames
                term_col = None
                defn_col = None
                for col in fields:
                    cl = col.lower().strip()
                    if cl in ("term", "词条", "word", "headword", "key"):
                        term_col = col
                    elif cl in ("definition", "释义", "解释", "meaning", "value", "def"):
                        defn_col = col

                if not term_col or not defn_col:
                    log.warning(f"  CSV 缺少 term/definition 列: {self.path} (列: {fields})")
                    self._loaded = True
                    return

                for row in reader_obj:
                    term = (row.get(term_col) or "").strip()
                    defn = (row.get(defn_col) or "").strip()
                    if term:
                        if term not in self._index:
                            self._index[term] = []
                        self._index[term].append(defn)

            self._entry_count = len(self._index)
            elapsed = time.time() - start
            log.info(f"  CSV 加载完成: {self.name} ({self._entry_count} 词条, {elapsed:.1f}秒)")
        except Exception as e:
            log.error(f"  CSV 加载失败: {self.path}: {e}")
        self._loaded = True

    def lookup(self, term: str) -> list[dict]:
        self._ensure_loaded()
        results = []
        definitions = self._index.get(term, [])
        for defn in definitions:
            results.append({
                "dict_id": self.dict_id,
                "dict_name": self.name,
                "char_type": "用户词典",
                "term": term,
                "definition": defn,
            })
        return results

    @property
    def info(self) -> dict:
        self._ensure_loaded()
        return {
            "dict_id": self.dict_id,
            "name": self.name,
            "source": f"用户词典 (CSV): {self.path.name}",
            "entry_count": self._entry_count,
            "char_type": "用户词典",
        }


# ── 词典管理器 ──────────────────────────────────────────────────

# 格式注册表
FORMAT_MAP = {
    ".mdx": MdxDictionary,
    ".json": JsonDictionary,
    ".csv": CsvDictionary,
}


class UserDictManager:
    """
    用户词典管理器

    扫描指定目录下的词典文件，提供统一查询接口。
    词典采用延迟加载策略：扫描时只记录文件路径，首次查询时才真正加载数据。
    """

    def __init__(self, user_dict_dir: Path):
        self.dir = user_dict_dir
        self.dicts: list = []
        self._scan()

    def _scan(self):
        """扫描目录中的词典文件"""
        if not self.dir.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            # 创建 README 说明文件
            readme = self.dir / "README.txt"
            if not readme.exists():
                readme.write_text(
                    "将词典文件放入此目录，重启服务器后自动加载。\n"
                    "\n"
                    "支持格式:\n"
                    "  .mdx  — MDict 格式（最常见，古汉语词典等）\n"
                    "  .json — JSON 格式（对象或数组）\n"
                    "  .csv  — CSV 格式（需含 term 和 definition 列）\n"
                    "\n"
                    "示例文件名:\n"
                    "  古汉语词典.mdx\n"
                    "  汉语大词典.mdx\n"
                    "  自制术语表.csv\n",
                    encoding="utf-8",
                )
            log.info(f"  用户词典目录已创建: {self.dir}")
            return

        count = 0
        for path in sorted(self.dir.iterdir()):
            ext = path.suffix.lower()
            if ext in FORMAT_MAP and path.is_file():
                dict_class = FORMAT_MAP[ext]
                d = dict_class(path)
                self.dicts.append(d)
                count += 1
                log.info(f"  发现用户词典: {path.name} ({ext})")

        if count:
            log.info(f"  用户词典共 {count} 部（延迟加载，首次查询时读取）")
        else:
            log.info(f"  用户词典目录为空: {self.dir}")

    def lookup(self, term: str) -> list[dict]:
        """在所有用户词典中查询"""
        results = []
        for d in self.dicts:
            results.extend(d.lookup(term))
        return results

    def list_dicts(self) -> list[dict]:
        """列出所有用户词典信息"""
        return [d.info for d in self.dicts]

    def reload(self):
        """重新扫描目录（热重载）"""
        self.dicts.clear()
        self._scan()
