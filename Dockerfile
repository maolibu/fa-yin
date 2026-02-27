FROM python:3.13-slim

WORKDIR /app

# 系统依赖（lxml 编译需要）
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源代码
COPY src/ ./src/
COPY launcher.py .
COPY .env.example .

# 创建数据目录
RUN mkdir -p data/raw/cbeta data/db data/user_data/notes

# 暴露默认端口
EXPOSE 8002

# 默认命令（VPS 部署通常不需要浏览器）
CMD ["python", "launcher.py", "--no-browser"]
