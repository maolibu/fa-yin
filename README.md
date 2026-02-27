# 法印对照 (Fa-Yin)

一个**本地优先**的佛经阅读工具。

CBETA 的原始数据是 XML，官方客户端有 Windows 版和 macOS 版，但没有 Linux 版，而我主力用 Ubuntu。于是自己写了这个工具，把 XML 一键转成可阅读的网页，顺便把词典、注疏对照、法脉图谱等辅助功能都做在了一起。基于浏览器，天然跨平台，Windows 和 macOS 也能用。

> **注意**：本项目代码不含任何经文数据。需要用户自行从 [CBETA 官网](https://www.cbeta.org/download) 下载指定的经文数据包 `CBETA CBReader 2X 經文資料檔` (注: 若官网有更新，请下载最新版本) ，首次启动时脚本会引导你完成。

---

## 截图

<table>
  <tr>
    <td><img src="docs/screenshots/01.png" alt="首页：每日偈颂与九宫书架" width="400"/></td>
    <td><img src="docs/screenshots/02.png" alt="传承谱系：人物·法脉·行迹" width="400"/></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/03.png" alt="经文阅读器（横排）" width="400"/></td>
    <td><img src="docs/screenshots/06.png" alt="经文阅读器（竖排）" width="400"/></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/04.png" alt="经疏对照：分栏对读" width="400"/></td>
    <td><img src="docs/screenshots/05.png" alt="划词词典：多部辞书联查" width="400"/></td>
  </tr>
</table>

---

## 核心功能

| 功能 | 说明 |
|------|------|
| **经文阅读** | 横排/竖排双模式，简繁一键切换，HTMX 无刷新翻卷 |
| **划词词典** | 内置 6 部词典（其中 1 部是通用汉语词典，以解决拼音与古文词义），双击即查。支持自定义词典文件。前期整理了 42 部词典，最终只选了基础款。因为 AI 释义越来越好用，大部分辞典查询已经可以被 AI 替代 |
| **经疏对照** | 经文与注疏左右分屏，随文对读。默认对照关系解析自 CBETA 的 XML 结构与文件夹层级，数量有限，支持自定义添加 |
| **同经异译** | 多个译本左右分栏对照，可自由组合添加 |
| **全文搜索** | SQLite FTS5 毫秒级检索，繁简通搜 |
| **AI 释义** | 选一段文字，让 AI 帮你翻译/解释（支持 DeepSeek、Ollama 本地模型等 9 家） |
| **祖师法脉** | D3.js 交互式师承图 + Leaflet 行迹地图 + 编年表 |
| **九宫书架** | 预设 9 大修学门类，覆盖 100+ 部核心经论，可自定义增删改，编辑模式下随意拖动次序 |
| **每日偈颂** | 365 条佛言祖语，一日一则，可自撰，可置顶 |
| **闪念笔记** | 读到有感触的地方随手记，按日期自动归档 |
| **贝阙经藏** | 全藏部类或经藏目录树状浏览，模糊搜索 |

### 为什么又造一个轮子

- **本地运行**：所有数据在你自己电脑上，不依赖在线服务（AI 释义和查看 CBETA 原版 PDF 页面除外）
- **三套字体环境**：思源宋体 + 文津宋体（现代规范）、字雲（疏朗明朝）、纳米老宋（复古墨晕），各花入各眼。整体覆盖 Unicode 的 CJK 统一汉字扩展区（Ext.A–Ext.J）及 IVD（表意文字异体数据库），需要图片或组合字表达的生僻字异体字越来越少
- **完整保留 CBETA 标记**：行号、校勘、注释一个不少，可以和纸本精确对照
- **零构建前端**：没有 npm、没有 Webpack，改一行代码刷新就能看
- **一键启动**：`python launcher.py`，自动检测数据、下载引导、数据库构建、启动服务

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | [FastAPI](https://fastapi.tiangolo.com) · [Jinja2](https://jinja.palletsprojects.com) | SSR 渲染，Python 单语言全栈 |
| 交互 | [HTMX](https://htmx.org) · [Alpine.js](https://alpinejs.dev) | 无需前端构建工具 |
| 数据 | [SQLite](https://sqlite.org) · FTS5 | 全文检索，毫秒级响应 |
| 可视化 | [D3.js](https://d3js.org) · [Leaflet](https://leafletjs.com) | 法脉图谱与行迹地图 |

---

## 安装与运行

### 方式一：一键启动（推荐）

**Windows 用户**：下载项目后双击 `start.bat`，脚本会自动检查 Python 环境、安装依赖、启动服务。

> **⚠️ Windows 安全提示**：从浏览器下载的压缩包会被 Windows 标记为"来自互联网"，解压后的 `.bat` 文件可能会提示"已被阻止"而无法运行。解决方法（任选其一）：
> 1. **解压前**：右键 `.zip` 文件 → 属性 → 勾选底部的 **"解除锁定"** → 确定，然后再解压
> 2. 使用 [7-Zip](https://www.7-zip.org) 等第三方工具解压（不会传播锁定标记）
> 3. 改用 `git clone` 下载（见下方 macOS / Linux 的命令）
> 4. **右键 `start.bat` → 以管理员身份运行**

**macOS / Linux 用户**：

```bash
git clone https://github.com/maolibu/fa-yin.git
cd fa-yin
chmod +x start.sh && ./start.sh
```

> 启动脚本会自动完成：检测/安装 Python → 创建虚拟环境 → 安装依赖 → 检测 CBETA 数据（缺失则引导下载）→ 构建搜索数据库（首次约 5–15 分钟）→ 启动浏览器。

### 方式二：手动安装

如果你熟悉 Python：

```bash
git clone https://github.com/maolibu/fa-yin.git
cd fa-yin
pip install -r requirements.txt
python launcher.py
```

**可选参数**：

```bash
python launcher.py --port 8080    # 指定端口（默认 8400）
python launcher.py --check        # 仅运行数据自检
python launcher.py --no-browser   # 不自动打开浏览器
python launcher.py --skip-build   # 跳过数据库构建
```

### 方式三：Docker 部署

```bash
docker build -t fa-yin .
docker run -p 8400:8400 \
  -v /path/to/cbeta:/app/data/raw/cbeta \
  -v fa-yin-db:/app/data/db \
  -v fa-yin-userdata:/app/data/user_data \
  fa-yin
```

> **提示**：如果您想在绿联 NAS (如 DX4600) 或装有 1Panel 面板的云服务器 (VPS) 上通过 Docker Compose 部署，请参考详细教程：[NAS 与 1Panel 部署指南](docs/deploy_nas_1panel.md)。

---

## 项目结构

```
fa-yin/
├── launcher.py          # 一键启动脚本
├── src/
│   ├── main.py          # FastAPI 入口
│   ├── config.py        # 全局配置
│   ├── core/            # 核心模块：XML 解析、导航、偈颂、词典
│   ├── routers/         # 路由：阅读器、搜索、词典、法脉、AI …
│   ├── etl/             # 数据库构建脚本
│   ├── templates/       # Jinja2 模板
│   └── static/          # CSS / JS / 字体
├── data/
│   ├── raw/cbeta/       # CBETA 原始数据（用户自行下载）
│   ├── db/              # SQLite 数据库（ETL 生成）
│   └── user_data/       # 用户笔记、收藏、偏好
├── tools/               # 辅助工具（词典转换、偈颂提取等）
├── tests/               # 测试脚本
└── scripts/             # 地图瓦片下载等脚本
```

### 用户数据

个人笔记、收藏、偏好等数据全部保存在 `data/user_data/` 目录下：

| 文件 | 内容 |
|------|------|
| `notes/` | 闪念笔记（每日一个 Markdown 文件），可直接用 Obsidian 打开 |
| `favorites.json` | 九宫书架收藏 |
| `preferences.json` | 显示偏好（字体、主题、排版等） |
| `verses_custom.json` | 自定义偈颂 |
| `commentary_map.user.json` | 自定义经疏对照映射 |

**备份只需复制 `data/user_data/` 整个文件夹即可。首页自带快捷方式。**

### Obsidian 联动

首次启动时，launcher 会自动将全部 CBETA XML 转为 Markdown 文件，输出到 `obsidian_vault/` 目录。你可以直接在 Obsidian 中将该文件夹作为 Vault 打开，用 Obsidian 的双向链接、图谱等功能辅助研读。笔记文件同为 Markdown 格式，指定 Obsidian 仓库路径或将 `data/user_data/notes/` 同步/复制过去即可联动。

---

## 合规声明

本项目不含任何经文数据，仅提供 XML 解析、数据库构建与全文检索的通用算法实现。该技术框架同样适用于《全唐诗》、《二十四史》等大型古籍的数字化整理。

本项目设计为 **Localhost** 个人学习用途。未经相关行政许可，**不得**用于搭建公开访问的互联网宗教信息服务平台！欢迎拥有合法资质的宗教团体、学术机构或公益组织使用本代码构建内部或公开服务，但须自行取得相应许可。

---

## 致谢

**数据**
- 经文与目录：[CBETA](https://www.cbeta.org/download)（CC BY-NC-SA 2.5 TW）
- 人名/地名/时间：[DILA 佛学规范资料库](https://authority.dila.edu.tw)（CC BY-SA 3.0）
- 词典：主要来自 [CBETA](https://www.cbeta.org/download) 和 [华夏佛典宝库](https://www.fodian.net/)（域名可能已变更），具体包括，丁福保《佛學大辭典》、Soothill–Hodous 漢英佛學詞典、法相辞典（朱芾煌 编, 1939）、三藏法数（明·一如等 撰）、祖庭事苑（北宋·陈善卿），以及通用汉语词典 [萌典](https://github.com/g0v/moedict-data)（原文 CC BY-ND 3.0 TW；格式转换部分 CC0）

**字体**
- [Source Han Serif / 思源宋体](https://github.com/adobe-fonts/source-han-serif) · [Source Han Sans / 思源黑体](https://github.com/adobe-fonts/source-han-sans)（Adobe · Google, OFL 1.1）
- [WenJin Mincho / 文津宋体](https://github.com/takushun-wu/WenJinMincho)（OFL 1.1）
- [Jigmo / 字雲](https://kamichikoichi.github.io/jigmo/)（CC0 1.0）
- [NanoOldSong / 纳米老宋](https://github.com/Hansha2011/NanoOldSong)

**AI**
- 开发过程中使用 Google Antigravity 和 GitHub Copilot 作为编程助手（代码生成/重构/排错等）
- 运行时“AI 释义”为可选功能，由用户自行配置第三方（Token 费用）或本地模型服务（显卡+电费）

**技术栈**
- [FastAPI](https://fastapi.tiangolo.com) (MIT) · [HTMX](https://htmx.org) (BSD) · [Alpine.js](https://alpinejs.dev) (MIT) · [D3.js](https://d3js.org) (ISC) · [Leaflet](https://leafletjs.com) (BSD) · [Lucide](https://lucide.dev) (ISC) · [OpenCC](https://github.com/BYVoid/OpenCC) (Apache-2.0) · [Split.js](https://split.js.org) (MIT)

---

## 为什么做这个

> 初发心时，便成正觉。——《华严经》

自 2014 年起，我开始执笔抄经，并随之发愿通读《大藏经》。2021 年，八十卷《华严经》终告圆满，然而通读大藏经的进度却依然慢如蜗牛。

究其原因，除了经文浩瀚、个人修学尚浅外，阅读工具的割裂也是一个颇为棘手的难题。经文在一处，注疏在别处，词典又在第三处。虽有 CBETA 等伟大的数字化成果，但阅读时常需在多个窗口间频繁切换、分屏对照。这种操作上的琐碎极易打断思绪，难以保持读经所需的清净专注。

那时我便萌生了一个念头：若能有一方工具，将经、疏、典收摄于同一案头，该有多好。这个想法搁置了多年。近年来 AI 辅助编程突飞猛进，让我终于有了动手的底气。于是趁丙午年春节前后的三周假期，在 AI 的协助下"独立"完成了这个项目。

回头望去，正如一颗深埋已久的种子，终究等到了属于它的季节。所谓朝花夕拾，大抵如是。

---

## 开发者说明

本项目由 AI 辅助编码完成。虽然通过数据分析逻辑确保了核心功能的实现，但由于开发周期较短，测试尚不充分，细节处难免存在 Bug。

如果您在使用中发现问题：欢迎提交 Issue 反馈建议；欢迎提交 Pull Request 协助完善。

愿这份工具能为同修志士带来一分清净阅读的便利。

---

## 许可证

代码采用 [AGPL-3.0](LICENSE) 许可证。经文数据等版权归 CBETA 及相关机构所有。
