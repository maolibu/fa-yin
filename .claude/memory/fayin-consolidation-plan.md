---
name: fayin-consolidation-plan
description: 法印对照项目 2026-07-19 体检结论：暂不改动，明年 CBETA 大版本时合并 80demo→90_fa_yin 并清理过程文件
metadata: 
  node_type: memory
  type: project
  originSessionId: 4e34538e-8821-4f2f-8d64-443a21373e39
  modified: 2026-07-19T08:45:51.489Z
---

/data/fjlsc 是用户第一个 AI 合作编码项目（法印对照，CBETA 佛经阅读工具）。2026-07-19 全面体检后决定：**暂不改动**，等 2027 年 CBETA 大版本更新时一并处理——目标是最终只保留一个「仓库 + 数据」目录。

**Why:** 待修都是小补丁（4 处 <50 行），外部素材仅 CBETA 数据落后一季度，不值得单独动；用户计划多次变更，希望减少目录冗余。

2026-07-19 同日经 Codex 复核（Claude 逐条实测属实）后，行动清单拆为两块：**A 块 = 测试基线重写（近期做，只动 tests/，为换数据提供新旧回归对比）**；B 块 = 目录合并 + 数据更新 + 清理（仍等明年）。现有 tests/ 无断言、正则漏扫 18.27%、缺字检测从未生效，不能作为测试套件。

**How to apply:** 完整结论、三档清理清单和 A/B 行动清单见 `/data/fjlsc/项目检查记录_2026-07-19.md`（含第七节 Codex 复核附录），下次会话先读它。关键事实：90_fa_yin 是 git 仓库（github.com/maolibu/fa-yin）；80demo 是非 git 的运行实例，.venv 已坏，价值在数据（user_data 个人笔记不可再生；capture_reader_screenshots.py 未入库，删前必须先提交）。
