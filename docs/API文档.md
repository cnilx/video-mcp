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

1. [download_video](#1-download_video---下载视频) - 下载在线视频
2. [extract_audio](#2-extract_audio---提取音频) - 从视频中提取音频
3. [transcribe_audio](#3-transcribe_audio---语音转文本) - 将音频转录为文本
4. [extract_frames](#4-extract_frames---提取视频帧) - 在指定时间点提取视频帧
5. [analyze_frames](#5-analyze_frames---图像识别) - 分析视频帧内容

---

## 1. download_video - 下载视频

### 功能描述
从支持的视频平台下载视频文件到本地工作目录。

### 支持的平台
- YouTube
- Bilibili（B站）
- 抖音
- 以及yt-dlp支持的1000+其他平台

### 输入参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| url | string | 是 | 视频链接URL |

**配置说明**：视频质量由配置文件 `config.json` 中的 `download.default_quality` 控制。

### 返回结果

```json
{
  "video_path": "/data/workspaces/uuid/video.mp4",
  "title": "视频标题",
  "duration": 300.5,
  "format": "mp4",
  "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_size": 52428800,
  "resolution": "1920x1080"
}
```

**注意**：`video_path` 是容器内路径，仅用于后续工具调用，Claude 无法直接访问。

### 字段说明

- **video_path**: 下载后的视频文件完整路径
- **title**: 视频标题
- **duration**: 视频时长（秒）
- **format**: 视频格式
- **workspace_id**: 工作目录ID，用于后续操作
- **file_size**: 文件大小（字节）
- **resolution**: 视频分辨率

### 使用示例

```python
# 下载YouTube视频
result = download_video(
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
)

# 下载B站视频
result = download_video(
    url="https://www.bilibili.com/video/BV1xx411c7mD"
)
```

### 错误处理

| 错误类型 | 说明 | 处理方式 |
|----------|------|----------|
| NetworkError | 网络连接失败 | 自动重试3次 |
| UnsupportedPlatform | 不支持的平台 | 返回错误信息 |
| VideoNotAvailable | 视频不可用 | 返回详细原因 |
| InsufficientSpace | 磁盘空间不足 | 返回空间需求 |

---

## 2. extract_audio - 提取音频

### 功能描述
从视频文件中提取音频轨道，并转换为适合语音识别的格式。

### 输入参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| video_path | string | 是 | 视频文件路径 |

**配置说明**：音频格式由配置文件 `config.json` 中的 `processing.audio_format` 控制。

### 返回结果

```json
{
  "audio_path": "/data/workspaces/uuid/audio.wav",
  "duration": 300.5,
  "sample_rate": 16000,
  "channels": 1,
  "bit_depth": 16,
  "file_size": 9600000
}
```

### 字段说明

- **audio_path**: 提取后的音频文件路径
- **duration**: 音频时长（秒）
- **sample_rate**: 采样率（Hz）
- **channels**: 声道数（1=单声道，2=立体声）
- **bit_depth**: 位深度
- **file_size**: 文件大小（字节）

### 使用示例

```python
# 提取音频
result = extract_audio(
    video_path="/path/to/video.mp4"
)
```

### 技术细节

- 自动转换为配置文件指定的格式（默认：16kHz单声道WAV）
- 使用ffmpeg进行音频处理
- 保持原始音频质量

---

## 3. transcribe_audio - 语音转文本

### 功能描述
使用阿里百炼 Qwen-ASR 模型将音频文件转录为带时间戳的文本。

### 输入参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| audio_path | string | 是 | 音频文件路径 |

**配置说明**：语言识别由配置文件 `config.json` 中的 `speech.language` 控制（null 为自动检测）。

### 返回结果

```json
{
  "text": "这是完整的转录文本内容...",
  "segments": [
    {
      "start": 0.0,
      "end": 5.2,
      "text": "这是第一句话"
    },
    {
      "start": 5.2,
      "end": 10.8,
      "text": "这是第二句话"
    }
  ],
  "language": "zh",
  "confidence": 0.95,
  "word_count": 150
}
```

### 字段说明

- **text**: 完整的转录文本
- **segments**: 分段文本数组，每段包含时间戳
  - **start**: 开始时间（秒）
  - **end**: 结束时间（秒）
  - **text**: 该段文本内容
- **language**: 检测到的语言
- **confidence**: 识别置信度（0-1）
- **word_count**: 词数统计

### 使用示例

```python
# 语音转文本（自动检测语言）
result = transcribe_audio(
    audio_path="/data/workspaces/uuid/audio.wav"
)
```

### 技术细节

- 使用阿里百炼 Qwen-ASR 模型（qwen3-asr-flash）
- OpenAI 兼容接口
- 支持 20+ 语种自动识别
- 返回带时间戳的分段文本
- 可选启用 ITN（逆文本标准化）

---

## 4. extract_frames - 提取视频帧

### 功能描述
在指定的时间点从视频中提取静态图像帧。

### 输入参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| video_path | string | 是 | 视频文件路径 |
| timestamps | array[float] | 是 | 时间戳列表（秒） |

**配置说明**：图片格式由配置文件 `config.json` 中的 `processing.frame_format` 控制。

### 返回结果

```json
{
  "frames": [
    {
      "timestamp": 10.5,
      "path": "/data/workspaces/uuid/frames/frame_10.5.jpg",
      "width": 1920,
      "height": 1080,
      "file_size": 245760
    },
    {
      "timestamp": 45.2,
      "path": "/data/workspaces/uuid/frames/frame_45.2.jpg",
      "width": 1920,
      "height": 1080,
      "file_size": 238592
    }
  ],
  "total_frames": 2
}
```

### 字段说明

- **frames**: 提取的帧数组
  - **timestamp**: 时间戳（秒）
  - **path**: 图片文件路径
  - **width**: 图片宽度（像素）
  - **height**: 图片高度（像素）
  - **file_size**: 文件大小（字节）
- **total_frames**: 提取的帧总数

### 使用示例

```python
# 提取多个时间点的帧
result = extract_frames(
    video_path="/path/to/video.mp4",
    timestamps=[10.5, 45.2, 120.8, 180.3]
)
```

### 技术细节

- 使用ffmpeg精确定位时间点
- 保持原始视频分辨率
- 支持批量提取

---

## 5. analyze_frames - 图像识别

### 功能描述
使用阿里百炼 Qwen-VL 模型对提取的视频帧进行图像识别和内容理解。

### 输入参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| frame_paths | array[string] | 是 | - | 图片路径列表 |
| prompt | string | 否 | "请提取图片中的所有信息内容，包括：文字、标题、正文、图表数据、代码片段、公式、表格等。" | 分析提示词 |

### 返回结果

```json
{
  "analyses": [
    {
      "frame_path": "/data/workspaces/uuid/frames/frame_10.5.jpg",
      "timestamp": 10.5,
      "content": "# Python 函数定义示例\n\n这是一个 Python 代码编辑器的截图，显示了以下代码：\n\n```python\ndef main():\n    print('Hello World')\n```\n\n这是一个简单的主函数定义，功能是打印 \"Hello World\" 字符串。"
    }
  ],
  "total_analyzed": 1
}
```

### 字段说明

- **analyses**: 分析结果数组
  - **frame_path**: 图片路径（容器内路径）
  - **timestamp**: 对应的视频时间戳（秒）
  - **content**: Qwen-VL 提取的完整信息内容（自由格式文本）
- **total_analyzed**: 分析的帧总数

### 使用示例

```python
# 基本分析（使用默认提示词）
result = analyze_frames(
    frame_paths=["/data/workspaces/uuid/frames/frame_10.5.jpg"]
)

# PPT 内容分析
result = analyze_frames(
    frame_paths=["/data/workspaces/uuid/frames/frame_10.5.jpg"],
    prompt="""这是一张 PPT 截图，请提取：
1. 标题和主要内容
2. 所有文字信息
3. 图表数据和趋势
4. 关键要点
保持原有的层次结构。"""
)

# 代码截图分析
result = analyze_frames(
    frame_paths=["/data/workspaces/uuid/frames/frame_10.5.jpg"],
    prompt="""请识别图片中的代码内容：
1. 编程语言
2. 完整的代码内容（保持格式）
3. 代码功能说明
4. 关键逻辑"""
)

# 图表数据分析
result = analyze_frames(
    frame_paths=["/data/workspaces/uuid/frames/frame_10.5.jpg"],
    prompt="""请分析这张图表：
1. 图表类型
2. 标题和坐标轴标签
3. 数据值和趋势
4. 关键发现和结论"""
)

# 批量分析多帧
result = analyze_frames(
    frame_paths=[
        "/data/workspaces/uuid/frames/frame_10.5.jpg",
        "/data/workspaces/uuid/frames/frame_45.2.jpg",
        "/data/workspaces/uuid/frames/frame_120.8.jpg"
    ],
    prompt="请提取图片中的文字、图表、代码等信息内容。"
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

**图表/数据可视化提取**：
```
请提取这张图表的信息：
1. 图表类型（柱状图、折线图、饼图等）
2. 标题、图例、坐标轴标签
3. 所有数据值和单位
4. 数据趋势和关键发现
```

**代码截图提取**：
```
请提取图片中的代码：
1. 编程语言
2. 完整的代码内容（保持原有格式和缩进）
3. 代码功能说明
4. 关键逻辑和算法
```

**教学内容提取**：
```
请提取教学内容：
1. 讲解的主题和标题
2. 屏幕上的所有文字和代码
3. 演示的步骤和流程
4. 关键知识点和公式
```

**技术文档提取**：
```
请提取文档内容：
1. 标题、章节、小节
2. 所有正文内容
3. 代码示例和配置
4. 图表、表格、公式
5. 重点内容和注意事项
```

**会议/演讲内容提取**：
```
请提取会议内容：
1. 屏幕/投影上的标题和文字
2. PPT 内容和要点
3. 图表和数据
4. 关键结论和决策
```

**产品界面提取**：
```
请提取产品界面信息：
1. 界面标题和菜单
2. 所有可见的文字和标签
3. 数据和数值
4. 功能说明和提示
```

---

## 完整工作流程示例

```python
# 1. 下载视频
download_result = download_video(
    url="https://www.youtube.com/watch?v=example"
)

# 2. 提取音频
audio_result = extract_audio(
    video_path=download_result["video_path"]
)

# 3. 语音转文本
transcript = transcribe_audio(
    audio_path=audio_result["audio_path"]
)

# 4. 分析转录文本，确定关键时间点
# （这一步由 Claude 完成）
key_timestamps = [10.5, 45.2, 120.8]

# 5. 提取关键帧
frames_result = extract_frames(
    video_path=download_result["video_path"],
    timestamps=key_timestamps
)

# 6. 分析图像内容
analysis_result = analyze_frames(
    frame_paths=[frame["path"] for frame in frames_result["frames"]],
    prompt="请提取图片中的文字、图表、代码等信息内容。"
)

# 7. 综合分析结果
# （由 Claude 基于转录文本和图像分析生成最终报告）
```

# 4. 根据转录内容决定关键时间点（由AI分析）
key_timestamps = [10.5, 45.2, 120.8]

# 5. 提取关键帧
frames_result = extract_frames(
    video_path=download_result["video_path"],
    timestamps=key_timestamps
)

# 6. 分析图像内容
analysis_result = analyze_frames(
    frame_paths=[frame["path"] for frame in frames_result["frames"]],
    prompt="请提取图片中的文字、图表、代码等信息内容。"
)

# 7. 综合分析结果
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
