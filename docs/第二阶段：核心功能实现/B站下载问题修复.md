# B站视频下载问题修复

## 问题描述

在使用 yt-dlp 下载 B站视频时遇到以下错误：

```
WARNING: [BiliBili] BV1x9PWzuEKc: Failed to parse JSON: Expecting value in '': line 1 column 1 (char 0)
[BiliBili] BV1x9PWzuEKc: Downloading wbi sign
ERROR: [BiliBili] 1x9PWzuEKc: BV1x9PWzuEKc: Failed to parse JSON (caused by JSONDecodeError("Expecting value in '': line 1 column 1 (char 0)"))
ERROR: [BiliBili] BV1x9PWzuEKc: Requested format is not available
```

## 问题原因

1. **yt-dlp 版本过旧**：旧版本 (2026.3.3) 的 B站 WBI 签名算法已失效，导致 JSON 解析失败
2. **格式选择问题**：代码中使用 `format: 'best'` 会尝试下载最高质量的视频（如 1080P 60帧），但这些格式需要 B站大会员权限
3. **缺少平台特定配置**：原代码中没有针对 B站的专用格式配置，导致格式选择失败

## 解决方案

### 1. 升级 yt-dlp 版本（关键）

```bash
pip install --upgrade yt-dlp
```

从 2026.3.3 升级到 2026.3.13，新版本修复了 B站 WBI 签名验证问题。

### 2. 添加 B站专用格式配置

在 `src/core/downloader.py:91-106` 的 `PLATFORM_FORMATS` 中添加 B站配置：

```python
'bilibili': {
    # B站格式选择 - 避免选择需要会员的格式
    VideoQuality.BEST: 'bestvideo[height<=1080][vcodec^=avc]+bestaudio/best[height<=1080]',
    VideoQuality.HIGH: 'bestvideo[height<=1080][vcodec^=avc]+bestaudio/best[height<=1080]',
    VideoQuality.MEDIUM: 'bestvideo[height<=720][vcodec^=avc]+bestaudio/best[height<=720]',
    VideoQuality.LOW: 'bestvideo[height<=480][vcodec^=avc]+bestaudio/best[height<=480]',
},
```

### 3. 更新 MCP 工具配置

在 MCP 工具中添加 Cookie 配置支持：

**src/tools/transcribe.py:87-92**
```python
downloader = VideoDownloader(
    output_dir=video_dir,
    max_file_size=config.download_max_file_size_gb * 1024 * 1024 * 1024,
    cookiefile=config.download_bilibili_cookie_file,  # 新增
)
```

**src/tools/analyze.py:222-226**
```python
downloader = VideoDownloader(
    output_dir=video_dir,
    max_file_size=config.download_max_file_size_gb * 1024 * 1024 * 1024,
    cookiefile=config.download_bilibili_cookie_file,  # 新增
)
```

### 4. 格式选择策略

- 使用 `[vcodec^=avc]` 过滤器选择 H.264 编码的视频（兼容性更好）
- 限制分辨率上限（`height<=1080`）避免选择需要会员的高帧率版本
- 使用 `bestvideo+bestaudio` 组合获取最佳质量

## 测试结果

修复后成功获取视频信息：
- ✓ WBI 签名验证通过（无 JSON 解析错误）
- ✓ 视频 BV1x9PWzuEKc 可以正常解析
- ✓ 格式选择成功，避开了需要会员的格式
- ✓ 视频时长：399.987秒

## 相关文件

- `src/core/downloader.py:91-106` - 平台格式配置
- `src/tools/transcribe.py:87-92` - 转录工具下载器配置
- `src/tools/analyze.py:222-226` - 帧分析工具下载器配置

## 注意事项

1. **保持 yt-dlp 更新**：B站的反爬虫机制会不断更新，建议定期升级 yt-dlp 到最新版本
2. 如果需要下载更高质量的视频，可以配置 Cookie 认证（使用 `cookies_from_browser` 或 `cookiefile` 参数）
3. 当前配置优先保证下载成功，而非追求最高画质
4. yt-dlp 版本：2026.3.13（已修复 WBI 签名问题）

## 修复时间

2026-03-17
