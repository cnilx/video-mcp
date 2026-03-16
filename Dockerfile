# ============================================
# 视频分析 MCP 服务 - Dockerfile
# ============================================
# 多阶段构建：减小最终镜像体积
# 基础镜像：Python 3.14-slim (Debian bookworm)
# ============================================

# ---------- 阶段1：构建依赖 ----------
FROM python:3.14-slim AS builder

# 复制宿主机 APT 源配置
COPY ./sources.list /etc/apt/sources.list

WORKDIR /build

# 安装构建依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 安装 Python 依赖到独立目录（排除测试依赖）
RUN pip install --no-cache-dir --prefix=/install \
    $(grep -v '^#' requirements.txt | grep -v '^$' | grep -v 'pytest')

# ---------- 阶段2：运行时镜像 ----------
FROM python:3.14-slim

LABEL maintainer="video-mcp"
LABEL description="视频分析 MCP 服务"

# 安装运行时依赖：ffmpeg + yt-dlp
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl && \
    pip install --no-cache-dir yt-dlp && \
    apt-get purge -y --auto-remove curl && \
    rm -rf /var/lib/apt/lists/*

# 从构建阶段复制 Python 依赖
COPY --from=builder /install /usr/local

WORKDIR /app

# 创建非 root 用户
RUN groupadd -r mcp && \
    useradd -r -g mcp -d /app -s /sbin/nologin mcp

# 创建数据目录并设置权限
RUN mkdir -p /data/workspaces && \
    chown -R mcp:mcp /data

# 复制应用代码和配置
COPY src/ ./src/
COPY config/config.example.json ./config/config.json

# 设置目录权限
RUN chown -R mcp:mcp /app

# 切换到非 root 用户
USER mcp

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONFIG_PATH=/app/config/config.json

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://:8000/health')" || exit 1

# 启动服务
CMD ["python", "-m", "uvicorn", "src.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--timeout-keep-alive", "3600"]
