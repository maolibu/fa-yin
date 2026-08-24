# CBETA → Obsidian Vault 转换器

使用 CBETA Bookcase 分卷版 XML（与阅读器共用同一份数据），将每部经的所有卷合并为一个 Obsidian 友好的 Markdown 文件。

**设计原则**：MD 文件只保留**纯经文正文**，所有校勘、异读、页码等学术标记由阅读器承担。

## 快速开始

先复制`.env.example`为`.env`，至少设置当前 Bookcase 路径：

```dotenv
CBETA_BASE=/path/to/cbeta
```

如数据库、个人数据或 Vault 放在仓库外，再一并设置`DB_DIR`、
`USER_DATA_DIR`和`OBSIDIAN_VAULT_DIR`。`.env`是机器专用配置，已被 Git 忽略。

**方式一：通过 launcher 自动生成**（推荐）

```bash
python launcher.py  # 一键启动：自动构建搜索数据库 + Obsidian Vault + 启动阅读器
```

**方式二：单独运行转换脚本**

```bash
# 转换心经
python obsidian_vault/xml_to_md.py --sutra T08n0251 --output /path/to/vault

# 转换大正藏
python obsidian_vault/xml_to_md.py --canon T --output /path/to/vault

# 转换全部藏经
python obsidian_vault/xml_to_md.py --all --output /path/to/vault

# 限制数量（测试用）
python obsidian_vault/xml_to_md.py --canon T --limit 50 --output /path/to/vault
```

省略`--output`时使用`OBSIDIAN_VAULT_DIR`；默认值为`obsidian_vault/output/`。
转换完成后，在 Obsidian 中选择实际输出目录并「打开文件夹作为仓库」。

## 输出结构

```
output/
├── 首頁.md                          ← 主索引（部類 + 經藏导航）
├── 目錄/
│   ├── 部類/                        ← 按部类分类（阿含部、般若部…）
│   └── 經藏/                        ← 按藏经分类（大正藏、續藏…）
├── 經文/                            ← 全部经文（一经一文件）
│   ├── T/T01/T0001_長阿含經.md       ← 多卷、跨册经合并为单文件
│   └── T/T08/T0251_般若波羅蜜多心經.md
└── 筆記/                            ← 用户笔记空间
```

## 藏经代码对照

下表经数是本轮固定 Bookcase 基线（CBReader 2X v0.9.9，
`bookcase_v099_20260430.zip`）实际生成的 4,882 部统一经号；更新数据后应以
转换器输出为准，不把这些数字当成上游永久常量。

| 代码 | 藏经名称 | 经数 |
|:---|:---|:---|
| T | 大正新脩大藏經 | 2471 |
| X | 卍新纂續藏經 | 1230 |
| J | 嘉興藏 | 285 |
| B | 大藏經補編 | 200 |
| ZW | 藏外佛教文獻 | 202 |
| I | 北朝佛拓百品 | 101 |
| N | 南傳大藏經 | 38 |
| D | 國圖善本佛典 | 64 |
| GA | 佛寺志彙刊 | 51 |
| G | 佛教大藏經 | 53 |
| Y | 印順法師著作集 | 42 |
| TX | 太虛大師全書 | 21 |
| F | 房山石經 | 27 |
| L | 乾隆藏 | 21 |
| P | 永樂北藏 | 13 |
| C | 中華大藏經 | 11 |
| A | 趙城金藏 | 9 |
| K | 高麗藏 | 9 |
| YP | 演培法師全集 | 13 |
| LC | 呂澂著作集 | 7 |
| CC | CBETA 選集 | 6 |
| M | 洪武南藏 | 1 |
| S | 宋藏遺珍 | 2 |
| GB | 佛寺志叢刊 | 2 |
| U | 卍正藏 | 2 |
| ZS | 正史佛教類編 | 1 |

## Markdown 功能详解

### YAML Frontmatter（元数据）

每个文件的头部包含：

```yaml
---
sutra_id: T0251          # 经号
title: 般若波羅蜜多心經   # 经名
author: 唐 玄奘譯         # 作者/译者
canon: 大正新脩大藏經     # 藏经名
volume: "08"              # 册号
volumes:                  # 全部来源册号（跨册经可有多个）
  - "08"
total_juan: 1             # 总卷数
source_xml_count: 1       # 合并的 Bookcase XML 数
cbeta_id: T08n0251        # CBETA 原始 ID
cbeta_ids:                # 全部官方 file ID，同时写入 aliases
  - T08n0251
aliases:
  - T08n0251
tags:
  - 佛經
  - T藏
---
```

### Block ID（精确引用）

每个段落末尾自动附加 CBETA 行号作为 Block ID：

```markdown
觀自在菩薩行深般若波羅蜜多時，照見五蘊皆空。 ^0848c07
```

- **阅读模式下完全隐藏**，不影响阅读体验
- 可精确引用：`[[T0251_般若波羅蜜多心經#^0848c07]]`
- 嵌入引用：`![[T0251_般若波羅蜜多心經#^0848c07]]`
- 官方 ID 已写入 aliases，也可用`[[T08n0251#^0848c07]]`

### 章节目录

XML 的 `<cb:mulu>` 目录标记自动转为 Markdown 标题层级：

```markdown
### 1 分                    ← level 1
#### 1 大本經               ← level 2
##### 3-5 有尋有伺等三地    ← level 3
```

便于在 Obsidian 的「大纲」面板中快速导航长经。

### 偈颂

```markdown
> 「比丘集法堂，　講說賢聖論；<br>
> 如來處靜室，　天耳盡聞知。」
```

### 校勘与注释

- **底本正文**：始终取 `<lem>`（底本/校正文），异读 `<rdg>` 不输出（阅读器已保留完整校勘信息）
- **夹注**：保留，以（括号）显示（如咒语中的「二合」「引」等读音标记，属经藏原文）
- **校勘脚注**：不输出（`<note>` 非 inline 类型、`<back>` 校勘记均略去）
- **巴利文/梵文注音**：`<cb:tt>` 只取中文部分，外语注音不输出

### 陀罗尼 / 咒语

```markdown
> 🔔 「揭帝　揭帝　般羅揭帝　般羅僧揭帝　菩提　莎婆訶」
```

### 交叉引用（疏钞 → 论本 Wikilink）

注疏类经典中的 `<ref>` 自动转为 Obsidian wikilink：

```markdown
[[T30n1579|論本卷第一]]
```

点击可直接跳转到被注释的经文，自动建立疏钞和经本之间的双向链接网络。

## 内容过滤策略

> MD 文件只保留纯经文正文，学术标记由阅读器承担。

### ✅ 保留

| 内容 | 来源标签 | MD 输出 |
|:---|:---|:---|
| 段落正文 | `<p>` | 纯文本 |
| 偈颂 | `<lg>` / `<l>` | `> ` blockquote |
| 陀罗尼 | `<p cb:type="dharani">` | `> 🔔` |
| 章节标题 | `<cb:mulu>` / `<head>` | `###` ~ `######` |
| 卷标题 | 自动生成 | `## 卷一` |
| 作者/译者 | `<byline>` | *斜体* |
| 夹注 | `<note place="inline">` | （内容） |
| 罕见字 | `<g ref>` | Unicode 字符 |
| 底本正文 | `<lem>` | 正文 |
| Block ID | `<lb>` | `^0001a09` |
| 交叉引用 | `<ref>` | `[[wikilink]]` |
| 中文术语 | `<cb:tt>` 中文部分 | 中文文本 |

### ❌ 删除

| 内容 | 来源标签 | 原因 |
|:---|:---|:---|
| 页码标记 | `<pb>` | 大正藏页码，Obsidian 阅读无用 |
| 编目号 | `<cb:docNumber>` | 如 `No. 251`，已在 frontmatter 记录 |
| 校勘脚注 | `<note>` (非 inline) | 异读比对，阅读器已保留 |
| 校勘异读 | `<rdg>` | 版本异文，阅读器已保留 |
| 校勘记 | `<back>` | 尾部校勘汇总 |
| 巴利文/梵文 | `<cb:t>` (非中文) | 注音标记 |
| 卷首标题 | `<cb:jhead>` | 含混乱校勘文本，已由卷标题替代 |

## 字体配置

项目提供预配置的 CSS snippet，实现两层字体回退：

```
思源宋体（主字体）→ 字雲明朝（100% CJK 回退）
```

### 使用方法

1. 将 `obsidian_snippets/sutra-fonts.css` 复制到 Vault 的 `.obsidian/snippets/`
2. Obsidian → 设置 → 外观 → CSS 代码片段 → 启用 `sutra-fonts`
3. 如需本地字体文件，编辑 CSS 中 `@font-face` 路径并取消注释

> 最简方案：只需系统安装思源宋体即可满足 99% 显示；加装字雲明朝 (Jigmo) 可覆盖 100%。

### 罕见字处理

- 缺字按`uni_char → norm_uni_char → norm_big5_char → composition`顺序解析
- 没有任何可用映射时保留显式 CB 编号（如`[CB01234]`），便于自动检测和复核
- 无需额外图片资源

### CSS snippet 排版效果

- 正文行高 1.85，适合长文阅读
- 偈颂居中显示，行距 2.2
- 校勘記小字灰色，不抢视线
- 陀罗尼圆角背景框

## 研究笔记工作流

### 眉批 / 段落批注

利用 Block ID 在自己的笔记中精确引用经文：

```markdown
<!-- 我的读经笔记.md -->
![[卷一#^0848c07]]

觀自在 = 觀世音。「行深」不是淺層般若，是甚深般若。
```

Obsidian 的 Callout 语法也适合做段内批注：

```markdown
> [!note] 眉批
> 此段是全經綱領...
```

### 疏钞对照

转换注疏类经典后，Obsidian 的 Graph View 会自动显示疏钞和经本之间的链接关系。可以：

- 左右分屏，一边看疏钞一边看原经
- 点击 wikilink 直接跳转到对应经卷
- 在 backlinks 面板查看哪些注疏引用了当前经文

## 关于词典

24 万条 CBETA 词典条目不适合做成 `.md` 文件（影响 Obsidian 性能）。推荐：

- **AI 查词**：安装 Obsidian AI 插件（Copilot / Smart Connections），提供词典数据作为上下文
- **高频词汇**：可单独导入约 3600 条佛学常见词汇为 `.md`

## 依赖

- Python 3.10+
- `CBETA_BASE/XML/`（CBETA Bookcase 分卷 XML，与阅读器共用）
- `CBETA_BASE/bookdata.txt`（藏经名称）
- `CBETA_BASE/bulei_nav.xhtml`（部类分类数据）
- `GAIJI_PATH`（缺字映射；默认`data/raw/cbeta_gaiji.json`）
