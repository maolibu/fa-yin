# NAS 与云服务器 (VPS) Docker 部署指南

本项目 `fa-yin` 原生支持 Docker 部署。无论你使用的是各类成品 NAS（群晖、绿联等），还是安装了 1Panel/宝塔面板的云服务器（VPS），都是通过 **Docker Compose** 来拉起服务。

核心思路非常清晰，分为四步：**1. 获取源码定下目录框架** ➡️ **2. 填入庞大的经文数据源** ➡️ **3. 配置 Docker** ➡️ **4. 一键启动**。

---

## 📍 第一步：获取源码（确立项目目录）

你需要先把源码保存到服务器（或 NAS）上的某个位置，**这个文件夹接下来就是你的“项目主目录”**。

- **对于云服务器 (VPS) 或熟悉命令行的 NAS 用户**：
  直接 SSH 连入服务器，找一个宽敞的路径（如 `/opt`），执行：
  ```bash
  git clone https://github.com/maolibu/fa-yin.git /opt/fa-yin
  cd /opt/fa-yin
  ```
  此时你的主目录就是 `/opt/fa-yin`。你会看到里面包含了 `docker-compose.yml` 等文件。

- **对于使用可视化面板的用户（1Panel / NAS 网页端）**：
  1. 在本地电脑下载项目源码 ZIP 压缩包并解压。
  2. 登录 1Panel 的“文件”菜单，或 NAS 的“文件管理”。
  3. 在你喜欢的位置（比如 `/volume1/docker/fa-yin`）创建一个文件夹。
  4. 将解压后的**所有源码文件**上传进去（上传压缩包再在线解压更快）。

---

## 📍 第二步：准备 CBETA 经文数据源

本项目不自带庞大的佛经数据，需要你自行下载并放进刚才设立的目录里。

1. **下载数据包**：前往 [CBETA 官网下载页](https://www.cbeta.org/download) 下载包含 `.xml` 文件的压缩包（文件名通常叫 `CBETA CBReader 2X 經文資料檔` ）。
2. **解压数据**：在你的电脑上将这个压缩包解压，会得到一个名为 `CBETA` 的文件夹（内含 `XML/`、`toc/` 等子目录，共几万个文件）。
3. **上传至服务器**：
   将解压得到的 `CBETA` 文件夹**重命名为小写 `cbeta`**，然后上传到项目主目录的 `data/raw/` 下（CBETA 数据含几万个小文件，强烈建议上传压缩包后在线解压）。最终结构如下：
   
   ```text
   你的主目录/ (例如 /opt/fa-yin/)
   ├── docker-compose.yml
   ├── src/
   ├── launcher.py
   └── data/
       └── raw/
           └── cbeta/              <--- 注意小写！
               ├── XML/            （经文 XML，核心数据）
               ├── toc/            （目录数据）
               ├── sd-gif/         （悉昙字图片）
               ├── advance_nav.xhtml
               ├── bulei_nav.xhtml
               └── ...
   ```


---

## 📍 第三步：修改 `docker-compose.yml`

有了代码，有了数据，现在只需告诉 Docker 它们在哪里。

用文本编辑器打开项目主目录下的 `docker-compose.yml` 文件。**你只需要修改一行**——把 CBETA 数据的路径填进去。

找到 `volumes` 部分，将第一行的 `/path/to/your/cbeta` 替换为你实际存放 CBETA 数据的路径：

```yaml
    volumes:
      # ⚠️ 将冒号左边替换为你的 CBETA 数据实际路径
      - /path/to/your/cbeta:/app/data/raw/cbeta
      # 下面两行用于持久化数据库和用户数据，请勿修改
      - ./data/db:/app/data/db
      - ./data/user_data:/app/data/user_data
```

例如，如果你按第二步将 CBETA 放在了项目里的 `data/raw/cbeta`，就改为 `./data/raw/cbeta:/app/data/raw/cbeta`。如果放在 NAS 另一块硬盘上，就填绝对路径如 `/mnt/disk2/cbeta:/app/data/raw/cbeta`。

---

## 📍 第四步：一键运行

### 方案 A：在各类 NAS（群晖、绿联等）上运行
1. 打开 NAS 的 **Docker** 或 **容器管理 (Container Manager)** 应用。
2. 找到 **项目 (Projects)** / **Compose**，点击“新建项目”。
3. 命名为 `fa-yin`，**路径选择你在第一步建立的项目主目录**。
4. 系统将自动读取该目录下的 YAML 配置。点击 **启动/构建**。

### 方案 B：在 1Panel 等服务器面板上运行
1. 进入控制台的 **容器 -> 编排 (Compose)**。
2. 点击 **创建编排 -> 路径选择**。
3. 填入你在第一步建立的项目主目录下的 YAML 配置（例如 `/opt/1panel/docker/compose/fayin/docker-compose.yml`）。
4. 点击 **保存** 并启动。

### 方案 C：纯命令行运行 (Linux/VPS 极客)
确保你已安装 `docker` 与 `docker-compose` 插件：
```bash
cd /opt/fa-yin    # 切入项目主目录
docker compose up -d --build
```

---

## 🎉 验收与初次启动说明

启动后，访问浏览器：`http://你的设备局域网或公网IP:8400`。
*(VPS 用户别忘了在面板防火墙和云服务器安全组中放行 8400 端口！)*

**⚠️【首次启动必看】网页打不开、一直转圈、报 404？**
完全正常。这是法印的**“初始化 ETL 建库阶段”**。
程序必须在容器后台把你放进去的几万份 CBETA XML 文件扫描一遍，并构建出一个能支撑全文毫秒级检索的 SQLite 数据库文件（这也是本项目最大的核心价值）。

根据你设备的 CPU 性能：
- 在主流 VPS 或绿联 DX4600 等高性能机型上：大约需 **5 到 15 分钟**。
- 在性能极弱的 ARM 软路由或古董机器上：可能长达半小时。

你可以随时在容器详情页的**“日志”**控制台中查看构建进度。当你看到最后输出 `✅ 服务启动于 http://...:8400` 时，刷新网页，属于你个人的私有藏经阁就搭建完毕了。后续因任何原因重启容器，都属“秒开”。

---

## 🔄 升级版本与数据安全

核心原则：**Docker 容器怎么删都无所谓，只要你的文件夹在，数据就在。**

1. 发现 GitHub 上有了新代码，你只需将新代码覆盖替换掉主目录里的旧代码。
2. 保持你的 `data` 目录不要动。
3. 在面板里对这个项目**重新构建 (Rebuild)**。
4. 全新镜像启动后会自动读取外部挂载的 `data/user_data`。你的高亮笔记、自定义词典和书签列表都会像魔法一样原封不动地出现在新版本里。
