FROM python:3.13-slim

WORKDIR /app

# 系统依赖（lxml 编译需要）
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── 复制项目文件 ─────────────────────────────────────────────
# 启动脚本
COPY launcher.py .
COPY .env.example .

# 源代码
COPY src/ ./src/

# 内置数据（组字映射、默认收藏、偈颂、对照映射等）
COPY data/raw/cbeta_gaiji.json ./data/raw/cbeta_gaiji.json
COPY data/db/ ./data/db/

# 词典压缩包（首次启动时自动解压）
COPY data/dicts.tar.gz ./data/dicts.tar.gz

# 地图瓦片压缩包（首次启动时自动解压）
COPY data/tiles.tar.gz ./data/tiles.tar.gz

# 辅助工具（词典构建等）
COPY tools/ ./tools/

# Obsidian Vault 转换器
COPY obsidian_vault/ ./obsidian_vault/

# ─── 创建运行时数据目录 ──────────────────────────────────────
RUN mkdir -p data/raw/cbeta data/user_data/notes

# 暴露默认端口
EXPOSE 8400

# 默认命令（VPS 部署通常不需要浏览器）
CMD ["python", "launcher.py", "--no-browser"]
