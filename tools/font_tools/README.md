# 字体测试与资产说明

本文档记录法印对照项目的字体方案评估过程和最终决策。

原 `font_tester/` 目录包含字体对比脚本和测试字体，评估完成后已清理。

## 最终部署字体（手动复制到 `90_fa_yin/public/fonts/`）

所有 Web 部署字体为 WOFF2 格式，扁平存放，无子目录。

| 文件名 | 字体 | 用途 | 大小 | 许可证 |
|---|---|---|---|---|
| `SourceHanSerif-VF.otf.woff2` | 思源宋体 VF | 经文主字体 | 19M | SIL OFL |
| `SourceHanSans-VF.otf.woff2` | 思源黑体 VF | UI 界面字体 | 14M | SIL OFL |
| `BabelStoneHan.woff2` | BabelStone Han | 符号/罕见字补充 | 7M | Freeware |
| `WenJinMinchoP0-Regular.woff2` | 文津宋体 P0 | 现代高清风格补字 | 9M | SIL OFL |
| `WenJinMinchoP2-Regular.woff2` | 文津宋体 P2 | 现代高清风格补字 | 11M | SIL OFL |
| `WenJinMinchoP3-Regular.woff2` | 文津宋体 P3 | 现代高清风格补字 | 2M | SIL OFL |
| `NanoOldSongA-Regular.woff2` | 纳米老宋 A | 古籍墨晕风格主力 | 32M | Free |
| `NanoOldSongB-Regular.woff2` | 纳米老宋 B | 古籍墨晕风格主力 | 58M | Free |
| `NanoOldSongC-Regular.woff2` | 纳米老宋 C | 古籍墨晕风格主力 | 5M | Free |
| `NanoOldSongD-Regular.woff2` | 纳米老宋 D | 古籍墨晕风格主力 | 0.3M | Free |
| `Jigmo.woff2` | 字雲 | 终极回退（100% CJK） | 7M | SIL OFL |
| `Jigmo2.woff2` | 字雲 2 | 终极回退 | 13M | SIL OFL |
| `Jigmo3.woff2` | 字雲 3 | 终极回退 | 3M | SIL OFL |

**合计约 180 MB**（WOFF2 压缩后）

## 字体下载地址（重新获取源文件用）

| 字体 | 下载地址 |
|---|---|
| 思源宋体 / 思源黑体 | https://github.com/notofonts/noto-cjk/releases |
| BabelStone Han | https://www.babelstone.co.uk/Fonts/Han.html |
| 文津宋体 (WenJinMincho) | https://github.com/takushun-wu/WenJinMincho |
| 纳米老宋 (NanoOldSong) | https://github.com/Hansha2011/NanoOldSong |
| 字雲 (Jigmo) | https://github.com/ge9/jigmern (GlyphWiki 衍生) |

## 字体更新操作流程

当字体发布新版本需要更新 WOFF2 时，按以下步骤操作：

### 1. 下载新版字体

从上方"字体下载地址"获取最新 TTF/OTF，放入 `72_font_tester/font/` 目录。
多文件字体（如 Jigmo、NanoOldSong）可使用子目录分组，避免混淆。

```
72_font_tester/font/
├── SourceHanSerif-VF.otf       # 单文件直接放
├── SourceHanSans-VF.otf
├── BabelStoneHan.ttf
├── Jigmo/                      # 多文件用子目录
│   ├── Jigmo.ttf
│   ├── Jigmo2.ttf
│   └── Jigmo3.ttf
├── WenJinMincho/
│   ├── WenJinMinchoP0-Regular.ttf
│   ├── WenJinMinchoP2-Regular.ttf
│   └── WenJinMinchoP3-Regular.ttf
└── NanoOldSongA/
    ├── NanoOldSongA-Regular.ttf
    ├── NanoOldSongB-Regular.ttf
    ├── NanoOldSongC-Regular.ttf
    └── NanoOldSongD-Regular.ttf
```

### 2. 转换为 WOFF2

```bash
cd /data/fjlsc/72_font_tester

# 增量转换（跳过已有的 WOFF2）
python convert_to_woff2.py

# 强制全部重新转换
python convert_to_woff2.py --force
```

输出目录：`72_font_tester/fonts_woff2/`（扁平结构，无子目录）

完成后手动复制到：`90_fa_yin/public/fonts/`

### 3. 验证字体覆盖（可选）

```bash
# 对比 5 个核心字体的 cmap 覆盖
python compare_fonts.py
# → 生成 font_target_5.html，浏览器打开查看

# 扫描全部字体的渲染效果
python generate_font_test.py
# → 生成 font_all_{N}.html
```

### 4. 清理源文件

转换完成后，`font/` 目录中的 TTF/OTF 可以删除（WOFF2 已在部署目录）。
需要时可重新从 GitHub 下载。

## 工具脚本说明

| 脚本 | 用途 | 输入 | 输出 |
|---|---|---|---|
| `convert_to_woff2.py` | TTF/OTF → WOFF2 批量转换 | `font/` | `fonts_woff2/` |
| `compare_fonts.py` | 5 个核心字体的 cmap 覆盖对比 | `font/` | `font_target_{N}.html` |
| `generate_font_test.py` | 全部字体渲染测试 | `font/` | `font_all_{N}.html` |

依赖：`fonttools` + `brotli-python`（已包含在 `environment.yml` 中）

## 三风格 CSS 字体堆栈

```css
/* A. 古籍墨晕：纸墨温润，书卷雅韵 */
--font-sutra-retro: "NanoOldSongA", "Jigmo", "BabelStoneHan", serif;

/* B. 禅碑金石：铁画银钩，清冷骨感 */
--font-sutra-refined: "Jigmo", "BabelStoneHan", serif;

/* C. 现代高清：笔画锐利，规范清晰（默认） */
--font-sutra-standard: "Source Han Serif SC", "WenJinMincho", "Jigmo", "BabelStoneHan", serif;

/* UI 界面 */
--font-ui: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
```

## 已评估但未采用的字体

| 字体 | 说明 | 未采用原因 |
|---|---|---|
| 花園明朝 (HanaMin) | 传统 CJK 回退字体 | 已被字雲 (Jigmo) 替代 |
| 謎乃明朝 (NazoMin) | 贝塞尔曲线优化的明朝体 | 功能被 Jigmo 覆盖 |
| 源流明體 (GenRyuMin2TC) | 台湾明体，禅碑风格 | 未最终部署 |
| 源样明體 (GenYoMin2TC) | 台湾明体变体 | 未最终部署 |
| 全字庫宋體 (TW-Sung) | 台湾政府全字库 | "可信堆栈"备选，未部署 |
| 霞鶩文楷 (LXGW WenKai) | 现代楷体 | 风格与经文不匹配 |
| LorchinSans | 藏文无衬线体 | 未使用 |
| 一點明體 (I.Ming) | IPA 明体衍生 | 被文津宋体替代 |
| 文渊宋体 (WenYuanSerif) | 现代可变宋体 | 被思源宋体替代 |
| 悉昙体 (Siddam) | 梵文悉昙字体 | CBETA PUA 不兼容，改用 GIF |
| 兰札体 (Ranjana) | 梵文兰札字体 | 同上 |
