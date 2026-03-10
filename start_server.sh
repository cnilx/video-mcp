#!/bin/bash

# 视频分析 MCP 服务启动脚本

# 激活虚拟环境
source venv/Scripts/activate

# 启动服务
python -m uvicorn src.server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --timeout-keep-alive 3600 \
    --reload
