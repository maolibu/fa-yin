# 经文-疏钞映射工具

从 CBETA 数据中自动生成经文与注疏的对应关系。

## 数据来源

使用两种可靠数据源：

| 方法 | 来源 | 说明 |
|------|------|------|
| `xml_cf_tag` | CBETA XML `<cf>` 标签 | CBETA 官方标注，最可靠 |
| `folder_hierarchy` | `bulei_nav.xhtml` 目录分组 | 利用目录名中的经文 ID 范围区分经/疏 |

## 文件说明

| 文件 | 说明 |
|------|------|
| `generate_mapping_json.py` | 生成脚本 |
| `cbeta_cf_mapping.json` | 输入：CBETA XML cf 标签数据 |
| `work_title_cache.json` | 输入：work_id → 标题缓存 |
| `cbeta_sutra_commentary_map.json` | **输出：主映射文件** |
| `cbeta_mapping_needs_review.json` | 输出：需人工审核条目 |

## 使用方法

```bash
cd /data/fjlsc/60_ready/tools/sutra_commentary_map
~/miniforge3/envs/fjlsc/bin/python generate_mapping_json.py
```

## 当前结果

- 经文 152 个，注疏映射 753 条
- `xml_cf_tag`: 214 条（CBETA 官方）
- `folder_hierarchy`: 539 条（目录结构解析）
- 需审核 16 条（CF 互指 11 + 无 ID 目录 5）
