"""
视频帧处理模块
根据时间戳列表从视频中提取帧图片，上传到 OSS，返回结构化结果

特性:
- 根据指定时间戳提取视频帧
- 支持 JPEG/PNG/WebP 格式输出
- 可选缩放控制
- 并发提取 + 批量 OSS 上传
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum

import ffmpeg
from loguru import logger

from ..utils.oss import OSSUploader


class ImageFormat(str, Enum):
    """图片格式枚举"""
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"


@dataclass
class FrameConfig:
    """帧提取配置"""
    image_format: ImageFormat = ImageFormat.JPEG
    quality: int = 85                    # JPEG/WebP 质量 1-100
    max_width: Optional[int] = None      # 最大宽度（等比缩放）
    max_height: Optional[int] = None     # 最大高度（等比缩放）
    max_concurrent: int = 4              # 并发提取数


@dataclass
class FrameInfo:
    """单帧信息"""
    index: int                           # 序号
    timestamp: float                     # 秒
    file_path: str                       # 本地路径
    oss_url: str = ""                    # OSS 公网 URL
    width: int = 0
    height: int = 0
    file_size: int = 0


@dataclass
class ExtractionResult:
    """帧提取结果"""
    success: bool
    frames: List[FrameInfo] = field(default_factory=list)
    total_requested: int = 0
    total_extracted: int = 0
    video_duration: float = 0.0
    error: Optional[str] = None


class FrameExtractor:
    """视频帧提取器"""

    def __init__(
        self,
        config: Optional[FrameConfig] = None,
        oss_uploader: Optional[OSSUploader] = None,
    ):
        self.config = config or FrameConfig()
        self.oss_uploader = oss_uploader

    # === 公开方法 ===

    async def extract_frames(
        self,
        video_path: str,
        output_dir: str,
        timestamps: List[float],
    ) -> ExtractionResult:
        """
        根据时间戳列表提取帧，上传 OSS，返回结果

        Args:
            video_path: 视频文件路径
            output_dir: 帧图片输出目录
            timestamps: 时间戳列表（秒）

        Returns:
            ExtractionResult
        """
        try:
            video_path_obj = Path(video_path)
            if not video_path_obj.exists():
                return ExtractionResult(
                    success=False,
                    total_requested=len(timestamps),
                    error=f"视频文件不存在: {video_path}",
                )

            # 获取视频时长
            duration = await self._get_video_duration(video_path)
            if duration <= 0:
                return ExtractionResult(
                    success=False,
                    total_requested=len(timestamps),
                    error="无法获取视频时长",
                )

            # 过滤超出视频时长的时间戳
            valid_timestamps = []
            for ts in timestamps:
                if ts < 0 or ts > duration:
                    logger.warning(f"时间戳 {ts:.2f}s 超出视频时长 {duration:.2f}s，已跳过")
                else:
                    valid_timestamps.append(ts)

            if not valid_timestamps:
                return ExtractionResult(
                    success=False,
                    total_requested=len(timestamps),
                    video_duration=duration,
                    error="所有时间戳均超出视频时长",
                )

            # 创建输出目录
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # 批量提取
            result = await self._extract_batch(video_path, output_dir, valid_timestamps)
            result.total_requested = len(timestamps)
            result.video_duration = duration

            # 上传到 OSS
            if result.frames and self.oss_uploader and self.oss_uploader.bucket:
                await self._upload_frames_to_oss(result.frames)

            return result

        except Exception as e:
            logger.error(f"帧提取失败: {str(e)}")
            return ExtractionResult(
                success=False,
                total_requested=len(timestamps),
                error=str(e),
            )

    # === 内部方法 ===

    async def _extract_single_frame(
        self,
        video_path: str,
        timestamp: float,
        output_path: str,
    ) -> Optional[FrameInfo]:
        """提取单帧"""
        try:
            stream = ffmpeg.input(video_path, ss=timestamp)

            # 缩放滤镜
            if self.config.max_width or self.config.max_height:
                w = self.config.max_width or -1
                h = self.config.max_height or -1
                stream = ffmpeg.filter(
                    stream, 'scale', w, h,
                    force_original_aspect_ratio='decrease',
                )

            # 输出参数
            output_kwargs = {'vframes': 1}
            fmt = self.config.image_format

            if fmt == ImageFormat.JPEG:
                output_kwargs['qscale:v'] = self._quality_to_qscale(self.config.quality)
            elif fmt == ImageFormat.WEBP:
                output_kwargs['quality'] = self.config.quality
            # PNG 无损，不需要质量参数

            stream = ffmpeg.output(stream, output_path, **output_kwargs)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.run(stream, overwrite_output=True, quiet=True),
            )

            output_file = Path(output_path)
            if not output_file.exists():
                logger.warning(f"帧提取后文件不存在: {output_path}")
                return None

            # 获取图片尺寸
            probe = ffmpeg.probe(output_path)
            video_stream = next(
                (s for s in probe['streams'] if s['codec_type'] == 'video'), None
            )
            width = int(video_stream['width']) if video_stream else 0
            height = int(video_stream['height']) if video_stream else 0

            return FrameInfo(
                index=0,  # 由调用方设置
                timestamp=timestamp,
                file_path=str(output_file.absolute()),
                width=width,
                height=height,
                file_size=output_file.stat().st_size,
            )

        except ffmpeg.Error as e:
            logger.error(f"帧提取失败 @{timestamp:.2f}s: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"帧提取失败 @{timestamp:.2f}s: {str(e)}")
            return None

    async def _extract_batch(
        self,
        video_path: str,
        output_dir: str,
        timestamps: List[float],
    ) -> ExtractionResult:
        """并发批量提取帧"""
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        ext = self.config.image_format.value

        async def _extract_with_sem(idx: int, ts: float) -> Optional[FrameInfo]:
            async with semaphore:
                output_path = str(Path(output_dir) / f"frame_{idx:04d}_{ts:.2f}s.{ext}")
                frame = await self._extract_single_frame(video_path, ts, output_path)
                if frame:
                    frame.index = idx
                return frame

        logger.info(f"开始批量提取 {len(timestamps)} 帧 (并发={self.config.max_concurrent})")

        tasks = [
            _extract_with_sem(i, ts)
            for i, ts in enumerate(timestamps)
        ]
        results = await asyncio.gather(*tasks)

        frames = [f for f in results if f is not None]
        frames.sort(key=lambda f: f.index)

        success = len(frames) > 0
        logger.info(f"帧提取完成: {len(frames)}/{len(timestamps)} 成功")

        return ExtractionResult(
            success=success,
            frames=frames,
            total_extracted=len(frames),
        )

    async def _upload_frames_to_oss(self, frames: List[FrameInfo]) -> None:
        """批量上传帧到 OSS"""
        logger.info(f"开始上传 {len(frames)} 帧到 OSS")
        loop = asyncio.get_event_loop()

        for frame in frames:
            try:
                url = await loop.run_in_executor(
                    None,
                    lambda fp=frame.file_path: self.oss_uploader.upload_file(
                        fp, folder="frames"
                    ),
                )
                if url:
                    frame.oss_url = url
                else:
                    logger.warning(f"帧 {frame.index} 上传失败")
            except Exception as e:
                logger.error(f"帧 {frame.index} 上传异常: {str(e)}")

        uploaded = sum(1 for f in frames if f.oss_url)
        logger.info(f"OSS 上传完成: {uploaded}/{len(frames)}")

    @staticmethod
    async def _get_video_duration(video_path: str) -> float:
        """获取视频时长（秒）"""
        try:
            loop = asyncio.get_event_loop()
            probe = await loop.run_in_executor(
                None, lambda: ffmpeg.probe(video_path)
            )
            return float(probe['format'].get('duration', 0))
        except Exception as e:
            logger.error(f"获取视频时长失败: {str(e)}")
            return 0.0

    @staticmethod
    def _quality_to_qscale(quality: int) -> int:
        """将 1-100 质量值转换为 ffmpeg qscale (1-31, 1=最高)"""
        quality = max(1, min(100, quality))
        return max(1, int(31 - (quality / 100) * 30))
