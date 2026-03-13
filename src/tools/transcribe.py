"""
视频转录工具
串联：下载视频 → 提取音频 → 上传OSS → 语音识别 → 生成SRT

输入视频 URL，返回 task_id + 转录文本 + SRT 结构化数据
"""

from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

from loguru import logger

from ..core.downloader import VideoDownloader, VideoQuality
from ..core.audio import AudioProcessor, AudioFormat, TranscriptionResult
from ..utils.oss import OSSUploader
from ..utils.workspace import WorkspaceManager
from ..utils.config import config


@dataclass
class SRTEntry:
    """SRT 条目"""
    index: int
    start_time: str  # HH:MM:SS,mmm
    end_time: str
    text: str


@dataclass
class TranscribeResult:
    """转录工具返回结果"""
    success: bool
    task_id: str = ""
    text: str = ""
    srt_content: str = ""
    srt_entries: List[SRTEntry] = field(default_factory=list)
    duration: float = 0.0
    video_title: Optional[str] = None
    error: Optional[str] = None


class TranscribeVideoTool:
    """视频转录工具 - MCP Tool 实现"""

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
        url: str,
        quality: str = "best",
        language: str = "zh",
    ) -> TranscribeResult:
        """
        执行视频转录

        Args:
            url: 视频 URL
            quality: 视频质量 (best/high/medium/low)
            language: 语言代码

        Returns:
            TranscribeResult
        """
        # 1. 创建工作空间
        ws = self.workspace_mgr.create()
        task_id = ws.workspace_id
        logger.info(f"[{task_id}] 开始视频转录: {url}")

        try:
            # 2. 下载视频
            logger.info(f"[{task_id}] 步骤 1/4: 下载视频")
            video_dir = str(self.workspace_mgr.get_path(task_id, "video"))
            downloader = VideoDownloader(
                output_dir=video_dir,
                max_file_size=config.download_max_file_size_gb * 1024 * 1024 * 1024,
            )

            video_quality = VideoQuality(quality) if quality in [q.value for q in VideoQuality] else VideoQuality.BEST
            download_result = await downloader.download(url, quality=video_quality)

            if not download_result.success:
                return TranscribeResult(
                    success=False,
                    task_id=task_id,
                    error=f"视频下载失败: {download_result.error}",
                )

            video_path = download_result.file_path
            logger.info(f"[{task_id}] 视频下载完成: {video_path}")

            # 3. 提取音频
            logger.info(f"[{task_id}] 步骤 2/4: 提取音频")
            audio_dir = str(self.workspace_mgr.get_path(task_id, "audio"))
            audio_output = str(Path(audio_dir) / "audio.mp3")

            audio_processor = AudioProcessor(
                api_key=config.dashscope_api_key,
                model=config.speech_model,
                language=language,
                oss_uploader=self.oss_uploader,
            )

            audio_path = await audio_processor.extract_audio(
                video_path=video_path,
                output_path=audio_output,
                audio_format=AudioFormat.MP3,
            )

            if not audio_path:
                return TranscribeResult(
                    success=False,
                    task_id=task_id,
                    error="音频提取失败",
                )

            logger.info(f"[{task_id}] 音频提取完成: {audio_path}")

            # 4. 语音识别（内部会上传 OSS）
            logger.info(f"[{task_id}] 步骤 3/4: 语音识别")
            transcription = await audio_processor.transcribe_audio(audio_path)

            if not transcription.success:
                return TranscribeResult(
                    success=False,
                    task_id=task_id,
                    error=f"语音识别失败: {transcription.error}",
                )

            logger.info(f"[{task_id}] 语音识别完成: {len(transcription.text)} 字符")

            # 5. 生成 SRT
            logger.info(f"[{task_id}] 步骤 4/4: 生成 SRT")
            srt_content = transcription.to_srt()
            srt_path = str(Path(str(self.workspace_mgr.get_path(task_id, "output"))) / "subtitle.srt")
            await audio_processor.save_srt(transcription, srt_path)

            # 构建 SRT 条目
            srt_entries = self._parse_srt_entries(transcription)

            logger.info(f"[{task_id}] 视频转录完成")

            return TranscribeResult(
                success=True,
                task_id=task_id,
                text=transcription.text,
                srt_content=srt_content,
                srt_entries=srt_entries,
                duration=transcription.duration,
                video_title=download_result.title,
            )

        except Exception as e:
            logger.error(f"[{task_id}] 视频转录异常: {str(e)}")
            return TranscribeResult(
                success=False,
                task_id=task_id,
                error=str(e),
            )

    def _parse_srt_entries(self, transcription: TranscriptionResult) -> List[SRTEntry]:
        """从转录结果中提取 SRT 条目"""
        entries = []
        counter = 1

        for segment in transcription.segments:
            if segment.sentences:
                for sentence in segment.sentences:
                    entries.append(SRTEntry(
                        index=counter,
                        start_time=TranscriptionResult._format_srt_time(sentence.begin_time),
                        end_time=TranscriptionResult._format_srt_time(sentence.end_time),
                        text=sentence.text,
                    ))
                    counter += 1
            else:
                entries.append(SRTEntry(
                    index=counter,
                    start_time=TranscriptionResult._format_srt_time(int(segment.start_time * 1000)),
                    end_time=TranscriptionResult._format_srt_time(int(segment.end_time * 1000)),
                    text=segment.text,
                ))
                counter += 1

        return entries
