# 经文-疏钞映射工具

从 CBETA 部类目录自动提取经文与注疏的对应关系。

## 算法概述

### 第一步：部类目录解析 (`extract_v10.py`)

从 `bulei_catalog_slim.md`（CBETA 部类目录精简版）提取经疏对。

**栈式树解析**：逐行扫描，利用缩进深度自动管理层级关系：

```
📖 般若心經 ／ 疏                 ← 压栈新组
  **T0250-57 般若心經 T08**       ← 粗体标题 → 维护缩进层级
    `T0250` 摩訶般若波羅蜜大明呪經   ← 由 classify_item 判断归类
  **T1710-14 般若心經疏 T33**      ← 粗体标题
    `T1710` 般若波羅蜜多心經幽贊    ← 由 classify_item 判断归类
```

核心规则：
- 遇到 `📖` 行 → 压栈一个新的经疏组
- 遇到 `**粗体**` 行 → 仅维护缩进层级（不影响分类决策）
- 遇到 `` `ID` `` 条目 → 严格由 `classify_item` 按标题特征判断归类（经/疏/忽略）
- 缩进回退 → 自动弹出栈顶组，避免子组条目泄漏到父组

**注疏判断**：长关键词全文匹配 + 短关键词（疏/鈔/記/解/釋）末尾匹配，排除礼忏/仪轨/异译本等。

**经疏匹配**：
- 多种匹配策略取 max 分（全称匹配、核心名匹配、逐字截断），避免 if-elif 短路导致的优先级错误
- 评分为 0 时直接放弃，杜绝"大锅饭"式的盲目广播

**疏之疏链条**（V10 新增）：
- 同组注疏之间做全称匹配：若注疏 A 的全称出现在注疏 B 的标题中，且 B 更长，则产生 A→B 对应关系
- 带前缀容错：`佛說盂蘭盆經疏` 可匹配 `盂蘭盆經疏孝衡鈔`
- 过滤同名异版互指和已知误配

### 第二步：合并 XML cf 标签 (`merge_final.py`)

4. 结合 V10 提取结果与过滤后的 CF 标签进行最终组合去重。

## 数据来源

| 方法 | 标记 | 说明 |
|------|------|------|
| 部类目录 | `bulei_catalog` | 从 `bulei_catalog_slim.md` 的 📖 分组解析 (由 extract_v10.py 产出) |
| XML cf 标签 | `xml_cf_tag` | CBETA 官方标注，补充基于名称校验过的跨组关系 (由 filter_cf_pairs.py 产出) |

## 文件说明

### 输出文件

| 文件 | 说明 |
|------|------|
| `cbeta_sutra_commentary_map.json` | 本目录的合并映射文件（全量最终版） |
| `sutra_commentary_pairs.csv` | V10 中间结果（仅部类目录来源，UTF-8-BOM） |
| `cf_sutra_commentary_pairs.json` | CF 标签精准过滤中间结果 |
| `../../data/db/commentary_map.default.json` | **项目实际使用的文件**，部署时复制 |

### 处理脚本

| 文件 | 说明 |
|------|------|
| `extract_v10.py` | 核心提取：从部类目录提取经疏对 → CSV |
| `filter_cf_pairs.py` | CF 标签过滤：根据标题匹配度精准提取 XML cf_tag 里的经疏关联 |
| `merge_final.py` | 最终合并：合并 CSV + 过滤后的 CF JSON → 最终全量 JSON |
| `export_bulei_md.py` | 工具：从 `bulei_nav.xhtml` 导出完整目录 |
| `export_bulei_slim.py` | 工具：导出精简版目录（仅含 📖 组） |

### 数据文件

| 文件 | 说明 |
|------|------|
| `bulei_catalog.md` | CBETA 部类目录完整版（250K） |
| `bulei_catalog_slim.md` | 精简版（仅保留含 📖 的经疏分组） |
| `work_title_cache.json` | work_id → 标题 缓存 |

## 使用方法

```bash
cd 60_ready/tools/sutra_commentary_map

# 第一步：提取（V10）
~/miniforge3/envs/fjlsc/bin/python extract_v10.py

# 第二步：合并生成最终 JSON
~/miniforge3/envs/fjlsc/bin/python merge_final.py
```

## 当前结果（V10）

- 部类目录提取：原经/论 **194** 部，注疏 **489** 部，映射 **1007** 对
  - 其中约 **210** 对为疏之疏关系（如 法華玄義 → 法華玄義釋籤）

### V8 → V10 修复记录

| 版本 | 修复内容 |
|------|----------|
| V9 | 修复"大锅饭"漏洞（score=0 时不再广播给全组）|
| V9 | 修复"层级倒置"漏洞（严格执行 classify_item 分类） |
| V10 | 新增疏之疏链条（全称匹配 + 前缀容错） |
| V10 | 评分取 max 替代 if-elif 短路 |
| V10 | 删除 `is_commentary_section` 死代码 |
| V10 | CSV 输出改用 UTF-8-BOM（兼容 Windows Excel） |
| V10 | 过滤同名异版互指和攝大乘論釋→釋論误配 |
