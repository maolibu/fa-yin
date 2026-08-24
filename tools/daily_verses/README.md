# 每日偈颂（Daily Verses）

佛教经典偈颂的校对、转换工具，为首页“警策”栏目提供每日一偈。

## 数据文件

| 文件 | 说明 |
|---|---|
| `每日偈颂.csv` | **正式数据**：365 条偈颂（偈颂、出处） |
| `校对报告.md` | 数据来源、恢复方式与校验记录 |

## 脚本

### `csv_to_verses_json.py`

将 `每日偈颂.csv` 转换为 `data/db/verses.json`，供 FastAPI 后端读取。
脚本自动按全角 `｜` 分段，并生成 1–365 的序号。

```bash
python tools/daily_verses/csv_to_verses_json.py

# 先写入临时目录核对，不覆盖正式数据
python tools/daily_verses/csv_to_verses_json.py --output /tmp/verses.json
```

### `proofread_verses.py`

CSV 校对脚本，包含：

- OpenCC 简→繁转换（含佛经特有过度转换修正）
- OCR 错字修正（经 CBETA 原文比对确认）
- 出处格式统一（书名号、经名补全、作者分隔）
- 分段符统一（全角 `｜`）
- 重复检测

### 其他脚本

- `extract_cbeta_verses.py`：从 CBETA Markdown 文件中提取 blockquote 格式偈颂。
- `select_doctrinal.py`：从大藏经提取结果中精选教理偈颂。
- `ocr_pdf.py`：扫描 PDF 的 OCR 识别工具。

## 一致性保证

`tests/test_daily_verses.py` 会把 CSV 转成临时 JSON，并与仓内
`data/db/verses.json` 进行逐字段比对。未通过此测试时不应发布新版偈颂。

## 依赖

```text
opencc-python-reimplemented
PyYAML
```
