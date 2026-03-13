# 视频分析MCP服务 - API文档

## 概述

本文档详细说明了视频分析 MCP HTTP API 服务提供的所有工具接口。

## 服务架构

本服务基于 **MCP over HTTP/SSE** 协议，提供以下特性：

- **通信方式**：HTTP/SSE
- **认证方式**：API Key（Bearer Token）
- **数据格式**：JSON
- **处理模式**：同步处理（长超时）

## API 端点

### 基础信息

- **Base URL**: `http://your-host:8000`
- **MCP 端点**: `/mcp`
- **健康检查**: `/health`

### 认证

所有 MCP 请求需要在请求头中包含 API Key：

```http
Authorization: Bearer your-api-key-here
```

### Claude 配置示例

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

## 工具列表

1. [transcribe_video](#1-transcribe_video---视频语音转录) - 输入视频URL，返回语音转录结果
2. [analyze_video_frames](#2-analyze_video_frames---视频帧画面分析) - 根据时间戳分析视频帧画面内容

---

## 1. transcribe_video - 视频语音转录

### 功能描述
输入视频URL，自动完成下载、音频提取、语音识别，返回带句子级时间戳的转录文本和SRT内容。

### 内部流程
下载视频 → 提取音频 → 上传OSS → 语音识别（Qwen-ASR）→ 生成SRT

### 支持的平台
- YouTube
- Bilibili（B站）
- 抖音
- 以及yt-dlp支持的1000+其他平台

### 输入参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| url | string | 是 | 视频链接URL |

### 返回结果

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "视频标题",
  "duration": 300.5,
  "text": "完整的转录文本内容...",
  "segments": [
    {
      "start": 0.0,
      "end": 4.24,
      "text": "很多人把原始资本积累失败理解成三个词：不努力、认知低、不会赚钱。",
      "sentences": [
        {
          "text": "很多人把原始资本积累失败理解成三个词：不努力、认知低、不会赚钱。",
          "begin_time": 0,
          "end_time": 4240
        }
      ]
    },
    {
      "start": 4.4,
      "end": 11.04,
      "text": "但如果你真正观察现实社会，会发现一个更冷静的事实...",
      "sentences": [
        {
          "text": "但如果你真正观察现实社会，会发现一个更冷静的事实...",
          "begin_time": 4400,
          "end_time": 11040
        }
      ]
    }
  ],
  "srt_content": "1\n00:00:00,000 --> 00:00:04,240\n很多人把原始资本积累失败...\n\n2\n00:00:04,400 --> 00:00:11,040\n但如果你真正观察现实社会...\n",
  "sentence_count": 8,
  "character_count": 235
}
```

### 字段说明

- **task_id**: 任务ID，可供 analyze_video_frames 复用已下载的视频
- **title**: 视频标题
- **duration**: 视频时长（秒）
- **text**: 完整的转录文本
- **segments**: 分段文本数组，每段包含句子级时间戳
  - **start**: 开始时间（秒）
  - **end**: 结束时间（秒）
  - **text**: 该段文本内容
  - **sentences**: 句子级详细信息
    - **text**: 句子文本
    - **begin_time**: 开始时间（毫秒）
    - **end_time**: 结束时间（毫秒）
- **srt_content**: SRT 字幕格式的完整内容
- **sentence_count**: 句子总数
- **character_count**: 字符总数

### 使用示例

```python
# 转录 YouTube 视频
result = transcribe_video(
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
)

# 转录 B站视频
result = transcribe_video(
    url="https://www.bilibili.com/video/BV1xx411c7mD"
)

# 获取 task_id 供后续帧分析使用
task_id = result["task_id"]
```

### SRT 字幕示例

返回的 `srt_content` 字段格式：

```srt
1
00:00:00,000 --> 00:00:04,240
很多人把原始资本积累失败理解成三个词：不努力、认知低、不会赚钱。

2
00:00:04,400 --> 00:00:11,040
但如果你真正观察现实社会，会发现一个更冷静的事实：原始资本积累从来不是赚钱能力问题，而是能否进入资源网络的问题。
```

### 性能指标

| 音频时长 | 处理时间（含下载） | 句子数（参考） |
|---------|-------------------|--------------|
| 30秒    | 5-10秒            | 8-10句       |
| 5分钟   | 15-30秒           | 80-100句     |
| 30分钟  | 1-3分钟           | 400-500句    |
| 60分钟  | 3-8分钟           | 800-1000句   |

### 错误处理

| 错误类型 | 说明 | 处理方式 |
|----------|------|----------|
| NetworkError | 网络连接失败 | 自动重试3次 |
| UnsupportedPlatform | 不支持的平台 | 返回错误信息 |
| VideoNotAvailable | 视频不可用 | 返回详细原因 |
| InsufficientSpace | 磁盘空间不足 | 返回空间需求 |
| TranscriptionError | 语音识别失败 | 返回API错误详情 |

---

## 2. analyze_video_frames - 视频帧画面分析

### 功能描述
根据指定的时间戳列表，从视频中提取帧并使用 Qwen-VL 进行图像识别和内容理解。

### 内部流程
获取视频（从工作空间/本地路径/URL）→ 提取帧 → 上传OSS → 图像识别（Qwen-VL）

### 输入参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| timestamps | array[float] | 是 | - | 时间戳列表（秒） |
| prompt | string | 否 | "请提取图片中的所有信息内容，包括：文字、标题、正文、图表数据、代码片段、公式、表格等。" | 分析提示词 |
| task_id | string | 否 | - | 来自 transcribe_video 的任务ID（优先使用） |
| video_path | string | 否 | - | 本地视频文件路径（备选） |
| url | string | 否 | - | 视频链接URL（降级方案） |

**视频来源优先级**：`task_id` > `video_path` > `url`（三者至少提供一个）

### 返回结果

```json
{
  "analyses": [
    {
      "timestamp": 10.5,
      "content": "# Python 函数定义示例\n\n这是一个 Python 代码编辑器的截图，显示了以下代码：\n\n```python\ndef main():\n    print('Hello World')\n```\n\n这是一个简单的主函数定义，功能是打印 \"Hello World\" 字符串。"
    },
    {
      "timestamp": 45.2,
      "content": "PPT 页面标题：微服务架构设计\n\n主要内容：\n1. 服务拆分原则\n2. API 网关设计\n3. 服务间通信方式..."
    }
  ],
  "total_analyzed": 2
}
```

### 字段说明

- **analyses**: 分析结果数组
  - **timestamp**: 对应的视频时间戳（秒）
  - **content**: Qwen-VL 提取的完整信息内容（自由格式文本）
- **total_analyzed**: 分析的帧总数

### 使用示例

```python
# 典型用法：配合 transcribe_video 使用
transcript = transcribe_video(url="https://www.youtube.com/watch?v=example")
task_id = transcript["task_id"]

# 根据转录内容选择关键时间点，使用 task_id 复用已下载的视频
result = analyze_video_frames(
    task_id=task_id,
    timestamps=[10.5, 45.2, 120.8]
)

# 使用自定义提示词（PPT 内容分析）
result = analyze_video_frames(
    task_id=task_id,
    timestamps=[10.5, 45.2],
    prompt="""这是一张 PPT 截图，请提取：
1. 标题和主要内容
2. 所有文字信息
3. 图表数据和趋势
4. 关键要点"""
)

# 使用本地视频文件
result = analyze_video_frames(
    video_path="/path/to/local/video.mp4",
    timestamps=[5.0, 15.0, 30.0]
)

# 降级方案：直接使用 URL（会重新下载）
result = analyze_video_frames(
    url="https://www.youtube.com/watch?v=example",
    timestamps=[10.5, 45.2]
)
```
### 技术细节

- 使用阿里百炼 Qwen-VL 多模态模型
- 支持图像理解、OCR、物体识别、场景分析
- OpenAI 兼容接口
- 支持自定义提示词引导分析方向
- 可批量处理多张图片

### 提示词建议

根据不同的分析需求，可以使用不同的提示词：

**通用信息提取（默认）**：
```
请提取图片中的所有信息内容，包括：文字、标题、正文、图表数据、代码片段、公式、表格等。
```

**PPT/演示文稿提取**：
```
这是一张 PPT 截图，请提取：
1. 标题和主要内容
2. 所有文字信息（包括正文、列表、注释）
3. 图表数据和趋势
4. 关键要点和结论
保持原有的层次结构和格式。
```

**代码截图提取**：
```
请提取图片中的代码：
1. 编程语言
2. 完整的代码内容（保持原有格式和缩进）
3. 代码功能说明
4. 关键逻辑和算法
```

**图表/数据可视化提取**：
```
请提取这张图表的信息：
1. 图表类型（柱状图、折线图、饼图等）
2. 标题、图例、坐标轴标签
3. 所有数据值和单位
4. 数据趋势和关键发现
```

---

## 完整工作流程示例

```python
# 1. 转录视频语音
transcript = transcribe_video(
    url="https://www.youtube.com/watch?v=example"
)

# 2. 获取 task_id 和转录文本
task_id = transcript["task_id"]
text = transcript["text"]
segments = transcript["segments"]

# 3. AI 分析转录内容，确定关键时间点
# （这一步由 Claude 完成）
key_timestamps = [10.5, 45.2, 120.8]

# 4. 分析关键帧画面（使用 task_id 复用已下载的视频）
analysis = analyze_video_frames(
    task_id=task_id,
    timestamps=key_timestamps,
    prompt="请提取图片中的文字、图表、代码等信息内容。"
)

# 5. 综合分析结果
# （由 Claude 基于转录文本和图像分析生成最终报告）
```

## 错误码参考

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| E001 | 无效的URL | 检查视频链接格式 |
| E002 | 文件不存在 | 确认文件路径正确 |
| E003 | API密钥无效 | 检查配置文件中的API密钥 |
| E004 | 配额超限 | 等待配额重置或升级服务 |
| E005 | 网络超时 | 检查网络连接 |
| E006 | 磁盘空间不足 | 清理磁盘空间 |
| E007 | 不支持的格式 | 使用支持的格式 |
| E008 | 处理超时 | 增加超时时间或分段处理 |

## 性能建议

1. **批量处理**: 多个帧的分析可以批量调用以提高效率
2. **并发限制**: 建议同时处理的视频数量不超过3个
3. **缓存利用**: 相同视频的重复分析会使用缓存结果
4. **资源清理**: 定期清理过期的工作目录以释放空间
