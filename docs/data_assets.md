# 当前数据与静态资产保护边界

本文只说明主仓迁移时必须保持的现状，不授权下载、升级或替换任何数据。
迁移验收应使用下表所列文件或现用 Bookcase；重建命令只能写入显式指定的测试目录。

## 运行数据

| 资产 | 当前来源与状态 | 当前校验/数量 | 重建或更新边界 |
|---|---|---|---|
| CBETA 经文与目录 | 仓库外现用 Bookcase/CBReader 2X v0.9.9，发行包名记录为 `bookcase_v099_20260430.zip` | 63,088 个文件；其中 XML 21,960 个。迁移冻结 manifest SHA-256 `84dbf34a71abba84a59f7f3c26530b05d09b79e510c22fb134c6b71093c13cb5` | 继续作为默认数据源。本轮不得下载或切换新版，不开发 GitHub P5 目录生成器。经文与目录版权/许可按 CBETA 发行说明和 README 致谢执行。 |
| 组字映射 | CBETA 组字数据，仓内 `data/raw/cbeta_gaiji.json` | SHA-256 `6b71c27e2cdf3ddf19054b0cc11eeea2a3dad8db576dc0103edeaf96ff335fc2` | 跟随当前 Bookcase 配套版本；本轮不得替换。 |
| 搜索库 | 由 `src/etl/etl_build_search.py`从同一 Bookcase 重建 | 当前全量测试基线：source 21,960、content 21,955、catalog 4,882 | 只可用 `CBETA_SEARCH_DB`和`ETL_LOG_DIR`指向不存在的测试目标重建；不得覆盖现用库。 |
| 内置词典原料 | `data/dicts.tar.gz`，含 6 份精选 JSON（13Dicts/DILA-DDBC、fodict2 与萌典） | 29,938,772 bytes；8 个 tar 项；SHA-256 `9dc30f63bf8ebc3b1780b9de22d066ab202104fff8b19d1520660bebcc5c7728` | 许可证和来源见 README 与 `tools/dict_converter/build_dict_db.py`元数据。用 `build_dict_db.py --output <不存在的测试库>`重建；不得覆盖现用库。外部旧转换工作区本轮不整理。 |
| 法脉库 | `data/db/lineage.db`，README 记录来源为 DILA 佛学规范资料库（CC BY-SA 3.0） | 44,654,592 bytes；SHA-256 `2cdc429c4cfb2841e1ee0eb2b73bb91506293d3e122716a7405deffd46be026f`；6 个业务表 | 仓库及旧工作区均未找到 DILA→SQLite builder。现用部署与 Git 文件逐字相同；迁移冻结快照因 SQLite backup 重排页而文件 SHA 不同，但逐表逐行摘要相同。本轮只保留、复制和只读验证，不重建、不升级。 |
| 离线地图 | `scripts/download_tiles.py`记录为 CARTO light/dark 底图，`data/tiles.tar.gz`为当前冻结包 | 68,577,200 bytes；19,414 个 tar 项（含 18,934 张 PNG）；SHA-256 `c4a8e31450fea9d2401a9b07b07f14f2fe5f492fe8c2ac3f9e9b8852e2bf206b` | 当前包随仓保留。本轮禁止重新下载。脚本未保存精确下载日期、上游版本或完整再分发许可证据；未来更新/再发布前必须另做 CARTO/OSM 许可和署名审查。 |
| 每日偈颂 | Git 跟踪的 `data/db/verses.json` | 365 条；SHA-256 `51d864334a42af558abb76a88c07a8a4a7467fd70ab998864bbb6e83a480a4c4` | README 所称正式 CSV 与校对报告当前缺失；该 JSON 视为不可完整重建资产，迁移期间禁止覆盖。研究脚本迁移后另审。 |
| 经疏映射 | `data/db/commentary_map.default.json`，由 `tools/sutra_commentary_map/`记录的部类目录与 XML `cf`流程产出 | 259 个顶层键；SHA-256 `069cc53a70fbbe4eea442c890588c239cbc7890f482f927b72863eb88b0a008f` | 当前默认映射随仓保留。旧维护脚本仍有历史绝对路径，本轮不执行；迁移后修复并复核原料再允许更新。 |
| 默认收藏 | `data/db/favorites.default.json` | 9 个顶层项；SHA-256 `915a41433b3c073f269a6b4f60ddf9917c39bd3936fe9270fb4979318a48a9e7` | 只作为首次初始化默认值；不得覆盖现用 `data/user_data/`。 |

## 字体

`src/static/fonts/`当前有 15 个文件、182,380,804 bytes。README 与
`tools/font_tools/README.md`记录了 Source Han、WenJinMincho、Jigmo、
NanoOldSong 等来源；其中思源、文津与字雲的许可说明较明确，仓库对
NanoOldSong、Ranjana、SantipurOT、Siddam 的精确二进制版本、下载日期和
随附许可证据记录不完整。

迁移期间全部字体按 Git 对象原样保留，不从旧 `72_font_tester/`反向覆盖，
不重新转换。迁移验收后的独立许可审查应先补齐每个二进制的来源、版本、
许可证原文与 SHA-256，再决定是否更新或调整分发范围。

## 迁移约束

- Bookcase、目录、DILA、词典、字体、地图、偈颂和经疏映射版本均保持不变。
- 可重建产物只写入“测试运行”目录；个人笔记、偏好、收藏和自定义映射只做校验与备份。
- 缺失 builder 或许可证据的资产不以推测补齐，不因迁移擅自换版。
- 大型配套资产是否移出 Git 仓库，待完整主仓迁移验收后另行审查。
