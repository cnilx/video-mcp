"""
音频处理模块
使用 ffmpeg 进行音频提取和格式转换
集成阿里百炼 Qwen-ASR 进行语音转文本

特性:
- 从视频中提取音频
- 音频格式转换（支持 mp3, wav, flac 等）
- 音频采样率调整
- 语音转文本（支持长音频分段转录）
- 自动处理大文件分段
"""

import os
import asyncio
import time
import json
import math
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

import ffmpeg
from loguru import logger
import dashscope
import requests

from ..utils.oss import OSSUploader


class AudioFormat(str, Enum):
    """音频格式枚举"""
    MP3 = "mp3"
    WAV = "wav"
    FLAC = "flac"
    AAC = "aac"
    OGG = "ogg"


class SampleRate(int, Enum):
    """音频采样率枚举"""
    SR_8000 = 8000
    SR_16000 = 16000
    SR_22050 = 22050
    SR_44100 = 44100
    SR_48000 = 48000


@dataclass
class AudioInfo:
    """音频信息"""
    duration: float  # 秒
    sample_rate: int
    channels: int
    codec: str
    bitrate: Optional[int] = None
    file_size: int = 0


@dataclass
class SentenceTimestamp:
    """句子时间戳"""
    text: str
    begin_time: int  # 毫秒
    end_time: int  # 毫秒


@dataclass
class TranscriptionSegment:
    """转录片段"""
    text: str
    start_time: float  # 秒
    end_time: float  # 秒
    duration: float  # 秒
    sentences: List[SentenceTimestamp] = None  # 句子级别时间戳

    def __post_init__(self):
        if self.sentences is None:
            self.sentences = []


@dataclass
class TranscriptionResult:
    """转录结果"""
    success: bool
    text: str = ""
    segments: List[TranscriptionSegment] = None
    duration: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if self.segments is None:
            self.segments = []

    def to_srt(self) -> str:
        """转换为 SRT 字幕格式"""
        srt_lines = []
        counter = 1

        for segment in self.segments:
            if segment.sentences:
                # 如果有句子级别的时间戳，使用句子
                for sentence in segment.sentences:
                    # 转换时间格式
                    start_ms = sentence.begin_time
                    end_ms = sentence.end_time

                    start_time = self._format_srt_time(start_ms)
                    end_time = self._format_srt_time(end_ms)

                    # SRT 格式
                    srt_lines.append(str(counter))
                    srt_lines.append(f"{start_time} --> {end_time}")
                    srt_lines.append(sentence.text)
                    srt_lines.append("")  # 空行

                    counter += 1
            else:
                # 如果没有句子级别的时间戳，使用分段时间
                start_ms = int(segment.start_time * 1000)
                end_ms = int(segment.end_time * 1000)

                start_time = self._format_srt_time(start_ms)
                end_time = self._format_srt_time(end_ms)

                # SRT 格式
                srt_lines.append(str(counter))
                srt_lines.append(f"{start_time} --> {end_time}")
                srt_lines.append(segment.text)
                srt_lines.append("")  # 空行

                counter += 1

        return "\n".join(srt_lines)

    @staticmethod
    def _format_srt_time(milliseconds: int) -> str:
        """格式化为 SRT 时间格式 HH:MM:SS,mmm"""
        seconds = milliseconds // 1000
        ms = milliseconds % 1000
        minutes = seconds // 60
        seconds = seconds % 60
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


class AudioProcessor:
    """音频处理器"""

    # 支持的音频格式
    SUPPORTED_FORMATS = [fmt.value for fmt in AudioFormat]

    # 默认转录参数
    DEFAULT_SEGMENT_DURATION = 120  # 2分钟分段
    MAX_FILE_SIZE_MB = 10  # 单个文件最大 10MB

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen3-asr-flash-filetrans",
        language: str = "zh",
        oss_uploader: Optional[OSSUploader] = None,
    ):
        """
        初始化音频处理器

        Args:
            api_key: 阿里百炼 API Key
            model: 语音识别模型（默认使用 qwen3-asr-flash-filetrans）
            language: 语言代码（zh, en, ja, ko 等）
            oss_uploader: OSS 上传器实例（用于上传音频文件）
        """
        self.api_key = api_key
        self.model = model
        self.language = language
        self.oss_uploader = oss_uploader

        # 设置 API Key（未提供时仍可使用音频提取等不依赖 API 的功能）
        if self.api_key:
            dashscope.api_key = self.api_key

        # 如果未提供 OSS 上传器，创建一个
        if self.oss_uploader is None:
            self.oss_uploader = OSSUploader()
            if not self.oss_uploader.bucket:
                logger.warning("OSS 未配置，使用 filetrans 模型时需要 OSS 支持")

    async def get_audio_info(self, audio_path: str) -> Optional[AudioInfo]:
        """
        获取音频文件信息

        Args:
            audio_path: 音频文件路径

        Returns:
            音频信息，失败返回 None
        """
        try:
            probe = ffmpeg.probe(audio_path)
            audio_stream = next(
                (s for s in probe['streams'] if s['codec_type'] == 'audio'),
                None
            )

            if not audio_stream:
                logger.error(f"未找到音频流: {audio_path}")
                return None

            file_size = Path(audio_path).stat().st_size

            return AudioInfo(
                duration=float(probe['format'].get('duration', 0)),
                sample_rate=int(audio_stream.get('sample_rate', 0)),
                channels=int(audio_stream.get('channels', 0)),
                codec=audio_stream.get('codec_name', 'unknown'),
                bitrate=int(probe['format'].get('bit_rate', 0)) if probe['format'].get('bit_rate') else None,
                file_size=file_size,
            )

        except ffmpeg.Error as e:
            logger.error(f"获取音频信息失败: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"获取音频信息失败: {str(e)}")
            return None

    async def extract_audio(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        audio_format: AudioFormat = AudioFormat.MP3,
        sample_rate: Optional[SampleRate] = None,
        audio_bitrate: str = "128k",
    ) -> Optional[str]:
        """
        从视频中提取音频

        Args:
            video_path: 视频文件路径
            output_path: 输出音频文件路径，None 则自动生成
            audio_format: 音频格式
            sample_rate: 采样率，None 则保持原始采样率
            audio_bitrate: 音频比特率

        Returns:
            输出文件路径，失败返回 None
        """
        try:
            video_path = Path(video_path)
            if not video_path.exists():
                logger.error(f"视频文件不存在: {video_path}")
                return None

            # 生成输出路径
            if output_path is None:
                output_path = video_path.with_suffix(f".{audio_format.value}")
            else:
                output_path = Path(output_path)

            logger.info(f"开始提取音频: {video_path} -> {output_path}")

            # 构建 ffmpeg 命令
            stream = ffmpeg.input(str(video_path))

            # 构建输出参数
            output_kwargs = {
                'format': audio_format.value,
                'audio_bitrate': audio_bitrate,
            }

            # 添加编解码器
            if audio_format == AudioFormat.MP3:
                output_kwargs['acodec'] = 'libmp3lame'

            # 添加采样率（如果指定）
            if sample_rate:
                output_kwargs['ar'] = sample_rate.value

            stream = ffmpeg.output(stream, str(output_path), vn=None, **output_kwargs)

            # 在线程池中执行（避免阻塞）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.run(stream, overwrite_output=True, quiet=True)
            )

            logger.info(f"音频提取成功: {output_path}")
            return str(output_path)

        except ffmpeg.Error as e:
            logger.error(f"音频提取失败: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"音频提取失败: {str(e)}")
            return None

    async def convert_audio(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        audio_format: AudioFormat = AudioFormat.MP3,
        sample_rate: Optional[SampleRate] = None,
        audio_bitrate: str = "128k",
    ) -> Optional[str]:
        """
        转换音频格式

        Args:
            input_path: 输入音频文件路径
            output_path: 输出音频文件路径，None 则自动生成
            audio_format: 目标音频格式
            sample_rate: 目标采样率，None 则保持原始采样率
            audio_bitrate: 音频比特率

        Returns:
            输出文件路径，失败返回 None
        """
        try:
            input_path = Path(input_path)
            if not input_path.exists():
                logger.error(f"音频文件不存在: {input_path}")
                return None

            # 生成输出路径
            if output_path is None:
                output_path = input_path.with_suffix(f".{audio_format.value}")
            else:
                output_path = Path(output_path)

            logger.info(f"开始转换音频: {input_path} -> {output_path}")

            # 构建 ffmpeg 命令
            stream = ffmpeg.input(str(input_path))
            stream = ffmpeg.output(
                stream,
                str(output_path),
                acodec='libmp3lame' if audio_format == AudioFormat.MP3 else None,
                audio_bitrate=audio_bitrate,
                ar=sample_rate.value if sample_rate else None,
                format=audio_format.value,
            )

            # 在线程池中执行
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.run(stream, overwrite_output=True, quiet=True)
            )

            logger.info(f"音频转换成功: {output_path}")
            return str(output_path)

        except ffmpeg.Error as e:
            logger.error(f"音频转换失败: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"音频转换失败: {str(e)}")
            return None

    async def adjust_sample_rate(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        sample_rate: SampleRate = SampleRate.SR_16000,
    ) -> Optional[str]:
        """
        调整音频采样率

        Args:
            input_path: 输入音频文件路径
            output_path: 输出音频文件路径，None 则覆盖原文件
            sample_rate: 目标采样率

        Returns:
            输出文件路径，失败返回 None
        """
        try:
            input_path = Path(input_path)
            if not input_path.exists():
                logger.error(f"音频文件不存在: {input_path}")
                return None

            # 生成输出路径
            if output_path is None:
                output_path = input_path.with_stem(f"{input_path.stem}_resampled")
            else:
                output_path = Path(output_path)

            logger.info(f"开始调整采样率: {input_path} -> {sample_rate.value}Hz")

            # 构建 ffmpeg 命令
            stream = ffmpeg.input(str(input_path))
            stream = ffmpeg.output(
                stream,
                str(output_path),
                ar=sample_rate.value,
            )

            # 在线程池中执行
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.run(stream, overwrite_output=True, quiet=True)
            )

            logger.info(f"采样率调整成功: {output_path}")
            return str(output_path)

        except ffmpeg.Error as e:
            logger.error(f"采样率调整失败: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"采样率调整失败: {str(e)}")
            return None

    async def _split_audio(
        self,
        audio_path: str,
        segment_duration: int,
        output_dir: Optional[str] = None,
    ) -> List[str]:
        """
        分割音频文件

        Args:
            audio_path: 音频文件路径
            segment_duration: 分段时长（秒）
            output_dir: 输出目录，None 则使用音频文件所在目录

        Returns:
            分段文件路径列表
        """
        try:
            audio_path = Path(audio_path)
            if output_dir is None:
                output_dir = audio_path.parent / f"{audio_path.stem}_segments"
            else:
                output_dir = Path(output_dir)

            output_dir.mkdir(parents=True, exist_ok=True)

            # 获取音频时长
            info = await self.get_audio_info(str(audio_path))
            if not info:
                return []

            total_duration = info.duration
            num_segments = math.ceil(total_duration / segment_duration)

            logger.info(f"开始分割音频: 总时长 {total_duration:.2f}s，分为 {num_segments} 段")

            segment_files = []
            for i in range(num_segments):
                start_time = i * segment_duration
                output_file = output_dir / f"segment_{i:03d}.mp3"

                # 构建 ffmpeg 命令
                stream = ffmpeg.input(str(audio_path), ss=start_time, t=segment_duration)
                stream = ffmpeg.output(stream, str(output_file), acodec='copy')

                # 执行分割
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda s=stream: ffmpeg.run(s, overwrite_output=True, quiet=True)
                )

                if output_file.exists():
                    segment_files.append(str(output_file))
                    logger.debug(f"分段 {i+1}/{num_segments} 完成: {output_file}")

            logger.info(f"音频分割完成: {len(segment_files)} 个分段")
            return segment_files

        except Exception as e:
            logger.error(f"音频分割失败: {str(e)}")
            return []

    async def transcribe_audio(
        self,
        audio_path: str,
        auto_split: bool = False,  # 默认不分片，使用长音频模型
        segment_duration: Optional[int] = None,
        use_filetrans: bool = True,  # 默认使用 filetrans 模型
    ) -> TranscriptionResult:
        """
        语音转文本

        Args:
            audio_path: 音频文件路径
            auto_split: 是否自动分段处理长音频（仅用于非 filetrans 模型）
            segment_duration: 分段时长（秒），None 则使用默认值
            use_filetrans: 是否使用 filetrans 模型（支持长音频，需要 OSS）

        Returns:
            转录结果
        """
        if not self.api_key:
            return TranscriptionResult(
                success=False,
                error="未配置 API Key，无法进行语音转文本"
            )

        try:
            audio_path = Path(audio_path)
            if not audio_path.exists():
                return TranscriptionResult(
                    success=False,
                    error=f"音频文件不存在: {audio_path}"
                )

            # 获取音频信息
            info = await self.get_audio_info(str(audio_path))
            if not info:
                return TranscriptionResult(
                    success=False,
                    error="无法获取音频信息"
                )

            logger.info(f"开始转录音频: {audio_path} (时长: {info.duration:.2f}s)")

            # 使用 filetrans 模型（推荐，支持长音频且有句子级时间戳）
            if use_filetrans or "filetrans" in self.model:
                return await self._transcribe_with_filetrans(str(audio_path), info.duration)

            # 使用默认分段时长
            if segment_duration is None:
                segment_duration = self.DEFAULT_SEGMENT_DURATION

            # 判断是否需要分段（仅用于旧模型）
            if auto_split and info.duration > self.DEFAULT_SEGMENT_DURATION:
                logger.info(f"音频时长超过 {self.DEFAULT_SEGMENT_DURATION}s，将进行分段处理")
                return await self._transcribe_long_audio(
                    str(audio_path),
                    segment_duration,
                    info.duration
                )
            else:
                # 直接转录
                return await self._transcribe_single_audio(str(audio_path))

        except Exception as e:
            logger.error(f"语音转文本失败: {str(e)}")
            return TranscriptionResult(
                success=False,
                error=str(e)
            )

    async def _transcribe_with_filetrans(
        self,
        audio_path: str,
        duration: float,
    ) -> TranscriptionResult:
        """
        使用 filetrans 模型转录音频（支持长音频，需要公网 URL）

        Args:
            audio_path: 音频文件路径
            duration: 音频时长（秒）

        Returns:
            转录结果
        """
        try:
            # 1. 上传音频到 OSS
            if not self.oss_uploader or not self.oss_uploader.bucket:
                return TranscriptionResult(
                    success=False,
                    error="OSS 未配置，无法使用 filetrans 模型"
                )

            logger.info("上传音频文件到 OSS...")
            audio_url = self.oss_uploader.upload_file(audio_path)
            if not audio_url:
                return TranscriptionResult(
                    success=False,
                    error="上传音频到 OSS 失败"
                )

            logger.info(f"音频上传成功: {audio_url}")

            # 2. 提交转录任务
            task_id = await self._submit_filetrans_task(audio_url)
            if not task_id:
                return TranscriptionResult(
                    success=False,
                    error="提交转录任务失败"
                )

            logger.info(f"任务已提交，任务ID: {task_id}")

            # 3. 等待任务完成
            transcription_url = await self._wait_for_task_completion(task_id)
            if not transcription_url:
                return TranscriptionResult(
                    success=False,
                    error="任务执行失败或超时"
                )

            logger.info("任务完成，开始下载结果")

            # 4. 下载转录结果
            result_data = await self._download_transcription_result(transcription_url)
            if not result_data:
                return TranscriptionResult(
                    success=False,
                    error="下载转录结果失败"
                )

            # 5. 解析结果
            segments = self._parse_transcription_result(result_data)
            if not segments:
                return TranscriptionResult(
                    success=False,
                    error="解析转录结果失败"
                )

            # 合并所有文本
            full_text = "\n".join(seg.text for seg in segments)

            logger.info(f"转录成功，共 {len(segments)} 个句子，{len(full_text)} 个字符")

            return TranscriptionResult(
                success=True,
                text=full_text,
                segments=segments,
                duration=duration,
            )

        except Exception as e:
            logger.error(f"filetrans 转录失败: {str(e)}")
            return TranscriptionResult(
                success=False,
                error=str(e)
            )

    async def _submit_filetrans_task(self, audio_url: str) -> str:
        """
        提交 filetrans 转录任务（使用 DashScope SDK）

        Args:
            audio_url: 音频文件公网 URL

        Returns:
            任务ID，失败返回空字符串
        """
        try:
            from dashscope.audio.qwen_asr import QwenTranscription

            loop = asyncio.get_event_loop()

            # 使用 DashScope SDK 提交任务
            response = await loop.run_in_executor(
                None,
                lambda: QwenTranscription.async_call(
                    model='qwen3-asr-flash-filetrans',
                    file_url=audio_url,
                    enable_itn=True,
                    enable_disfluency_removal=False,
                    enable_words=True,
                )
            )

            logger.debug(f"API 响应: {response}")

            if response.status_code != 200:
                logger.error(f"提交任务失败: {response.code} - {response.message}")
                return ""

            if response.output and response.output.get("task_id"):
                return response.output["task_id"]
            else:
                logger.error(f"响应中没有task_id: {response}")
                return ""

        except Exception as e:
            logger.error(f"提交转录任务异常: {str(e)}")
            return ""

    async def _transcribe_single_audio(
        self,
        audio_path: str,
        start_time: float = 0,
        duration: float = 0,
    ) -> TranscriptionResult:
        """
        转录单个音频文件

        Args:
            audio_path: 音频文件路径
            start_time: 起始时间（秒）
            duration: 时长（秒）

        Returns:
            转录结果
        """
        try:
            # 调用 DashScope MultiModalConversation API（支持本地文件）
            loop = asyncio.get_event_loop()

            # 将本地路径转换为绝对路径
            abs_path = str(Path(audio_path).absolute())

            # 构建消息
            messages = [
                {
                    "role": "user",
                    "content": [{"audio": abs_path}]
                }
            ]

            # 调用 API
            response = await loop.run_in_executor(
                None,
                lambda: dashscope.MultiModalConversation.call(
                    api_key=self.api_key,
                    model=self.model,
                    messages=messages,
                    result_format="message",
                    asr_options={
                        "language": self.language,
                        "enable_itn": True,  # 启用逆文本归一化
                        "timestamp_alignment_enabled": True  # 启用时间戳对齐
                    }
                )
            )

            if response.status_code != 200:
                error_msg = f"API 调用失败: {response.code} - {response.message}"
                logger.error(error_msg)
                return TranscriptionResult(
                    success=False,
                    error=error_msg
                )

            # 调试：打印完整的响应结构
            logger.debug(f"完整 API 响应: {response}")

            # 提取转录文本和时间戳
            text = ""
            sentences = []

            if response.output and response.output.get("choices"):
                choices = response.output["choices"]
                if choices and len(choices) > 0:
                    message = choices[0].get("message", {})
                    content = message.get("content", [])
                    if content and len(content) > 0:
                        content_item = content[0]
                        text = content_item.get("text", "")

                        # 调试：打印完整的 content_item 结构
                        logger.debug(f"API 返回的 content_item 键: {list(content_item.keys())}")

                        # 提取句子级别的时间戳
                        asr_result = content_item.get("asr_result", {})
                        if asr_result:
                            logger.debug(f"找到 asr_result，键: {list(asr_result.keys())}")
                            sentence_list = asr_result.get("sentences", [])
                            for sent in sentence_list:
                                sentences.append(SentenceTimestamp(
                                    text=sent.get("text", ""),
                                    begin_time=sent.get("begin_time", 0),
                                    end_time=sent.get("end_time", 0)
                                ))
                        else:
                            logger.warning(f"未找到 asr_result，content_item: {content_item}")

            text = text.strip()
            logger.info(f"转录完成: {len(text)} 字符, {len(sentences)} 个句子")

            segment = TranscriptionSegment(
                text=text,
                start_time=start_time,
                end_time=start_time + duration,
                duration=duration,
                sentences=sentences
            )

            return TranscriptionResult(
                success=True,
                text=text,
                segments=[segment],
                duration=duration,
            )

        except Exception as e:
            logger.error(f"转录失败: {str(e)}")
            return TranscriptionResult(
                success=False,
                error=str(e)
            )

    async def _transcribe_long_audio(
        self,
        audio_path: str,
        segment_duration: int,
        total_duration: float,
    ) -> TranscriptionResult:
        """
        转录长音频（分段处理）

        Args:
            audio_path: 音频文件路径
            segment_duration: 分段时长（秒）
            total_duration: 总时长（秒）

        Returns:
            转录结果
        """
        try:
            # 分割音频
            segment_files = await self._split_audio(audio_path, segment_duration)
            if not segment_files:
                return TranscriptionResult(
                    success=False,
                    error="音频分割失败"
                )

            # 转录每个分段
            all_segments = []
            full_text = []

            for i, segment_file in enumerate(segment_files):
                start_time = i * segment_duration
                logger.info(f"转录分段 {i+1}/{len(segment_files)}: {segment_file}")

                result = await self._transcribe_single_audio(
                    segment_file,
                    start_time,
                    segment_duration
                )

                if result.success and result.segments:
                    all_segments.extend(result.segments)
                    full_text.append(result.text)
                else:
                    logger.warning(f"分段 {i+1} 转录失败: {result.error}")

            # 清理分段文件
            segment_dir = Path(segment_files[0]).parent
            try:
                import shutil
                shutil.rmtree(segment_dir)
                logger.debug(f"已清理分段文件: {segment_dir}")
            except Exception as e:
                logger.warning(f"清理分段文件失败: {str(e)}")

            if not all_segments:
                return TranscriptionResult(
                    success=False,
                    error="所有分段转录均失败"
                )

            return TranscriptionResult(
                success=True,
                text="\n".join(full_text),
                segments=all_segments,
                duration=total_duration,
            )

        except Exception as e:
            logger.error(f"长音频转录失败: {str(e)}")
            return TranscriptionResult(
                success=False,
                error=str(e)
            )

    async def _wait_for_task_completion(
        self,
        task_id: str,
        max_wait_time: int = 600,
        poll_interval: int = 2
    ) -> str:
        """等待任务完成

        Args:
            task_id: 任务ID
            max_wait_time: 最大等待时间（秒）
            poll_interval: 轮询间隔（秒）

        Returns:
            str: 转录结果URL，失败返回空字符串
        """
        try:
            from dashscope.audio.qwen_asr import QwenTranscription

            start_time = time.time()
            loop = asyncio.get_event_loop()

            while time.time() - start_time < max_wait_time:
                # 使用 QwenTranscription.wait() 查询任务状态
                result = await loop.run_in_executor(
                    None,
                    lambda: QwenTranscription.wait(task=task_id)
                )

                status = result.output.task_status
                logger.debug(f"任务状态: {status}")

                if status == "SUCCEEDED":
                    transcription_url = result.output.result.get('transcription_url')
                    if transcription_url:
                        return transcription_url
                    else:
                        logger.error(f"任务成功但没有transcription_url: {result}")
                        return ""

                elif status == "FAILED":
                    error_msg = result.output.message if hasattr(result.output, 'message') else "未知错误"
                    logger.error(f"任务失败: {error_msg}")
                    logger.error(f"完整响应: {result}")
                    return ""

                # 等待后继续轮询
                await asyncio.sleep(poll_interval)

            logger.error(f"任务超时（{max_wait_time}秒）")
            return ""

        except Exception as e:
            logger.error(f"等待任务完成异常: {str(e)}")
            return ""

    async def _download_transcription_result(self, url: str) -> dict:
        """下载转录结果

        Args:
            url: 结果URL

        Returns:
            dict: 转录结果数据，失败返回None
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=30)
            )

            if response.status_code != 200:
                logger.error(f"下载结果失败: {response.status_code}")
                return None

            return response.json()

        except Exception as e:
            logger.error(f"下载转录结果异常: {str(e)}")
            return None

    def _parse_transcription_result(self, data: dict) -> List[TranscriptionSegment]:
        """解析转录结果

        Args:
            data: 转录结果数据

        Returns:
            List[TranscriptionSegment]: 分段列表
        """
        try:
            segments = []

            # 获取句子列表
            transcripts = data.get("transcripts", [])
            if not transcripts:
                logger.warning("转录结果中没有transcripts")
                return []

            sentences_data = transcripts[0].get("sentences", [])
            if not sentences_data:
                logger.warning("转录结果中没有sentences")
                return []

            # 将每个句子作为一个segment
            for sentence_data in sentences_data:
                text = sentence_data.get("text", "")
                begin_time = sentence_data.get("begin_time", 0)  # 毫秒
                end_time = sentence_data.get("end_time", 0)  # 毫秒

                if not text:
                    continue

                # 创建句子时间戳
                sentence_timestamp = SentenceTimestamp(
                    text=text,
                    begin_time=begin_time,
                    end_time=end_time
                )

                # 创建segment（每个句子一个segment）
                segment = TranscriptionSegment(
                    text=text,
                    start_time=begin_time / 1000.0,  # 转为秒
                    end_time=end_time / 1000.0,
                    duration=(end_time - begin_time) / 1000.0,
                    sentences=[sentence_timestamp]
                )

                segments.append(segment)

            return segments

        except Exception as e:
            logger.error(f"解析转录结果异常: {str(e)}")
            return []

    async def save_srt(
        self,
        result: TranscriptionResult,
        output_path: str,
    ) -> bool:
        """
        保存转录结果为 SRT 字幕文件

        Args:
            result: 转录结果
            output_path: 输出 SRT 文件路径

        Returns:
            是否成功
        """
        try:
            if not result.success:
                logger.error("转录结果不成功，无法生成 SRT 文件")
                return False

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 生成 SRT 内容
            srt_content = result.to_srt()

            # 写入文件
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(srt_content)

            logger.info(f"SRT 文件保存成功: {output_path}")
            return True

        except Exception as e:
            logger.error(f"保存 SRT 文件失败: {str(e)}")
            return False
