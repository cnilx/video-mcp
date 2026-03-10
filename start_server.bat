@echo off
REM 视频分析 MCP 服务启动脚本 (Windows)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 启动服务
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 3600 --reload
