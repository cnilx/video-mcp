"""
全流程集成测试
测试从视频下载 -> 音频提取 -> 语音识别生成SRT文件的完整流程
生成的文件保存到 ./testWorkspace 目录
"""
import pytest
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from src.core.downloader import VideoDownloader, VideoQuality
from src.core.audio import AudioProcessor, AudioFormat, SampleRate
from src.utils.oss import OSSUploader

# 加载环境变量
load_dotenv()


# ============ 测试配置 - 请在这里填写你的配置 ============

# 测试视频URL
TEST_VIDEO_URL = "https://v.douyin.com/hCKa72AHs0c/"

# 阿里百炼 API Key
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

# OSS 配置
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT")
OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME")

# ========================================================

# 测试工作目录
TEST_WORKSPACE = Path("./workspace")
TEST_WORKSPACE.mkdir(parents=True, exist_ok=True)


class TestFullWorkflow:
    """全流程集成测试"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """
        完整流程测试：视频下载 -> 音频提取 -> 语音识别 -> 生成SRT

        测试步骤：
        1. 从URL下载视频
        2. 从视频中提取音频
        3. 使用语音识别生成文本
        4. 保存为SRT字幕文件
        """

        # 检查配置
        if not DASHSCOPE_API_KEY:
            pytest.fail("未配置 DASHSCOPE_API_KEY，请在 .env 文件中配置")

        if not OSS_ACCESS_KEY_ID or not OSS_ACCESS_KEY_SECRET or not OSS_ENDPOINT or not OSS_BUCKET_NAME:
            pytest.fail("未配置 OSS 相关配置，请在 .env 文件中配置")

        if not TEST_VIDEO_URL:
            pytest.fail("未配置测试视频URL，请在文件头部设置 TEST_VIDEO_URL")

        print(f"\n{'='*80}")
        print("全流程集成测试开始")
        print(f"{'='*80}")
        print(f"测试视频URL: {TEST_VIDEO_URL}")
        print(f"工作目录: {TEST_WORKSPACE.absolute()}")

        # 生成时间戳用于文件命名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ============ 步骤1: 下载视频 ============
        print(f"\n[步骤1] 下载视频")

        downloader = VideoDownloader(
            output_dir=str(TEST_WORKSPACE),
            max_retries=3,
            timeout=300
        )

        # 设置进度回调
        def progress_callback(progress):
            if progress.status == 'downloading':
                print(f"  下载进度: {progress.percent:.1f}% "
                      f"({progress.downloaded_mb:.2f}MB / {progress.total_mb:.2f}MB) "
                      f"速度: {progress.speed/1024/1024:.2f}MB/s", end='\r')
            elif progress.status == 'finished':
                print(f"\n  下载完成")

        downloader.set_progress_callback(progress_callback)

        download_result = await downloader.download(
            TEST_VIDEO_URL,
            quality=VideoQuality.MEDIUM,  # 使用中等质量以节省时间
            format_type='mp4'
        )

        assert download_result.success, f"视频下载失败: {download_result.error}"
        assert download_result.file_path is not None

        video_path = download_result.file_path
        print(f"  [OK] 视频下载成功")
        print(f"  文件路径: {video_path}")
        print(f"  视频标题: {download_result.title}")
        if download_result.duration:
            print(f"  视频时长: {download_result.duration:.2f}秒")
        if download_result.file_size:
            print(f"  文件大小: {download_result.file_size / 1024 / 1024:.2f}MB")

        # ============ 步骤2: 提取音频 ============
        print(f"\n[步骤2] 提取音频")

        audio_processor = AudioProcessor()

        # 生成音频文件路径
        audio_filename = f"audio_{timestamp}.mp3"
        audio_path = TEST_WORKSPACE / audio_filename

        extracted_audio = await audio_processor.extract_audio(
            video_path,
            output_path=str(audio_path),
            audio_format=AudioFormat.MP3,
            audio_bitrate="128k"
        )

        assert extracted_audio is not None, "音频提取失败"
        assert Path(extracted_audio).exists(), f"音频文件不存在: {extracted_audio}"

        print(f"  [OK] 音频提取成功")
        print(f"  音频文件: {extracted_audio}")

        # 获取音频信息
        audio_info = await audio_processor.get_audio_info(extracted_audio)
        assert audio_info is not None, "无法获取音频信息"

        print(f"  音频时长: {audio_info.duration:.2f}秒")
        print(f"  采样率: {audio_info.sample_rate}Hz")
        print(f"  声道数: {audio_info.channels}")
        print(f"  文件大小: {audio_info.file_size / 1024 / 1024:.2f}MB")

        # ============ 步骤3: 语音识别 ============
        print(f"\n[步骤3] 语音识别")

        # 创建带API Key的音频处理器
        # 设置 OSS 环境变量（用于音频上传）
        os.environ["OSS_ACCESS_KEY_ID"] = OSS_ACCESS_KEY_ID
        os.environ["OSS_ACCESS_KEY_SECRET"] = OSS_ACCESS_KEY_SECRET
        os.environ["OSS_ENDPOINT"] = OSS_ENDPOINT
        os.environ["OSS_BUCKET_NAME"] = OSS_BUCKET_NAME

        audio_processor_with_api = AudioProcessor(
            api_key=DASHSCOPE_API_KEY,
            model="qwen3-asr-flash-filetrans",
            language="zh"
        )

        print(f"  开始识别音频（使用 filetrans 模型）...")

        transcription_result = await audio_processor_with_api.transcribe_audio(
            extracted_audio,
            use_filetrans=True  # 使用 filetrans 模型，支持长音频
        )

        assert transcription_result.success, f"语音识别失败: {transcription_result.error}"
        assert len(transcription_result.text) > 0, "识别文本为空"

        print(f"  [OK] 识别成功")
        print(f"  识别字符数: {len(transcription_result.text)}")
        print(f"  分段数量: {len(transcription_result.segments)}")

        # 统计句子数量
        total_sentences = sum(
            len(seg.sentences) for seg in transcription_result.segments
            if seg.sentences
        )
        if total_sentences > 0:
            print(f"  句子数量: {total_sentences}")

        # ============ 步骤4: 保存结果 ============
        print(f"\n[步骤4] 保存识别结果")

        # 4.1 保存文本结果
        text_filename = f"transcription_{timestamp}.txt"
        text_path = TEST_WORKSPACE / text_filename

        with open(text_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("视频语音识别结果\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"视频URL: {TEST_VIDEO_URL}\n")
            f.write(f"视频文件: {video_path}\n")
            f.write(f"音频文件: {extracted_audio}\n")
            f.write(f"识别时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"音频时长: {transcription_result.duration:.2f}秒\n")
            f.write(f"识别字符数: {len(transcription_result.text)}字符\n")
            f.write(f"分段数量: {len(transcription_result.segments)}\n\n")

            f.write("=" * 80 + "\n")
            f.write("完整识别文本\n")
            f.write("=" * 80 + "\n\n")
            f.write(transcription_result.text + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("分段详情（带时间戳）\n")
            f.write("=" * 80 + "\n\n")

            for i, segment in enumerate(transcription_result.segments, 1):
                f.write(f"【段{i}】\n")
                f.write(f"时间: {segment.start_time:.2f}s - {segment.end_time:.2f}s\n")
                f.write(f"时长: {segment.duration:.2f}秒\n")
                f.write(f"内容: {segment.text}\n")
                f.write("-" * 80 + "\n\n")

        assert text_path.exists(), "文本结果保存失败"
        print(f"  [OK] 文本结果已保存: {text_path}")

        # 4.2 保存SRT字幕文件
        srt_filename = f"subtitle_{timestamp}.srt"
        srt_path = TEST_WORKSPACE / srt_filename

        save_success = await audio_processor_with_api.save_srt(
            transcription_result,
            str(srt_path)
        )

        assert save_success, "SRT字幕保存失败"
        assert srt_path.exists(), "SRT文件不存在"
        print(f"  [OK] SRT字幕已保存: {srt_path}")

        # ============ 测试总结 ============
        print(f"\n{'='*80}")
        print("全流程测试完成！")
        print(f"{'='*80}")
        print(f"工作目录: {TEST_WORKSPACE.absolute()}")
        print(f"[OK] 视频文件: {video_path}")
        print(f"[OK] 音频文件: {extracted_audio}")
        print(f"[OK] 文本结果: {text_path}")
        print(f"[OK] SRT字幕: {srt_path}")
        print(f"\n统计信息:")
        if download_result.duration:
            print(f"  视频时长: {download_result.duration:.2f}秒")
        print(f"  识别字符数: {len(transcription_result.text)}")
        print(f"  分段数量: {len(transcription_result.segments)}")
        if total_sentences > 0:
            print(f"  句子数量: {total_sentences}")
        print(f"{'='*80}\n")

        # 显示前3个字幕段预览
        print("字幕预览（前3段）:")
        for i, segment in enumerate(transcription_result.segments[:3], 1):
            print(f"  [{i}] {segment.start_time:.2f}s - {segment.end_time:.2f}s")
            print(f"      {segment.text[:50]}...")
        print()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
