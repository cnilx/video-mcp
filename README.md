# 视频分析 MCP 服务

一个强大的 MCP HTTP API 服务，用于智能分析视频内容。支持视频下载、音频转录、智能抽帧、图像识别和内容总结。

## 核心功能

- 🎥 **多平台视频下载** - 支持 YouTube、B站、抖音等 1000+ 平台
- 🎙️ **语音转文本** - 使用阿里百炼 API 进行高精度语音识别
- 🖼️ **智能抽帧** - 基于音频语义智能提取关键视频帧
- 👁️ **图像识别** - 使用视觉语言模型深度理解画面内容
- 📝 **内容总结** - 综合音频和图像信息生成结构化总结

## 快速启动（Docker）

### 前置要求

- Docker 和 Docker Compose
- 阿里百炼 API 密钥（[获取地址](https://dashscope.console.aliyun.com/)）
- 阿里云 OSS 存储（[开通地址](https://oss.console.aliyun.com/)）
- 网络代理（用于下载 YouTube 等国外视频）

### 三步启动

**1. 克隆项目**
```bash
git clone https://github.com/yourusername/video-mcp.git
cd video-mcp
```

**2. 配置环境变量**
```bash
cd deploy
cp .env.example .env
```

编辑 `deploy/.env` 文件，填入必需配置：
```bash
# 服务认证密钥（必需，自定义，用于 Claude 连接）
API_KEY=your-api-key-here

# 阿里百炼 API 密钥（必需，用于语音识别和图像识别）
DASHSCOPE_API_KEY=your-dashscope-api-key

# 阿里云 OSS 配置（必需，用于存储处理文件）
OSS_ACCESS_KEY_ID=your-oss-access-key-id
OSS_ACCESS_KEY_SECRET=your-oss-access-key-secret
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
OSS_BUCKET_NAME=your-bucket-name

# 网络代理配置（必需，用于下载视频）
HTTP_PROXY=http://host.docker.internal:7890
HTTPS_PROXY=http://host.docker.internal:7890
NO_PROXY=localhost,127.0.0.1,host.docker.internal
```

**3. 一键部署**
```bash
./deploy.sh
```

脚本会自动完成：
- 停止旧容器
- 删除旧镜像
- 拉取最新代码
- 构建新镜像
- 启动服务

## 在 Claude 中配置

编辑 Claude Desktop 配置文件（`claude_desktop_config.json`），添加：

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

重启 Claude Desktop 即可使用。

### 配置文件位置

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

## 使用示例

在 Claude 中直接发送视频链接：

```
请帮我分析这个视频：https://www.youtube.com/watch?v=xxxxx
```

Claude 会自动：
1. 下载视频
2. 提取并转录音频
3. 分析内容，确定关键时间点
4. 提取关键帧并进行图像识别
5. 生成结构化总结

## 常用命令

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 更新服务
git pull
docker-compose down
docker build -t video-mcp:latest .
docker-compose up -d
```

## MCP 工具列表

本服务提供 2 个 MCP 工具：

1. **transcribe_video** - 视频转录为 SRT 字幕
   - 自动完成：下载视频 → 提取音频 → 语音识别 → 生成 SRT 字幕
   - 支持 YouTube、B站、抖音等主流平台
   - 返回带时间戳的字幕文本和 task_id

2. **analyze_video_frames** - 提取视频画面并进行 AI 图像识别
   - 提取指定时间点的视频帧
   - 使用视觉语言模型分析画面内容
   - 可复用 transcribe_video 的 task_id，无需重复下载视频
   - 支持多种识别类型：综合描述、文字识别、场景分析等

详细 API 文档请参见 [API文档.md](./docs/API文档.md)

## 技术栈

- **Python 3.14** - 主要编程语言
- **FastAPI** - 高性能 Web 框架
- **MCP Python SDK** - MCP 协议实现（HTTP transport）
- **yt-dlp** - 视频下载
- **ffmpeg** - 音视频处理
- **阿里百炼** - 语音识别和图像识别
- **Docker** - 容器化部署

## 项目结构

```
video-mcp/
├── src/                      # 源代码
│   ├── server.py            # FastAPI HTTP 服务入口
│   ├── mcp_app.py           # MCP 应用定义
│   ├── auth.py              # API Key 认证
│   ├── tools/               # MCP 工具定义
│   ├── core/                # 核心处理模块
│   └── utils/               # 工具函数
├── config/                   # 配置文件
├── deploy/                   # 部署配置
│   └── docker-compose.yml   # Docker Compose 配置
├── docs/                     # 文档
├── Dockerfile               # Docker 镜像
├── .env.example             # 环境变量模板
├── requirements.txt         # Python 依赖
└── README.md
```

## 文档

- [设计文档](./docs/设计文档.md) - 架构设计和技术选型
- [API文档](./docs/API文档.md) - 详细的工具接口说明
- [配置指南](./docs/配置指南.md) - 配置文件和 API 密钥设置
- [使用指南](./docs/使用指南.md) - 使用场景和最佳实践

## 常见问题

### 如何获取阿里百炼 API 密钥？

1. 访问 [阿里百炼控制台](https://dashscope.console.aliyun.com/)
2. 注册/登录阿里云账号
3. 开通百炼服务
4. 创建 API Key

### 如何更换端口？

编辑 `deploy/docker-compose.yml`，修改 `ports` 配置：
```yaml
ports:
  - "9000:8000"  # 将本地端口改为 9000
```

### 处理视频时超时怎么办？

在 Claude 配置中增加超时时间，或在 `config/config.json` 中调整 `server.timeout`。

### 如何查看详细日志？

```bash
cd deploy
docker-compose logs -f video-mcp
```

## 许可证

MIT License

## 致谢

感谢以下开源项目：
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 视频下载
- [ffmpeg](https://ffmpeg.org/) - 音视频处理
- [MCP](https://github.com/anthropics/mcp) - Model Context Protocol
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
