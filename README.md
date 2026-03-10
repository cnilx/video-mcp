# 视频分析MCP服务

一个强大的 MCP HTTP API 服务，用于智能分析视频内容，支持视频下载、音频转录、智能抽帧、图像识别和内容总结。

## 功能特性

- 🎥 **多平台视频下载** - 支持YouTube、B站、抖音等1000+平台
- 🎙️ **语音转文本** - 使用云服务API进行高精度语音识别
- 🖼️ **智能抽帧** - 基于音频语义智能提取关键视频帧
- 👁️ **图像识别** - 结合专门API和视觉语言模型深度理解画面
- 📝 **内容总结** - 综合音频和图像信息生成结构化总结
- 🐳 **Docker 部署** - 一键部署，支持本地、局域网、云服务器
- 🔐 **API 认证** - 简单的 API Key 认证机制

## 架构特点

- **HTTP/SSE 传输**：基于 MCP 协议的 HTTP transport，Claude 通过 URL 直接连接
- **容器化部署**：Docker 封装所有依赖，部署简单
- **灵活配置**：支持环境变量和配置文件混合配置
- **同步处理**：长超时支持，适合视频处理场景

## 快速开始

### 开发环境

**系统要求**：
- Python 3.11+
- 至少 5GB 可用磁盘空间

**启动步骤**：

1. **克隆项目**
```bash
git clone https://github.com/yourusername/video-mcp.git
cd video-mcp
```

2. **创建虚拟环境**
```bash
python -m venv venv
source venv/Scripts/activate  # Linux/Mac
# 或
venv\Scripts\activate.bat     # Windows
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入以下配置：
# - API_KEY: 服务认证密钥（自定义）
# - DASHSCOPE_API_KEY: 阿里百炼 API 密钥（语音识别 + 图像识别）
```

5. **配置服务（可选）**
```bash
cp config/config.example.json config/config.json
# 根据需要调整配置（端口、超时时间等）
```

6. **启动服务**
```bash
# Linux/Mac
./start_server.sh

# Windows
start_server.bat

# 或直接运行
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000 --reload
```

7. **验证服务**
```bash
# 访问健康检查端点
curl http://localhost:8000/health

# 或运行测试脚本
./test_server.sh
```

### Docker 部署

**系统要求**：
- Docker 和 Docker Compose
- 至少 5GB 可用磁盘空间

**部署步骤**：

1. **克隆项目**
```bash
git clone https://github.com/yourusername/video-mcp.git
cd video-mcp
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入以下配置：
# - API_KEY: 服务认证密钥（自定义）
# - DASHSCOPE_API_KEY: 阿里百炼 API 密钥（语音识别 + 图像识别）
```

3. **配置服务（可选）**
```bash
cp config/config.example.json config/config.json
# 根据需要调整配置（端口、超时时间等）
```

4. **启动服务**
```bash
docker-compose up -d
```

5. **验证服务**
```bash
curl http://localhost:8000/health
```

### 在 Claude 中配置

编辑 Claude 配置文件，添加：

**本地部署**：
```json
{
  "mcpServers": {
    "video-analyzer": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

**局域网部署**：
```json
{
  "mcpServers": {
    "video-analyzer": {
      "url": "http://192.168.1.100:8000/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

**云服务器部署**：
```json
{
  "mcpServers": {
    "video-analyzer": {
      "url": "https://your-domain.com/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

重启 Claude Desktop 即可使用。

## 使用示例

### 分析YouTube视频

```
用户：请帮我分析这个视频 https://www.youtube.com/watch?v=xxxxx

Claude会自动：
1. 下载视频
2. 提取并转录音频
3. 分析内容，确定关键时间点
4. 提取关键帧并进行图像识别
5. 生成结构化总结
```

### 提取会议纪要

```
用户：请分析这个会议录像，提取讨论要点和决策

Claude会生成：
- 会议时长和参与人数
- 主要议题和讨论内容
- 关键决策和行动项
- 重要时刻的截图
```

### 分析教学视频

```
用户：请分析这个编程教程，提取代码示例

Claude会提供：
- 教程章节结构
- 所有代码示例（带时间戳）
- 关键概念讲解
- 练习建议
```

## MCP工具

本服务提供5个MCP工具：

1. **download_video** - 下载在线视频
2. **extract_audio** - 提取音频
3. **transcribe_audio** - 语音转文本
4. **extract_frames** - 提取视频帧
5. **analyze_frames** - 图像识别

详细API文档请参见 [API文档.md](./docs/API文档.md)

## 部署选项

### 本地部署
适合个人使用，Claude Desktop 和服务在同一台机器上。

```bash
docker-compose up -d
```

配置 URL：`http://localhost:8000/mcp`

### 局域网部署
适合团队使用，服务部署在局域网服务器上。

```bash
# 在服务器上
docker-compose up -d

# 如需修改端口
vim docker-compose.yml  # 修改 ports 配置
```

配置 URL：`http://服务器IP:8000/mcp`

### 云服务器部署
适合远程访问，建议配置 HTTPS。

```bash
# 在云服务器上
docker-compose up -d

# 配置 Nginx 反向代理（推荐）
# 配置 Let's Encrypt SSL 证书
```

配置 URL：`https://your-domain.com/mcp`

## 配置说明

### 环境变量（.env）

```bash
# API 服务认证（必需）
API_KEY=your-secure-api-key-here

# 阿里百炼 API Key（必需）- 用于语音识别和图像识别
DASHSCOPE_API_KEY=your-dashscope-api-key
```

### 配置文件（config/config.json）

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "timeout": 3600
  },
  "speech": {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3-asr-flash",
    "enable_itn": false,
    "language": null
  },
  "vision": {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3-vl-flash",
    "max_tokens": 2000,
    "temperature": 0.7
  },
  "workspace": {
    "base_dir": "/data/workspaces",
    "auto_cleanup_days": 7
  },
  "download": {
    "default_quality": "best",
    "max_file_size_gb": 5
  }
}
```

详细配置说明请参见 [配置指南.md](./docs/配置指南.md)

## 项目结构

```
video-mcp/
├── src/
│   ├── server.py             # FastAPI HTTP 服务入口
│   ├── auth.py               # API Key 认证
│   ├── tools/                # MCP工具定义
│   ├── core/                 # 核心处理模块
│   └── utils/                # 工具函数
├── tests/                    # 测试文件
├── config/                   # 配置文件
├── docs/                     # 文档
├── Dockerfile                # Docker 镜像
├── docker-compose.yml        # Docker Compose 配置
├── .env.example              # 环境变量模板
├── requirements.txt          # Python依赖
└── README.md
```

## 技术栈

- **Python 3.11** - 主要编程语言
- **FastAPI** - 高性能 Web 框架
- **MCP Python SDK** - MCP 协议实现（HTTP transport）
- **yt-dlp** - 视频下载
- **ffmpeg** - 音视频处理
- **Docker** - 容器化部署
- **uvicorn** - ASGI 服务器

## 文档

- [设计文档](./docs/设计文档.md) - 架构设计和技术选型
- [API文档](./docs/API文档.md) - 详细的工具接口说明
- [配置指南](./docs/配置指南.md) - 配置文件和API密钥设置
- [使用指南](./docs/使用指南.md) - 使用场景和最佳实践

## 常见问题

### 如何更换端口？
编辑 `docker-compose.yml`，修改 `ports` 配置：
```yaml
ports:
  - "9000:8000"  # 将本地端口改为 9000
```

### 如何查看日志？
```bash
docker-compose logs -f
```

### 如何重启服务？
```bash
docker-compose restart
```

### 如何更新服务？
```bash
git pull
docker-compose down
docker-compose build
docker-compose up -d
```

### 处理视频时超时怎么办？
在 Claude 配置中增加超时时间，或在 `config/config.json` 中调整 `server.timeout`。

## 开发计划

- [ ] 架构设计（API 服务模式）
- [ ] 实现 HTTP 服务和认证
- [ ] 实现核心功能
- [ ] 添加单元测试
- [ ] Docker 镜像构建
- [ ] 支持更多语音识别服务
- [ ] 支持更多图像识别服务
- [ ] 添加缓存机制
- [ ] 性能优化
- [ ] Web 管理界面（未来）

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

## 联系方式

- 项目主页：https://github.com/yourusername/video-mcp
- 问题反馈：https://github.com/yourusername/video-mcp/issues

## 致谢

感谢以下开源项目：
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/)
- [MCP](https://github.com/anthropics/mcp)
- [FastAPI](https://fastapi.tiangolo.com/)
