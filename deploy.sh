#!/bin/bash

# 视频MCP项目自动部署脚本
# 用途：停止容器、删除镜像、拉取代码、构建镜像、启动服务

set -e  # 遇到错误立即退出

echo "=========================================="
echo "开始部署 video-mcp 项目"
echo "=========================================="

# 获取脚本所在目录（项目根目录）
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy"

echo ""
echo "[1/5] 停止并删除容器..."
cd "$DEPLOY_DIR"
docker compose down

echo ""
echo "[2/5] 删除旧镜像..."
docker rmi video-mcp:latest || echo "镜像不存在或已删除"

echo ""
echo "[3/5] 拉取最新代码..."
cd "$PROJECT_ROOT"
git pull

echo ""
echo "[4/5] 构建新镜像..."
docker build -t video-mcp .

echo ""
echo "[5/5] 启动服务..."
cd "$DEPLOY_DIR"
docker compose up -d

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo ""
echo "查看服务状态: cd deploy && docker compose ps"
echo "查看日志: cd deploy && docker compose logs -f"