# 每日偈頌（Daily Verses）

佛教經典偈頌的校對、轉換工具。為首頁「警策」欄目提供每日一偈。

## 數據文件

| 文件 | 說明 |
|------|------|
| `每日偈颂.csv` | **正式數據**：365 條校對版偈頌（偈頌、出處） |
| `校对报告.md` | 校對修改明細（700 處修改記錄） |

## 腳本

### `csv_to_verses_json.py`
將 `每日偈颂.csv` 轉換為 `data/db/verses.json`，供 FastAPI 後端讀取。
自動按全角 `｜` 分段、生成序號 1-365。

```bash
python csv_to_verses_json.py
```

### `proofread_verses.py`
CSV 校對腳本，包含：
- OpenCC 簡→繁轉換（含佛經特有過度轉換修正）
- OCR 錯字修正（經 CBETA 原文比對確認）
- 出處格式統一（書名號、經名補全、作者分隔）
- 分段符統一（全角 `｜`）
- 重複檢測

### `extract_cbeta_verses.py`
從 CBETA Markdown 文件中提取 blockquote 格式的偈頌段落。

### `select_doctrinal.py`
從大藏經提取結果中精選教理偈頌（評分排序）。

### `ocr_pdf.py`
掃描 PDF 的 OCR 識別工具。

## 依賴

```
opencc-python-reimplemented
PyYAML
```
