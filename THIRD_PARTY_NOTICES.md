# 第三方数据与静态资产说明

项目根目录的 `LICENSE` 只适用于项目自有代码与文档。下列数据、字体、
地图与第三方库仍分别受其上游条款约束。本文档是迁移时的来源与完整性
记录，不取代上游许可证原文。

## Web 字体

| 部署文件 | 来源 | 许可 | SHA-256 |
|---|---|---|---|
| `SourceHanSans-VF.otf.woff2` | [Noto CJK / Source Han](https://github.com/notofonts/noto-cjk) | [SIL OFL 1.1](licenses/OFL-1.1.txt) | `e6859af225ab928e9326fe435723d1f4b8302c8307d1dd8da272b525d715e05c` |
| `SourceHanSerif-VF.otf.woff2` | [Noto CJK / Source Han](https://github.com/notofonts/noto-cjk) | [SIL OFL 1.1](licenses/OFL-1.1.txt) | `8e7c0bbea734636530f8ecf2cb579f550a9ca4cbc2e95f25c99860897cc13bdf` |
| `WenJinMinchoP0-Regular.woff2` | [WenJin Mincho](https://github.com/takushun-wu/WenJinMincho) | [SIL OFL 1.1，含 WebFont 格式转换例外](https://github.com/takushun-wu/WenJinMincho/blob/main/LICENSE.md) | `d3e5aaf8cc043b7d02dde52cb623e6fcf47ba016702e4618021ae4790e6e5067` |
| `WenJinMinchoP2-Regular.woff2` | 同上 | 同上 | `4b96fa7be25f5eae445091355adcb5c365a25c9b5edf023d658b0df42a5efaa0` |
| `WenJinMinchoP3-Regular.woff2` | 同上 | 同上 | `77e90f59949294816e019d34935255568ddb2701948558500d1b4b9b27c16eba` |
| `Jigmo.woff2` | [Jigmo（字雲）官方发布页](https://kamichikoichi.github.io/jigmo/) | CC0 1.0（字形） | `01309b13aa4318e6b970353ccfcbdeb9aa1065412bb820bd1bf854b4bab89bf1` |
| `Jigmo2.woff2` | 同上 | 同上 | `6b9ffb80c337ced7b9e53ea6eb7fc2e36a45fe0c440dcdb9c697aa6ec6fe9508` |
| `Jigmo3.woff2` | 同上 | 同上 | `a65a514ed54656c2fe9404e522b2a07b82f490ecb1a444968a768ebf76d5c411` |
| `NanoOldSongA-Regular.woff2` | [NanoOldSong](https://github.com/Hansha2011/NanoOldSong) | 汇文明朝系自定义授权；允许免费嵌入、转发和格式转换，不得单独售卖字体 | `c106e4fe19d7dc00cbf46cfbdb7c0bbf69451a17fdb4a6025dac6fa2d91753c1` |
| `NanoOldSongB-Regular.woff2` | 同上 | 同上 | `9efc390837e6fdc02e96330e0cfc62104fc84e690d223e3676e68859b97a4a00` |
| `NanoOldSongC-Regular.woff2` | 同上 | 同上 | `f90da082cba1f1deba285cc6bc2c14c65721800fdc16eba4322fd012d7b08d99` |
| `NanoOldSongD-Regular.woff2` | 同上 | 同上 | `72d45da376d19d1616f42dc585d634f5a21ae571ed9d96e1d2eb533eb4562e60` |

WenJin Mincho 的上游版权声明与 OFL 条款见上表许可证链接。WOFF2 只用于
网页交付，项目没有修改字形。迁移时已从发行目录删除代码未引用且授权
存档不完整的 `Ranjana.otf`、`Siddam.otf` 和 `SantipurOT.ttf`。

OFL 字体的版权与保留名称声明：

- Source Han Sans：Copyright 2014–2025 Adobe，Reserved Font Name `Source`。
- Source Han Serif：Copyright 2017–2022 Adobe，Reserved Font Name `Source`。
- WenJin Mincho：Copyright 2024–2026 Takushun Wu，Reserved Font Names
  `WenJin Mincho`、`文津宋体`、`文津宋體`、`文津明朝`、`문진(文津) 명조`。
- WenJin Mincho 上游声明：Copyright 2010–2025 Adobe（Reserved Font Name
  `Source`）；Copyright 2021–2025 Tamcy；Copyright 2022–2025 Shanggu Fonts；
  © 2007–2024 Adobe, But Ko, CMEX, Creative Commons Corporation, GlyphWiki &
  Night Koo；Copyright 2022 The Noto Project Authors；Copyright © 2015 Google Inc.；
  Saudi Riyal Font © Emran Alhaddad。

## 地图瓦片

`data/tiles.tar.gz` 是由 `scripts/download_tiles.py` 记录的 CARTO light/dark 底图冻结包：

- SHA-256：`c4a8e31450fea9d2401a9b07b07f14f2fe5f492fe8c2ac3f9e9b8852e2bf206b`
- 底图设计与服务：[CARTO](https://carto.com/)
- 地图数据：[OpenStreetMap contributors，ODbL](https://www.openstreetmap.org/copyright)
- 应用的 Leaflet 地图右下角始终显示 `© CARTO © OSM`，并链接到上述页面。

当前冻结包可用于本地离线运行与已有部署的迁移恢复。任何公开大规模
镜像、转售或重新批量下载行为，都应另行核对当时的 CARTO 服务条款。

## 佛典、规范数据与辞典

- CBETA 经文、目录、缺字与悉曇图片：见 [CBETA 官网](https://www.cbeta.org/)
  与发行包内的 README / 授权说明。
- DILA 佛学规范资料库的人物、地名与时间数据：来源记录与上游文件保存于
  主项目的 `下载/` 与 `归档/`目录；现用 `data/db/lineage.db` 冻结文件的
  SHA-256 为 `2cdc429c4cfb2841e1ee0eb2b73bb91506293d3e122716a7405deffd46be026f`。
- 内置辞典：参见 `tools/dict_converter/README.md` 与
  `tools/dict_converter/build_dict_db.py` 中的分辞典来源元数据。

## 前端第三方库

`src/static/js/lib/` 与 `src/static/css/lib/` 内的离线库保留了其上游文件头的
版本与许可声明。其中 Leaflet 1.9.4 采用 BSD-2-Clause，D3 等其他组件
依各自文件头或官方发行许可。
