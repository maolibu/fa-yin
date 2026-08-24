# 迁移与完整回归命令

本文件给出当前代码的权威开发、迁移和本地数据回归命令。所有重建数据库、报告和 Vault 必须指向隔离测试目录，不得使用现用`data/db/`、`data/user_data/`或现用 Vault。

## 1. 干净依赖环境

```bash
python3.13 -m venv /path/to/test-run/venv
/path/to/test-run/venv/bin/python -m pip install -r requirements-dev.txt
```

## 2. 单元测试

```bash
/path/to/test-run/venv/bin/python -m pytest
```

## 3. 21,960 个 Bookcase XML 全量扫描

```bash
CBETA_BASE=/path/to/bookcase \
TEST_OUTPUT_DIR=/path/to/test-run/reports \
/path/to/test-run/venv/bin/python tests/scan_note_formats.py \
  --expected-count 21960

CBETA_BASE=/path/to/bookcase \
TEST_OUTPUT_DIR=/path/to/test-run/reports \
/path/to/test-run/venv/bin/python tests/smoke_test_parser.py \
  --expected-count 21960
```

两个扫描命令都会严格校验文件数和 XML 解析错误；阅读解析器扫描还会在注释泄漏或未解析 CB 缺字存在时返回非零退出码。

## 4. 隔离重建搜索数据库

目标文件必须预先不存在：

```bash
CBETA_BASE=/path/to/bookcase \
CBETA_SEARCH_DB=/path/to/test-run/db/cbeta_search.db \
ETL_LOG_DIR=/path/to/test-run/logs/etl \
/path/to/test-run/venv/bin/python src/etl/etl_build_search.py --all
```

全量 ETL 会对账源文件、唯一经号、逻辑卷、源文件台账和 FTS docsize，并执行 FTS5 integrity-check；任何 XML 失败或计数差异均返回非零退出码。

## 5. 隔离生成 Obsidian Vault

```bash
CBETA_BASE=/path/to/bookcase \
OBSIDIAN_VAULT_DIR=/path/to/test-run/obsidian-vault \
/path/to/test-run/venv/bin/python obsidian_vault/xml_to_md.py \
  --all --output /path/to/test-run/obsidian-vault
```

## 6. 启动自检

通过环境变量把搜索库、词典库、法脉库和用户数据全部指向隔离路径，再运行：

```bash
CBETA_BASE=/path/to/bookcase \
CBETA_SEARCH_DB=/path/to/test-run/db/cbeta_search.db \
DICTS_DB=/path/to/test-run/db/dicts.db \
LINEAGE_DB=/path/to/test-run/db/lineage.db \
USER_DATA_DIR=/path/to/test-run/user_data \
OBSIDIAN_VAULT_DIR=/path/to/test-run/obsidian-vault \
/path/to/test-run/venv/bin/python launcher.py --check
```

## 7. 隔离截图冒烟

先用上节的全部隔离环境变量启动本地服务，再把截图明确写入测试产物目录：

```bash
/path/to/test-run/venv/bin/python scripts/capture_reader_screenshots.py \
  --base-url http://127.0.0.1:8400 \
  --output-dir /path/to/test-run/screenshots/reader
```

脚本只读配置的`CBETA_SEARCH_DB`选择经文；Chrome 先停在`about:blank`，在首次导航前拦截 fetch、XMLHttpRequest 和 sendBeacon 写请求，再在页面内禁用偏好、对照、AI和经疏同步。`--output-dir`为必填，防止批量截图误写进 Git 仓库。README 使用的 12 张人工基准图由`capture_readme_screenshots.py`单独维护，不属于每轮批量测试产物。

中文完整路径回归使用同一组命令，只把仓库与`/path/to/test-run`替换为真实中文绝对路径。
