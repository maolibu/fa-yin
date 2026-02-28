# 多人使用的可能性

法印目前是个人版（单用户设计）。最理想的多人方案当然是升级代码支持多用户，但在此之前，以下是几种在现有架构下的变通思路。

## 为什么用 Tailscale？

- **免费**：个人版支持最多 100 台设备，绰绰有余。
- **合规**：流量走点对点加密隧道，不经过公网，本质是"局域网内部使用"，无需域名备案。
- **无需改代码**：法印不需要做任何修改，朋友通过 Tailscale 分配的内网 IP 访问即可。
- **手机友好**：Tailscale 有 iOS 和 Android 客户端，朋友装上就能用。

## 操作步骤

### 1. 你（NAS 端）

1. 前往 [tailscale.com](https://tailscale.com) 注册账号（可用微软/Google/GitHub 登录）。
2. 在 NAS 上安装 Tailscale：
   - **群晖**：套件中心搜索 Tailscale，或从 [官方页面](https://tailscale.com/download) 下载 `.spk` 安装。
   - **1Panel / Linux VPS**：SSH 执行 `curl -fsSL https://tailscale.com/install.sh | sh`，然后 `tailscale up`。
   - **绿联 / 其他 NAS**：可通过 Docker 方式安装，搜索 `tailscale/tailscale` 镜像。
3. 登录成功后，NAS 会获得一个 `100.x.x.x` 的 Tailscale 内网 IP。

### 2. 朋友（手机端）

1. 手机应用商店搜索 **Tailscale** 并安装（iOS / Android 均有）。
2. 你在 Tailscale 管理后台 → **Share** 功能邀请朋友的账号加入你的网络（或让朋友用自己的 Tailscale 账号，你共享节点给他）。
3. 朋友手机上打开 Tailscale 连接后，浏览器访问 `http://100.x.x.x:8400`（替换为你 NAS 的 Tailscale IP）即可。

> 💡 朋友也可以把这个地址"添加到主屏幕"，这样就像一个 App 一样直接打开。

## ⚠️ 重要：建议一人一个实例

法印目前是**单用户设计**，以下设置和数据在同一个实例中是**全局共享**的：

- 简体 / 繁体切换
- 黑底 / 白底（深色模式）
- 字体大小、横排 / 竖排
- 案头自定义布局
- AI 释义的 API Key（一人填入，所有人消耗他的额度）
- 书签、高亮标注、阅读笔记

**一个人改了设置，其他人看到的也跟着变。** 所以多人共用一个实例体验很差。

### 推荐做法

如果朋友也想用法印，**帮他在他自己的设备上单独部署一套**（哪怕是一台便宜 VPS），每人独立运行、独立设置。Tailscale 的作用是让你可以**远程帮他维护和管理**他那套实例，而不是把你自己的实例共享出去。

> 💡 如果将来真有多人共用一个实例的需求，升级方案是把这些设置改为浏览器本地存储（localStorage），每人的浏览器各存各的。但目前用的人少，不急着做——有人提了再说。

---

## 📦 进阶：一台服务器给多人各跑一个实例

如果你有一台 VPS 或高性能 NAS，可以用 Docker 在一台机器上同时跑多个法印实例——每人独立设置、独立笔记，互不干扰。

### 资源估算

Docker 容器共享系统内核，开销远比虚拟机小。法印的主要资源消耗如下：

| 资源 | 单实例 | 10 个实例 |
|------|--------|-----------|
| 磁盘 | ~500 MB（数据库） | ~4 GB 共享经文 + 10 × 500 MB ≈ **9 GB** |
| 内存 | ~50-100 MB 空闲时 | ~500 MB - 1 GB |
| CPU | 几乎为零（查询毫秒级） | 日常无压力 |

> ⚠️ **唯一压力点**：每个容器首次启动时要跑 ETL 建库（5-15 分钟满核）。建议**逐个启动**，建完一个再开下一个，不要 10 个同时首次启动。

**服务器配置参考**：2 核 4 GB（约 ¥50/月）可以轻松带 10 个实例。

### docker-compose 示例

核心技巧：**CBETA 经文数据只存一份，所有容器只读共享**，只有数据库和用户数据各自独立。

```yaml
version: '3.8'

services:
  # ---- 用户 1 ----
  fa-yin-user1:
    build: .
    container_name: fa-yin-user1
    restart: unless-stopped
    ports:
      - "8401:8400"
    volumes:
      - /opt/shared-cbeta:/app/data/raw/cbeta:ro    # 共享经文，只读
      - ./user1/db:/app/data/db                      # 独立数据库
      - ./user1/user_data:/app/data/user_data        # 独立用户数据
    environment:
      - TZ=Asia/Shanghai

  # ---- 用户 2 ----
  fa-yin-user2:
    build: .
    container_name: fa-yin-user2
    restart: unless-stopped
    ports:
      - "8402:8400"
    volumes:
      - /opt/shared-cbeta:/app/data/raw/cbeta:ro
      - ./user2/db:/app/data/db
      - ./user2/user_data:/app/data/user_data
    environment:
      - TZ=Asia/Shanghai

  # ---- 更多用户照此格式添加，端口号递增 ----
```

每位用户通过 `http://服务器IP:8401`、`8402`… 各自访问自己的实例。配合 Tailscale，朋友在手机上也能用。

---

> 📝 以上 Tailscale 组网和多实例部署只是两种举例，技术方案远不止这些。最根本的解决方案当然是升级代码原生支持多用户。但说实话，大概率不会做 😂。一个人安安静静读经，本来就挺好的。