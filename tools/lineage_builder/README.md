# DILA → `lineage.db` 可复现生成器

本工具用 DILA 人物 TEI、地点 TEI 和时间权威库 MySQL dump 重建项目的六表
`lineage.db`。构建过程只依赖 Python 标准库，不会定位或覆盖正式数据库。

## 构建模式

`source-faithful`（默认）优先忠实于冻结原料：

- 人物主名取第一个非别名 `persName`，别名以 JSON 列表保存；年份保留正负号；
- `is_monk` 只采信 TEI `note[@type='monk']`，未知值记入审计报告并以 `0` 降级；
- 人物 `cbeta_refs` 保留 `bibl` 的全部 `itertext()`，包括嵌套 `ref`；
- `worksInTripitaka` 按行解析行末经号，支持 `Ba001`、`T1986B`、`T0310.37`
  等 DILA 实际语法；不合语法的行一律审计；
- 师承同时读取 `teacher` 和 `student` 声明，即使端点人物不在当前快照中也保留并审计。
  同一师生键冲突时依次选择：`teacher` 声明、有 URL、较长描述、源文顺序；
- 地点只取直接位于 `listPlace` 下且带 `xml:id` 的 `place`；同一基础语言
  标签取最后一个名称；`geo` 原文是 longitude/latitude，写库时反转为
  latitude/longitude；无名但有 `xml:id` 的顶层地点用稳定占位名保留并审计；
- 时间库一个 `t_era` 生成一个年号，只用 `status='S'` 的标准月份计算范围。
  `start_from` 按月内起始日偏移处理；只有推算月份（`P`）的年号不输出，无任何月份的
  11 个年号保留且年份为 `NULL`。DILA 自身说明年代范围仍不完整，不应当作绝对断代。

`legacy-compatible` 是局部兼容剖面：人物 `cbeta_refs` 只取 `bibl.text`，年号按
`朝代 + 中文名`折叠、以最小 `era_id` 为主键，并将 `S/P` 都纳入范围。该模式不会
故意复制现用库已确认的 1,854 个 `is_monk` 异常和两个年份异常，也不承诺
与历史 SQLite 逐字相同。需要精确保留某条师承时，应使用明示的 `--edge-overrides`。

## 命令

目标数据库和所有报告路径必须事先不存在。下例故意写入仓库外的“测试运行”：

```bash
PYTHON=/path/to/venv/bin/python
SOURCE=/path/to/2026-08-24_现用DILA重建源
RUN=/path/to/测试运行/dila-lineage-source-faithful

"$PYTHON" tools/lineage_builder/build_lineage_db.py \
  --person-xml "$SOURCE/authority_person.2026-02/Buddhist_Studies_Person_Authority.xml" \
  --place-xml "$SOURCE/authority_place.2026-02/Buddhist_Studies_Place_Authority.xml" \
  --time-sql "$SOURCE/authority_time.2012-02/authority_time.sql" \
  --checksum-manifest "$SOURCE/SHA256SUMS.txt" \
  --output "$RUN/lineage.db" \
  --manifest "$RUN/build-manifest.json" \
  --audit-report "$RUN/source-audit.json" \
  --compare-to data/db/lineage.db \
  --diff-report "$RUN/legacy-diff.json"
```

可用参数：

| 参数 | 含义 |
|---|---|
| `--person-xml` / `--place-xml` / `--time-sql` | 三份必需原料 |
| `--output` | 必需、不存在的 SQLite 目标 |
| `--mode` | `source-faithful`（默认）或 `legacy-compatible` |
| `--schema` | 默认为同目录 `schema.sql` |
| `--manifest` / `--audit-report` | 显式报告路径；省略时使用输出同名后缀 |
| `--checksum-manifest` | 在解析前按文件名验证原料 SHA-256 |
| `--compare-to` / `--diff-report` | 对六表按主键、逐字段比较另一 SQLite，写 JSON |
| `--edge-overrides` | 应用经过原料哈希锁定且有理由的师承覆盖 |

覆盖文件格式：

```json
{
  "format_version": 1,
  "expected_source_sha256": {
    "person_xml": "<64-hex-sha256>"
  },
  "overrides": [
    {
      "action": "upsert",
      "source_id": "A000001",
      "target_id": "A000002",
      "edge_type": "teacher",
      "description": "经人工核实的兼容文本",
      "cbeta_ref": null,
      "reason": "具体的版本与证据说明"
    }
  ]
}
```

每条覆盖的前后值、理由、覆盖文件路径及 SHA-256 都会写入审计报告。

## 产物和验证

构建器会输出：

- `lineage.db`：固定 schema、固定排序插入并 `VACUUM` 后的 SQLite；
- manifest：生成器/模式/Python/SQLite 版本、三份原料及 schema 的 SHA-256、
  六表计数、输出 SHA-256、规则和验证结果；
- source audit：未知僧俗值、无中文名地点、非法经号、师承冲突/重复/悬空端点、
  经文关系冲突、无月份/仅推算年号和折叠详情；
- diff（可选）：六表的计数、主键新增/缺失行、公共行的每一个字段前后值和非空统计。

写库后内建执行 `PRAGMA integrity_check`、`foreign_key_check` 和 9 个必需索引检查，
任一失败都不交付目标。数据库的字节可复现性用两个不同的新目标重建后比较 SHA-256。

全部 7 个 lineage API 端点回归（依赖项目开发环境）：

```bash
"$PYTHON" tools/lineage_builder/regression_lineage_api.py \
  --lineage-db "$RUN/lineage.db" \
  --report "$RUN/lineage-api-regression.json"
```

## 测试

```bash
/path/to/venv/bin/python -m pytest -q tests/test_lineage_builder.py
```

小型 TEI/SQL fixture 位于 `tests/fixtures/lineage/`，覆盖两种模式、时间状态、嵌套文本、
坐标反转、师承去重、经号语法、哈希校验、拒绝覆盖和可审计覆盖。
