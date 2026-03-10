# HTTP 服务实现说明

## 概述

本文档说明了视频分析 MCP 服务的 HTTP 服务层实现，包括 FastAPI 基础服务、API Key 认证、健康检查和 MCP 协议集成。

## 实现的功能

### 1. FastAPI 基础服务 (src/server.py)

**核心特性**：
- 基于 FastAPI 的异步 HTTP 服务
- 支持长超时（默认 3600 秒）
- 完整的生命周期管理
- 统一的异常处理
- 结构化日志输出

**主要端点**：
- `GET /health` - 健康检查端点
- `POST /mcp` - MCP 协议 HTTP 端点
- `GET /mcp/sse` - MCP 协议 SSE 端点（待实现）

**配置**：
- 服务地址：通过配置文件设置（默认 0.0.0.0:8000）
- 超时时间：可配置（默认 3600 秒）
- 日志级别：INFO

### 2. API Key 认证中间件 (src/auth.py)

**认证方式**：
- Bearer Token 认证
- 请求头格式：`Authorization: Bearer <api_key>`

**认证逻辑**：
- 健康检查端点 `/health` 不需要认证
- 其他端点需要提供有效的 API Key
- API Key 通过环境变量 `API_KEY` 配置
- 认证失败返回 401 Unauthorized

**开发模式**：
- 如果未配置 `API_KEY` 环境变量，则跳过认证检查
- 仅用于开发和测试，生产环境必须配置

### 3. 配置管理 (src/utils/config.py)

**配置来源**：
- 环境变量（敏感信息）：`.env` 文件
  - `API_KEY` - 服务认证密钥
  - `DASHSCOPE_API_KEY` - 阿里百炼 API 密钥
- 配置文件（非敏感配置）：`config/config.json`
  - 服务器配置
  - 语音识别配置
  - 图像识别配置
  - 工作目录配置
  - 下载配置

**配置加载**：
- 自动加载 `.env` 文件
- 支持通过 `CONFIG_PATH` 环境变量指定配置文件路径
- 配置文件不存在时使用默认配置
- 启动时验证必需的配置项

### 4. CORS 配置

**当前配置**：
- 允许所有来源（`allow_origins=["*"]`）
- 允许所有方法
- 允许所有请求头
- 允许携带凭据

**生产环境建议**：
- 限制 `allow_origins` 为具体的域名
- 根据实际需求调整其他 CORS 设置

### 5. 错误处理

**HTTP 异常处理**：
- 统一的错误响应格式
- 包含错误码和错误信息
- 记录警告日志

**通用异常处理**：
- 捕获所有未处理的异常
- 返回 500 错误
- 记录详细的错误日志（包含堆栈跟踪）

## 使用方法

### 启动服务

**方式 1：使用启动脚本**

Linux/Mac:
```bash
chmod +x start_server.sh
./start_server.sh
```

Windows:
```bash
start_server.bat
```

**方式 2：直接运行**

```bash
# 激活虚拟环境
source venv/Scripts/activate  # Linux/Mac
# 或
venv\Scripts\activate.bat     # Windows

# 启动服务
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000 --reload
```

**方式 3：使用 Python 模块**

```bash
python -m src.server
```

### 配置环境变量

创建 `.env` 文件：

```bash
# 复制示例文件
cp .env.example .env

# 编辑配置
vim .env
```

`.env` 文件内容：

```bash
# API 服务认证（必需）
API_KEY=your-secure-api-key-here

# 阿里百炼 API Key（必需）
DASHSCOPE_API_KEY=your-dashscope-api-key
```

### 配置服务参数

编辑 `config/config.json`：

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "timeout": 3600
  },
  "workspace": {
    "base_dir": "/data/workspaces",
    "auto_cleanup_days": 7
  }
}
```

## API 测试

### 健康检查

```bash
curl http://localhost:8000/health
```

响应：
```json
{
  "status": "healthy",
  "service": "video-mcp",
  "version": "1.0.0",
  "config": {
    "api_key_enabled": true,
    "dashscope_enabled": true,
    "workspace_dir": "/data/workspaces",
    "timeout": 3600
  }
}
```

### MCP 端点测试

**无认证（应该失败）**：
```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"test"}'
```

响应：
```json
{
  "error": {
    "code": 403,
    "message": "Not authenticated"
  }
}
```

**带认证（应该成功）**：
```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key-here" \
  -d '{"jsonrpc":"2.0","id":1,"method":"test"}'
```

响应：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "message": "MCP SDK 集成待实现"
  }
}
```

## 日志输出

服务启动时的日志输出：

```
2026-03-10 19:49:39 | INFO     | src.server:lifespan:27 - ============================================================
2026-03-10 19:49:39 | INFO     | src.server:lifespan:28 - 视频分析 MCP 服务启动中...
2026-03-10 19:49:39 | INFO     | src.server:lifespan:29 - 服务地址: http://0.0.0.0:8000
2026-03-10 19:49:39 | INFO     | src.server:lifespan:30 - MCP 端点: http://0.0.0.0:8000/mcp
2026-03-10 19:49:39 | INFO     | src.server:lifespan:31 - 健康检查: http://0.0.0.0:8000/health
2026-03-10 19:49:39 | INFO     | src.server:lifespan:32 - 超时设置: 3600 秒
2026-03-10 19:49:39 | INFO     | src.server:lifespan:33 - 工作目录: /data/workspaces
2026-03-10 19:49:39 | INFO     | src.server:lifespan:35 - ✓ API Key 认证已启用
2026-03-10 19:49:39 | INFO     | src.server:lifespan:40 - ✓ 阿里百炼 API Key 已配置
2026-03-10 19:49:39 | INFO     | src.server:lifespan:45 - ============================================================
```

## 下一步工作

### 待实现功能

1. **MCP SDK 集成**
   - 集成 MCP Python SDK
   - 实现 MCP 协议处理
   - 注册 MCP 工具

2. **SSE 支持**
   - 实现 SSE 端点
   - 支持流式响应

3. **工具实现**
   - 实现 5 个 MCP 工具
   - 集成核心处理模块

### 优化建议

1. **安全性**
   - 生产环境限制 CORS 来源
   - 添加请求频率限制
   - 添加请求大小限制

2. **性能**
   - 添加请求缓存
   - 优化日志输出
   - 添加性能监控

3. **可观测性**
   - 添加 Prometheus 指标
   - 添加分布式追踪
   - 添加结构化日志

## 文件清单

```
src/
├── server.py           # FastAPI 主服务
├── auth.py            # API Key 认证中间件
└── utils/
    └── config.py      # 配置管理

start_server.sh        # Linux/Mac 启动脚本
start_server.bat       # Windows 启动脚本
```

## 总结

HTTP 服务层已经完成基础实现，包括：

✅ FastAPI 基础服务
✅ API Key 认证中间件
✅ 健康检查端点
✅ MCP 协议端点（框架）
✅ CORS 配置
✅ 错误处理
✅ 配置管理
✅ 日志输出

服务已经可以正常启动和响应请求，下一步需要集成 MCP SDK 并实现具体的工具功能。
