# 当前数据与静态资产保护边界

本文记录主仓迁移验收时的正式资产、完整性基线和更新边界。
完整的第三方来源、许可链接与字体校验值见 `THIRD_PARTY_NOTICES.md`。

## 运行数据

| 资产 | 当前来源与状态 | 当前校验/数量 | 重建或更新边界 |
|---|---|---|---|
| CBETA 经文与目录 | 现用 Bookcase/CBReader 2X v0.9.9，发行包 `bookcase_v099_20260430.zip`；已迁入 `data/raw/cbeta/` | 63,088 个文件；`XML/` 内经文 XML 21,960 个；含 `toc/` 的全部 XML 26,829 个；manifest SHA-256 `84dbf34a71abba84a59f7f3c26530b05d09b79e510c22fb134c6b71093c13cb5` | 继续作为默认数据源。更新时使用隔离目录完成全量验证后再切换，不得直接覆盖现用数据。 |
| 组字映射 | CBETA 组字数据，仓内 `data/raw/cbeta_gaiji.json` | SHA-256 `6b71c27e2cdf3ddf19054b0cc11eeea2a3dad8db576dc0103edeaf96ff335fc2` | 必须跟当前 Bookcase 配套更新。 |
| 搜索库 | 由 `src/etl/etl_build_search.py` 从同一 Bookcase 重建；现用文件为 `data/db/cbeta_search.db` | source 21,960、content 21,955、catalog 4,882；SHA-256 `723c1bbbe2ed50cde16bdf40a95ab48335c7e5c442eefcad1030ae9d0d5f3e52` | 先用 `CBETA_SEARCH_DB` 与 `ETL_LOG_DIR` 指向不存在的测试目标重建和验证，然后停止写入再切换。 |
| 内置词典原料 | `data/dicts.tar.gz`，含 6 份精选 JSON（13Dicts/DILA-DDBC、fodict2 与萌典） | 29,938,772 bytes；8 个 tar 项；SHA-256 `9dc30f63bf8ebc3b1780b9de22d066ab202104fff8b19d1520660bebcc5c7728` | 用 `tools/dict_converter/build_dict_db.py --output <测试库>` 重建。现用 `data/db/dicts.db` SHA-256 为 `b8ee63d511d9c81171455b1c725f17af87a6bb0f0e3049a964414198017f4cad`。 |
| 法脉库 | `data/db/lineage.db`，来源为 DILA 佛学规范资料库（CC BY-SA 3.0） | **正式库仍未切换**：44,654,592 bytes；SHA-256 `2cdc429c4cfb2841e1ee0eb2b73bb91506293d3e122716a7405deffd46be026f`；六表计数 123 / 1,100 / 48,701 / 59,154 / 22,947 / 30,028 | `tools/lineage_builder/` 已能从冻结的 2026-02 人物/地点与 2012-02 时间原料重建。仍必须先写入“测试运行”，审查 manifest/audit/六表差异和 API 回归后才能切换；默认模式不复制旧库已知异常。 |
| 离线地图 | `scripts/download_tiles.py` 记录的 CARTO light/dark 底图；`data/tiles.tar.gz` 为当前冻结包 | 68,577,200 bytes；19,414 个 tar 项（含 18,934 张 PNG）；SHA-256 `c4a8e31450fea9d2401a9b07b07f14f2fe5f492fe8c2ac3f9e9b8852e2bf206b` | 当前包随仓保留，迁移未重新下载。CARTO / OSM 来源、ODbL 链接与应用内署名已核对。公开大规模镜像或重新批量下载前，仍需核对当时的 CARTO 服务条款。 |
| 每日偈颂 | `data/db/verses.json` 与 `tools/daily_verses/每日偈颂.csv` | 365 条；JSON SHA-256 `51d864334a42af558abb76a88c07a8a4a7467fd70ab998864bbb6e83a480a4c4` | 缺失的 CSV 已从冻结 JSON 无损恢复，`tests/test_daily_verses.py` 保证再生 JSON 逐字段一致。原始“700 处人工校改明细”未找回，恢复过程已如实写入 `校对报告.md`。 |
| 经疏映射 | `data/db/commentary_map.default.json`，由 `tools/sutra_commentary_map/` 记录的部类目录与 XML `cf` 流程产出 | 259 个顶层键；SHA-256 `069cc53a70fbbe4eea442c890588c239cbc7890f482f927b72863eb88b0a008f` | 默认映射随仓保留；维护脚本已改为项目内相对路径。更新后必须先在临时输出与当前文件对照。 |
| 默认收藏 | `data/db/favorites.default.json` | 9 个顶层项；SHA-256 `915a41433b3c073f269a6b4f60ddf9917c39bd3936fe9270fb4979318a48a9e7` | 只作为首次初始化默认值，不得覆盖现用 `data/user_data/`。 |

## 字体

`src/static/fonts/` 正式发行目录有 12 个文件，仅保留已选定的
Source Han、WenJinMincho、Jigmo 与 NanoOldSong。上游链接、许可类型与每个部署
二进制的 SHA-256 已集中记录在 `THIRD_PARTY_NOTICES.md`。

代码未引用且授权存档不完整的 Ranjana、SantipurOT 与 Siddam 已从发行目录移除，
原始评估文件仍保留在主项目的历史归档中。更新字体时必须先保存上游许可、
版本、原文件与 SHA-256，再转换 WOFF2 并完成渲染回归。

## DILA 法脉库生成器验收（2026-08-24）

默认 `source-faithful` 模式对冻结 2026-02/2012-02 原料构建两次，两个 SQLite
均为 44,511,232 bytes，SHA-256 均为
`a0ac48203a672d5d70f7a424e2e8cc5b06742c7778bdacc90113d1d1963f2d66`。这是隔离候选库，
不是当前正式库的新基准。

| 表 | 现用库 | 默认重建 | 主键新增 / 缺失 | 公共行有字段差异 |
|---|---:|---:|---:|---:|
| `dynasties` | 123 | 123 | 0 / 0 | 0 |
| `eras` | 1,100 | 1,500 | 401 / 1 | 544 |
| `persons` | 48,701 | 48,701 | 0 / 0 | 11,159 |
| `places` | 59,154 | 59,167 | 13 / 0 | 9 |
| `edges` | 22,947 | 22,947 | 0 / 0 | 88 |
| `person_scriptures` | 30,028 | 30,349 | 322 / 1 | 191 |

人物差异由完整 `cbeta_refs` 9,886 条、TEI 明示的 `is_monk` 1,854 条和两个原料年份组成；
地点公共行只剩 9 条嵌套 note 完整文本差异。师承 7 条“旧库额外”记录已证实都在
TEI `student` 声明中，因此全部保留；其中 4 条端点人物不在当前快照中，已明示审计。

隔离产物位于
`/data/工作区/阅藏/测试运行/2026-08-24_DILA_lineage_builder/release-candidate/`，
其中 `build-manifest.json`、`source-audit.json`、`legacy-diff.json` 和
`lineage-api-regression.json` 分别记录哈希/规则、源异常、逐字段差异和全部 7 个
lineage API 端点回归。`integrity_check=ok`、`foreign_key_check` 无问题，9 个必需索引齐全。

本地 2026-08 候选 ZIP 也已解压到“测试运行”并真实前瞻构建成功：六表计数为
123 / 1,500 / 49,259 / 59,335 / 23,095 / 30,406，7 个 lineage API 端点全部通过。
相对 2026-02 默认重建，人物 +561/-3、地点 +168/-0、师承 +151/-3、经文关系
+60/-3；审计仍有 30 个未知僧俗值、8 条悬空师承和 1 条不合现行经号语法的书目。
因此生成器已经可以用于年底 2026-08 更新，但正式切换仍要等年底锁版并人工审查这些
有限异常及差异报告；当前不建议替换正式 `lineage.db`。完整规则和命令见
[`tools/lineage_builder/README.md`](../tools/lineage_builder/README.md)。

## 操作约束

- Bookcase、目录、DILA、词典、字体、地图、偈颂和经疏映射均必须以本文的冻结版本完成回归。
- 可重建产物只允许先写入“测试运行”或系统临时目录；个人笔记、偏好、收藏和自定义映射先备份后才能切换。
- 任何缺少 builder 或上游许可的资产，不以推测补齐，也不因迁移擅自换版。
- 配置、冻结数据、用户数据和 Git 历史必须同时有本机主项目归档与第二份外部备份，才允许退役旧路径。
