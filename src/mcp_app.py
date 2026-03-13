"""
MCP 工具注册与集成模块

将所有 MCP 工具注册到 FastMCP 服务器，并提供挂载到 FastAPI 的方法。
"""

import time
from typing import Optional, List

from loguru import logger
from mcp.server.fastmcp import FastMCP

from src.tools.transcribe import TranscribeVideoTool
from src.tools.analyze import AnalyzeVideoFramesTool
from src.utils.config import config

# 创建 FastMCP 实例
mcp = FastMCP(
    "视频分析MCP服务",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    host="0.0.0.0",
)

# 共享工具实例（延迟初始化）
_transcribe_tool: Optional[TranscribeVideoTool] = None
_analyze_tool: Optional[AnalyzeVideoFramesTool] = None


def _get_transcribe_tool() -> TranscribeVideoTool:
    global _transcribe_tool
    if _transcribe_tool is None:
        _transcribe_tool = TranscribeVideoTool()
    return _transcribe_tool


def _get_analyze_tool() -> AnalyzeVideoFramesTool:
    global _analyze_tool
    if _analyze_tool is None:
        _analyze_tool = AnalyzeVideoFramesTool()
    return _analyze_tool


@mcp.tool()
async def transcribe_video(
    url: str,
    quality: str = "best",
    language: str = "zh",
) -> dict:
    """将在线视频转录为带时间戳的SRT字幕文本。

    自动完成：下载视频 → 提取音频 → 语音识别 → 生成SRT字幕。
    返回的 task_id 可传给 analyze_video_frames 复用已下载的视频，避免重复下载。

    支持平台：YouTube、Bilibili（B站）、抖音、西瓜视频等主流平台。

    Args:
        url: 视频页面URL，如 https://www.bilibili.com/video/BVxxxxxxx
        quality: 视频质量。best=最高画质，high=1080p，medium=720p，low=480p
        language: 音频语言。zh=中文，en=英文，ja=日语，ko=韩语
    """
    start_time = time.time()
    logger.info(f"[MCP] transcribe_video 调用: url={url}, quality={quality}, language={language}")

    # 参数验证
    if not url or not url.strip():
        logger.warning("[MCP] transcribe_video 参数错误: url 为空")
        return {"success": False, "error": "url 不能为空"}

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        logger.warning(f"[MCP] transcribe_video 参数错误: 无效的 URL 格式: {url}")
        return {"success": False, "error": "url 必须以 http:// 或 https:// 开头"}

    valid_qualities = ["best", "high", "medium", "low"]
    if quality not in valid_qualities:
        logger.warning(f"[MCP] transcribe_video 参数错误: 无效的 quality: {quality}")
        return {"success": False, "error": f"quality 必须是 {valid_qualities} 之一"}

    try:
        tool = _get_transcribe_tool()
        result = await tool.run(url=url, quality=quality, language=language)

        elapsed = time.time() - start_time
        logger.info(
            f"[MCP] transcribe_video 完成: success={result.success}, "
            f"task_id={result.task_id}, 耗时={elapsed:.1f}s"
        )

        response = {
            "success": result.success,
            "task_id": result.task_id,
        }
        if result.success:
            response.update({
                "content": result.srt_content,
                "duration": result.duration,
                "video_title": result.video_title,
            })
        else:
            response["error"] = result.error

        return response

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[MCP] transcribe_video 异常: {e}, 耗时={elapsed:.1f}s")
        return {"success": False, "error": f"服务内部错误: {str(e)}"}


@mcp.tool()
async def analyze_video_frames(
    timestamps: List[float],
    task_id: Optional[str] = None,
    video_path: Optional[str] = None,
    url: Optional[str] = None,
    analysis_type: str = "smart",
    custom_prompt: Optional[str] = None,
) -> dict:
    """提取视频指定时间点的画面并进行AI图像识别，返回每帧的内容描述。

    注意：本工具会对每一帧调用大模型图像识别，资源消耗较高，请谨慎使用。
    - 仅在文字转录无法满足需求、确实需要理解画面内容时才调用
    - 每次调用建议不超过5个时间点，优先选择最关键的几帧
    - 优先通过 transcribe_video 的字幕文本获取信息，不足时再用本工具补充

    典型用法：先用 transcribe_video 获取字幕和 task_id，根据字幕内容选择少量关键时间点，
    再用本工具分析对应画面。通过 task_id 复用已下载的视频，无需重复下载。

    视频来源（三选一，优先级从高到低）：
    1. task_id - 复用 transcribe_video 已下载的视频（推荐）
    2. video_path - 服务器上的本地视频文件路径
    3. url - 在线视频URL（会重新下载）

    Args:
        timestamps: 要分析的时间点列表，单位秒，建议不超过5个。如 [10.0, 60.0, 120.0]
        task_id: transcribe_video 返回的任务ID，用于复用已下载的视频
        video_path: 服务器本地视频文件的绝对路径
        url: 视频页面URL，仅在没有 task_id 和 video_path 时使用
        analysis_type: 识别侧重点。smart=自动判断，general=综合描述，detailed=详细描述，objects=物体检测，text=文字识别，scene=场景分析
        custom_prompt: 自定义识别提示词，覆盖 analysis_type。如"描述画面中人物的表情和动作"
    """
    start_time = time.time()
    source = task_id or video_path or url or "未指定"
    logger.info(
        f"[MCP] analyze_video_frames 调用: "
        f"timestamps={len(timestamps)}个, source={source}, type={analysis_type}"
    )

    # 参数验证
    if not timestamps:
        logger.warning("[MCP] analyze_video_frames 参数错误: timestamps 为空")
        return {"success": False, "error": "timestamps 不能为空"}

    for i, ts in enumerate(timestamps):
        if ts < 0:
            logger.warning(f"[MCP] analyze_video_frames 参数错误: timestamps[{i}]={ts} 不能为负数")
            return {"success": False, "error": f"timestamps[{i}] 不能为负数"}

    if not task_id and not video_path and not url:
        logger.warning("[MCP] analyze_video_frames 参数错误: 未指定视频来源")
        return {"success": False, "error": "必须提供 task_id、video_path 或 url 之一"}

    if url and not url.strip().startswith(("http://", "https://")):
        logger.warning(f"[MCP] analyze_video_frames 参数错误: 无效的 URL: {url}")
        return {"success": False, "error": "url 必须以 http:// 或 https:// 开头"}

    valid_types = ["general", "detailed", "objects", "text", "scene", "smart"]
    if analysis_type not in valid_types:
        logger.warning(f"[MCP] analyze_video_frames 参数错误: 无效的 analysis_type: {analysis_type}")
        return {"success": False, "error": f"analysis_type 必须是 {valid_types} 之一"}

    try:
        tool = _get_analyze_tool()
        result = await tool.run(
            timestamps=timestamps,
            task_id=task_id,
            video_path=video_path,
            url=url.strip() if url else None,
            analysis_type=analysis_type,
            custom_prompt=custom_prompt,
        )

        elapsed = time.time() - start_time
        logger.info(
            f"[MCP] analyze_video_frames 完成: success={result.success}, "
            f"task_id={result.task_id}, "
            f"{result.total_succeeded}/{result.total_requested} 成功, "
            f"耗时={elapsed:.1f}s"
        )

        response = {
            "success": result.success,
            "task_id": result.task_id,
            "total_requested": result.total_requested,
            "total_succeeded": result.total_succeeded,
        }
        if result.success:
            response["frames"] = [
                {
                    "index": f.index,
                    "timestamp": f.timestamp,
                    "image_url": f.image_url,
                    "description": f.description,
                    "error": f.error,
                }
                for f in result.frames
            ]
        else:
            response["error"] = result.error

        return response

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[MCP] analyze_video_frames 异常: {e}, 耗时={elapsed:.1f}s")
        return {"success": False, "error": f"服务内部错误: {str(e)}"}
