"""
视频帧分析工具
串联：获取视频 → 提取帧 → 上传OSS → 图像识别

输入 timestamps + task_id/video_path/url，返回帧分析结果
视频来源优先级：task_id > video_path > url
"""

from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

from loguru import logger

from ..core.downloader import VideoDownloader, VideoQuality
from ..core.frames import FrameExtractor, FrameConfig, FrameInfo
from ..core.vision import VisionAnalyzer, AnalysisType
from ..utils.oss import OSSUploader
from ..utils.workspace import WorkspaceManager
from ..utils.config import config


@dataclass
class FrameAnalysis:
    """单帧分析结果"""
    index: int
    timestamp: float
    image_url: str = ""
    description: str = ""
    error: Optional[str] = None


@dataclass
class AnalyzeFramesResult:
    """帧分析工具返回结果"""
    success: bool
    task_id: str = ""
    frames: List[FrameAnalysis] = field(default_factory=list)
    total_requested: int = 0
    total_succeeded: int = 0
    error: Optional[str] = None


class AnalyzeVideoFramesTool:
    """视频帧分析工具 - MCP Tool 实现"""

    def __init__(
        self,
        workspace_manager: Optional[WorkspaceManager] = None,
        oss_uploader: Optional[OSSUploader] = None,
    ):
        self.workspace_mgr = workspace_manager or WorkspaceManager(
            base_dir=config.workspace_base_dir,
            max_size_gb=config.workspace_max_size_gb,
            auto_cleanup_days=config.workspace_auto_cleanup_days,
        )
        self.oss_uploader = oss_uploader or OSSUploader(
            endpoint=config.oss_endpoint,
            bucket_name=config.oss_bucket_name,
        )

    async def run(
        self,
        timestamps: List[float],
        task_id: Optional[str] = None,
        video_path: Optional[str] = None,
        url: Optional[str] = None,
        analysis_type: str = "smart",
        custom_prompt: Optional[str] = None,
    ) -> AnalyzeFramesResult:
        """
        执行视频帧分析

        Args:
            timestamps: 时间戳列表（秒）
            task_id: 已有任务 ID（复用工作空间中的视频）
            video_path: 本地视频文件路径
            url: 视频 URL（需要下载）
            analysis_type: 分析类型 (general/detailed/objects/text/scene/smart)
            custom_prompt: 自定义提示词

        Returns:
            AnalyzeFramesResult
        """
        if not timestamps:
            return AnalyzeFramesResult(
                success=False,
                error="timestamps 不能为空",
            )

        # 解析视频来源，优先级：task_id > video_path > url
        resolved_video, resolved_task_id, error = await self._resolve_video(
            task_id, video_path, url
        )
        if error:
            return AnalyzeFramesResult(
                success=False,
                task_id=resolved_task_id,
                total_requested=len(timestamps),
                error=error,
            )

        logger.info(f"[{resolved_task_id}] 开始帧分析: {len(timestamps)} 个时间戳")

        try:
            # 1. 提取帧
            logger.info(f"[{resolved_task_id}] 步骤 1/2: 提取视频帧")
            frames_dir = str(self.workspace_mgr.get_path(resolved_task_id, "frames"))

            frame_extractor = FrameExtractor(
                config=FrameConfig(),
                oss_uploader=self.oss_uploader,
            )

            extraction = await frame_extractor.extract_frames(
                video_path=resolved_video,
                output_dir=frames_dir,
                timestamps=timestamps,
            )

            if not extraction.success:
                return AnalyzeFramesResult(
                    success=False,
                    task_id=resolved_task_id,
                    total_requested=len(timestamps),
                    error=f"帧提取失败: {extraction.error}",
                )

            logger.info(f"[{resolved_task_id}] 帧提取完成: {extraction.total_extracted}/{len(timestamps)}")

            # 2. 图像识别
            logger.info(f"[{resolved_task_id}] 步骤 2/2: 图像识别")
            vision = VisionAnalyzer(
                api_key=config.dashscope_api_key,
                base_url=config.vision_base_url,
                model=config.vision_model,
                max_tokens=config.vision_max_tokens,
                temperature=config.vision_temperature,
                oss_uploader=self.oss_uploader,
            )

            a_type = AnalysisType(analysis_type) if analysis_type in [t.value for t in AnalysisType] else AnalysisType.SMART
            batch_result = await vision.analyze_frames(
                frame_infos=extraction.frames,
                analysis_type=a_type,
                custom_prompt=custom_prompt,
            )

            # 3. 组装结果
            frame_analyses = []
            for i, frame in enumerate(extraction.frames):
                analysis = FrameAnalysis(
                    index=frame.index,
                    timestamp=frame.timestamp,
                    image_url=frame.oss_url,
                )
                if i < len(batch_result.results):
                    r = batch_result.results[i]
                    if r.success:
                        analysis.description = r.description
                    else:
                        analysis.error = r.error
                frame_analyses.append(analysis)

            succeeded = sum(1 for f in frame_analyses if f.description and not f.error)
            logger.info(f"[{resolved_task_id}] 帧分析完成: {succeeded}/{len(timestamps)} 成功")

            return AnalyzeFramesResult(
                success=succeeded > 0,
                task_id=resolved_task_id,
                frames=frame_analyses,
                total_requested=len(timestamps),
                total_succeeded=succeeded,
            )

        except Exception as e:
            logger.error(f"[{resolved_task_id}] 帧分析异常: {str(e)}")
            return AnalyzeFramesResult(
                success=False,
                task_id=resolved_task_id,
                total_requested=len(timestamps),
                error=str(e),
            )

    async def _resolve_video(
        self,
        task_id: Optional[str],
        video_path: Optional[str],
        url: Optional[str],
    ) -> tuple[Optional[str], str, Optional[str]]:
        """
        解析视频来源

        Returns:
            (video_file_path, task_id, error)
        """
        # 优先级 1: task_id - 从已有工作空间获取视频
        if task_id:
            try:
                video_dir = self.workspace_mgr.get_path(task_id, "video")
                video_files = list(video_dir.glob("*.*"))
                video_files = [f for f in video_files if f.suffix.lower() in ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv')]
                if video_files:
                    return str(video_files[0]), task_id, None
                return None, task_id, f"工作空间 {task_id} 中未找到视频文件"
            except FileNotFoundError:
                return None, task_id, f"工作空间 {task_id} 不存在"

        # 优先级 2: video_path - 使用本地视频文件
        if video_path:
            if not Path(video_path).exists():
                return None, "", f"视频文件不存在: {video_path}"
            ws = self.workspace_mgr.create()
            return video_path, ws.workspace_id, None

        # 优先级 3: url - 下载视频
        if url:
            ws = self.workspace_mgr.create()
            tid = ws.workspace_id
            video_dir = str(self.workspace_mgr.get_path(tid, "video"))

            downloader = VideoDownloader(
                output_dir=video_dir,
                max_file_size=config.download_max_file_size_gb * 1024 * 1024 * 1024,
            )
            result = await downloader.download(url)

            if not result.success:
                return None, tid, f"视频下载失败: {result.error}"
            return result.file_path, tid, None

        return None, "", "必须提供 task_id、video_path 或 url 之一"
