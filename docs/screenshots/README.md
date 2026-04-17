# 截图备忘

README 引用的 12 张截图（暗 6 + 浅 6）由脚本自动捕获，UI 改动后跑一次即可全部更新。

## 一键重拍

```bash
cd /data/fjlsc/80demo
python3 launcher.py &              # 服务必须在 8400 上跑
python3 scripts/capture_readme_screenshots.py
cp docs/screenshots/*.png /data/fjlsc/90_fa_yin/docs/screenshots/   # 同步
```

约 30 秒。Chrome headless，1280×820（双栏 1680×820），1x 像素比，Pillow 优化，整个目录约 2.7 MB。

## 文件命名

| 文件 | 场景 | 说明 |
|---|---|---|
| `01.png` `11.png` | 首页（暗/浅） | 警策 + 案頭 9 模块全部折叠态 |
| `02.png` `12.png` | 法脉（暗/浅） | 自动选「灵祐 A001984」展示完整谱系 + 地图 |
| `03.png` `13.png` | 阅读器单栏横排 | T0235 金刚经 |
| `04.png` `14.png` | 双栏对照 | 左 T0235 + 右 T1698 金刚般若经疏 |
| `05.png` `15.png` | 划词词典 | 自动查询「般若」 |
| `06.png` `16.png` | 阅读器直排 | 同 T0235 |

`01-06` 暗色，`11-16` 浅色。命名固定，README.md 直接引用，不要改。

## 跑之前必须做的

1. **关闭所有访问 8400 的浏览器标签** — 首页 Alpine 有自动 PUT `/api/favorites`，开着的页面可能把 in-memory 状态写回服务器，覆盖脚本对收藏夹的临时改动（如折叠卡片）。脚本内部已 monkey-patch `app.save = noop`，但残留浏览器无法控制。
2. **服务必须运行在 8400** — 脚本读 `/api/health` 探活，挂了直接退出，不会自启。

## 已知的坑

- **主题必须在导航前设定**：地图（Leaflet）、法脉图等组件在 `window.load` 时一次性读 `body.classList.contains('theme-light')`，后续主题切换不会重 init。脚本通过 `goto_with_theme()` 先访问同源轻量页面写 `localStorage.reader_theme`，再导航到目标，确保 base.html 的 inline script 在首屏就挂上 theme 类。
- **收藏夹 seed 数据**：`data/db/favorites.default.json` + `data/user_data/favorites.json` 已用 OpenCC（s2tw）转繁，备份在 `*.simp.bak`。如重置 seed 需要重跑一次转换。
- **词典面板内容仍含简体**：05/15 截图里的辞典释义来自 DDBC/通用汉语辞典等公有领域数据库，本身简体，未做转换。
- **PNG 优化只用了 Pillow `optimize=True`**：效果有限。如装 `pngquant`，脚本会自动优先用它，可再压一半。

## 脚本结构

`scripts/capture_readme_screenshots.py`：

- 复用 `capture_reader_screenshots.py` 的 CDP 客户端（websockets + Chrome headless），不引入新依赖。
- 6 个场景 × 2 主题 = 12 次 capture，每次：设 viewport → 跑 setup_js → 等 ready_js → 截图 → 保存。
- setup_js 通过 Alpine `$data` 直接操控状态（`splitMode`、`activePanel`、`writingMode`、`dictQuery`），不模拟点击。
- 所有写服务器的 sync 都被 monkey-patch 成 noop，截图过程不污染 user_data。
