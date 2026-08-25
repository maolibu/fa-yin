# 法印对照（fa_yin）— AI 协作说明

本仓是 `/data/工作区/阅藏/` 的唯一权威代码与数据仓库（2026-08-24 自 `/data/fjlsc/90_fa_yin` + `80demo` 迁入）。旧路径 `/data/fjlsc`、`80demo`、`90_fa_yin`、`01_data_raw` 一律不再引用。

## 目录约定（阅藏/ 一级）

- `fa_yin/` — 本仓：代码、固定版 CBETA Bookcase、三份正式 SQLite、个人数据、Vault。`.env` 只用仓库内相对路径。
- `../下载/` — 上游材料临时落点，每个来源独立目录 + `SOURCE.md`；不进 Git，不放唯一副本。
- `../测试运行/` — 隔离回归与可重建产物；新数据先在这里验收，通过后才切换正式配置。
- `../冷归档/` — 冻结版本、个人数据、验收证据；每目录带 `归档说明.md` + `SHA256SUMS.txt`，并单向备份到 `/home/bml/fa_yin_backups/`（另一物理盘）。
- `../等待更新.md` — 迁移与数据更新的权威流水记录，做重大变更前先读末尾几节。

## 硬规则

1. **正式数据库不直接覆盖。** `data/db/lineage.db` 现为 SHA-256 `2cdc429c...026f`；DILA 2026-08 候选已能用 `tools/lineage_builder/` 可复现重建，但仍有 30 个未知僧俗值 + 8 条悬空师承待人工审查，按"年底锁版 + 差异审查 + 显式切换"闸门执行，不提前切换。
2. **CBETA 源不混用。** `data/raw/cbeta/` 是 Bookcase v0.99（2026-04-30）；GitHub `xml-p5` 是"一部经一文件"的 P5 源，结构不同，不能直接替换 `XML/`。切换前必须先做 `CBETA_SOURCE` 适配层和等价验证。
3. **外部动作需用户明确授权**：`git push`、向 NAS 传输含个人数据的副本、Docker 部署。本机无 GitHub 凭据；`main` 领先 `origin/main` 若干本地提交属正常状态。
4. **不删仓外目录**，除非用户明确裁定；删前先核对 `../冷归档/` 与异盘备份覆盖情况。
5. 数据版本、校验值与更新边界以 `docs/data_assets.md` 为准；第三方资产来源与许可以 `THIRD_PARTY_NOTICES.md` 为准，缺许可不得冒充自由许可。

## 验证命令

- 单元测试：`python -m pytest -q`（当前 39 passed）
- 路径自检：`python3 launcher.py --check`
- 完整回归（21,960 个 XML 全扫、隔离库重建、27 端点 API、中文路径）：见 `docs/migration_testing.md`

## 沿自 2026-07-19 体检的有效待办（原件见 `../冷归档/调研规划/`）

迁移前的项目记忆绑定在 `/data/fjlsc` 路径下，已随旧路径失效并冻结到 `../冷归档/2026-08-24_AI记忆与配置/claude项目记忆/`。其中"暂不改动、等 2027 年再合并目录"的结论已被 8 月迁移取代；以下判断仍有效：

- **测试基线（原 A 块）尚未闭环。** 迁移只补了 39 个 pytest 用例；`tests/scan_note_formats.py`、`tests/smoke_test_parser.py` 仍是旧的手工扫描脚本：无断言、永远退出码 0、文件名正则漏扫 18.27%（`CC`/`TX`/`GA`/`ZW` 前缀及 n 后带字母者）、缺字检测因 `#` 前缀不一致从未生效、直调私有 `_render()`。下一次更换 CBETA/DILA 数据前应先把它们改成真正的回归测试，否则新旧数据无法对比。DILA `cbeta-api` / `cbeta-normal-text` 可作解析器交叉验证基准。
- **README §数据来源的 CBETA 授权写法待核。** 体检时判定 `README.md:203` 的 "CC BY-NC-SA 2.5 TW" 过时，应为 CC BY-NC-SA 4.0 并注明四部排除文集；迁移后此行未改。改前到 https://www.cbeta.org/copyright.php 复核当前条款，不凭记忆改。
- **功能方向优先级**（2026-07-19 同类项目调研结论，FoJin / cbetar2 / Bilara / NTI 对照后得出）：段落级稳定 ID（用 CBETA 原生坐标）→ 一键引用导出 → `sources.yml` 来源清单 → 注疏关系升级 → 独立标注层。FoJin 的跨藏对齐未经人工审核，不可直接采信。
- 词典、字体逐项来源/许可确认仍是既有待办（见 `../冷归档/辞典202602/`、`辞典原始包202602/`、`字体202602/` 的说明文件）。

## 环境

- 运行/测试用本仓 `.venv`（Python ≥ 3.10，迁移回归在 3.13）。`tools/sutra_commentary_map/` 注释里的 `~/miniforge3/envs/fjlsc` 是旧环境名，仅为历史遗留。
- 系统无 `sqlite3` CLI，用 Python `sqlite3` 模块；只读检查用 `file:...?mode=ro` URI，避免生成 `-wal`/`-shm`。
- 本机无 Docker/Podman；容器相关验证移到 NAS 部署阶段。
