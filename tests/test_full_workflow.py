"""
全流程集成测试
测试从视频下载 -> 音频提取 -> 语音识别生成SRT文件 -> 视频帧提取 -> 图像识别的完整流程
使用 WorkspaceManager 管理工作目录
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
from src.core.frames import FrameExtractor, FrameConfig, ImageFormat
from src.core.vision import VisionAnalyzer, AnalysisType
from src.utils.oss import OSSUploader
from src.utils.workspace import WorkspaceManager

# 加载环境变量
load_dotenv()


# ============ 测试配置 - 请在这里填写你的配置 ============

# 测试视频URL
TEST_VIDEO_URL = "https://www.bilibili.com/video/BV1A3hRzpEY5/?share_source=copy_web&vd_source=8293de39e4ed8600888df26516cd9b8d"

# 阿里百炼 API Key
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

# OSS 配置
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT")
OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME")

# ========================================================

# 工作空间管理器
ws_manager = WorkspaceManager(
    base_dir="./workspace",
    max_size_gb=10.0,
    auto_cleanup_days=7,
)


class TestFullWorkflow:
    """全流程集成测试"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """
        完整流程测试：视频下载 -> 音频提取 -> 语音识别 -> 生成SRT -> 帧提取 -> 图像识别

        测试步骤：
        1. 从URL下载视频
        2. 从视频中提取音频
        3. 使用语音识别生成文本
        4. 保存为SRT字幕文件
        5. 提取视频帧并上传OSS
        6. 使用Qwen-VL识别视频帧内容
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

        # 创建本次测试的工作空间
        ws = ws_manager.create()
        video_dir = ws_manager.get_path(ws.workspace_id, "video")
        audio_dir = ws_manager.get_path(ws.workspace_id, "audio")
        frames_dir = ws_manager.get_path(ws.workspace_id, "frames")
        output_dir = ws_manager.get_path(ws.workspace_id, "output")

        print(f"工作空间: {ws.workspace_id}")
        print(f"工作目录: {ws.path.absolute()}")

        # 生成时间戳用于文件命名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ============ 步骤1: 下载视频 ============
        print(f"\n[步骤1] 下载视频")

        downloader = VideoDownloader(
            output_dir=str(video_dir),
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
        audio_path = audio_dir / audio_filename

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
        text_path = output_dir / text_filename

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
        srt_path = output_dir / srt_filename

        save_success = await audio_processor_with_api.save_srt(
            transcription_result,
            str(srt_path)
        )

        assert save_success, "SRT字幕保存失败"
        assert srt_path.exists(), "SRT文件不存在"
        print(f"  [OK] SRT字幕已保存: {srt_path}")

        # ============ 步骤5: 视频帧提取 ============
        print(f"\n[步骤5] 视频帧提取")

        # 构造时间戳列表（模拟 LLM 分析转录结果后给出的关键时间点）
        # 策略：取视频时长的 10%、30%、50%、70%、90% 位置
        duration = transcription_result.duration or audio_info.duration
        frame_timestamps = [
            round(duration * ratio, 2)
            for ratio in [0.1, 0.3, 0.5, 0.7, 0.9]
        ]
        print(f"  提取时间点: {frame_timestamps}")

        frame_output_dir = frames_dir
        oss_uploader = OSSUploader()

        config = FrameConfig(
            image_format=ImageFormat.JPEG,
            quality=85,
            max_width=1280,
        )
        extractor = FrameExtractor(config=config, oss_uploader=oss_uploader)

        extraction_result = await extractor.extract_frames(
            video_path=video_path,
            output_dir=str(frame_output_dir),
            timestamps=frame_timestamps,
        )

        assert extraction_result.success, f"帧提取失败: {extraction_result.error}"
        assert extraction_result.total_extracted > 0, "未提取到任何帧"

        print(f"  [OK] 帧提取成功: {extraction_result.total_extracted}/{extraction_result.total_requested}")
        print(f"  视频时长: {extraction_result.video_duration:.2f}s")

        for frame in extraction_result.frames:
            oss_info = f" -> {frame.oss_url}" if frame.oss_url else ""
            print(f"  帧 {frame.index}: {frame.timestamp:.2f}s "
                  f"({frame.width}x{frame.height}, {frame.file_size/1024:.1f}KB)"
                  f"{oss_info}")

        # ============ 步骤6: 图像识别 ============
        print(f"\n[步骤6] 图像识别")

        # 初始化图像识别分析器
        vision_analyzer = VisionAnalyzer(
            api_key=DASHSCOPE_API_KEY,
            model="qwen3-vl-flash",
            oss_uploader=oss_uploader,
        )

        print(f"  开始分析 {len(extraction_result.frames)} 帧图像...")

        # 批量分析视频帧
        vision_result = await vision_analyzer.analyze_frames(
            frame_infos=extraction_result.frames,
            analysis_type=AnalysisType.SMART,  # 智能识别：自动判断图表/PPT/代码/普通画面
            max_concurrent=3,
        )

        assert vision_result.success, f"图像识别失败: {vision_result.error}"
        assert vision_result.total_succeeded > 0, "没有成功识别的图像"

        print(f"  [OK] 图像识别完成: {vision_result.total_succeeded}/{vision_result.total_requested}")

        # 显示识别结果
        for i, result in enumerate(vision_result.results):
            if result.success:
                frame = extraction_result.frames[i]
                print(f"  帧 {frame.index} ({frame.timestamp:.2f}s):")
                print(f"    {result.description[:80]}...")

        # 保存图像识别结果
        vision_filename = f"vision_analysis_{timestamp}.txt"
        vision_path = output_dir / vision_filename

        with open(vision_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("视频帧图像识别结果\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"视频URL: {TEST_VIDEO_URL}\n")
            f.write(f"视频文件: {video_path}\n")
            f.write(f"识别时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"分析模型: qwen3-vl-flash\n")
            f.write(f"分析类型: 智能识别\n")
            f.write(f"总帧数: {vision_result.total_requested}\n")
            f.write(f"成功数: {vision_result.total_succeeded}\n")
            f.write(f"失败数: {vision_result.total_failed}\n\n")

            f.write("=" * 80 + "\n")
            f.write("识别详情\n")
            f.write("=" * 80 + "\n\n")

            for i, result in enumerate(vision_result.results):
                frame = extraction_result.frames[i]
                f.write(f"【帧 {frame.index}】\n")
                f.write(f"时间戳: {frame.timestamp:.2f}秒\n")
                f.write(f"图片尺寸: {frame.width}x{frame.height}\n")
                f.write(f"图片大小: {frame.file_size/1024:.1f}KB\n")
                f.write(f"本地路径: {frame.file_path}\n")
                if frame.oss_url:
                    f.write(f"OSS URL: {frame.oss_url}\n")
                f.write(f"识别状态: {'成功' if result.success else '失败'}\n")
                if result.success:
                    f.write(f"场景描述:\n{result.description}\n")
                else:
                    f.write(f"错误信息: {result.error}\n")
                f.write("-" * 80 + "\n\n")

        assert vision_path.exists(), "图像识别结果保存失败"
        print(f"  [OK] 识别结果已保存: {vision_path}")

        # ============ 测试总结 ============
        print(f"\n{'='*80}")
        print("全流程测试完成！")
        print(f"{'='*80}")

        # 获取工作空间最终信息
        ws_info = ws_manager.get_info(ws.workspace_id)
        print(f"工作空间: {ws.workspace_id}")
        print(f"工作目录: {ws.path.absolute()}")
        print(f"空间占用: {ws_info.size_mb:.2f} MB")
        print(f"[OK] 视频文件: {video_path}")
        print(f"[OK] 音频文件: {extracted_audio}")
        print(f"[OK] 文本结果: {text_path}")
        print(f"[OK] SRT字幕: {srt_path}")
        print(f"[OK] 帧图片: {frame_output_dir} ({extraction_result.total_extracted} 帧)")
        print(f"[OK] 图像识别: {vision_path}")
        print(f"\n统计信息:")
        if download_result.duration:
            print(f"  视频时长: {download_result.duration:.2f}秒")
        print(f"  识别字符数: {len(transcription_result.text)}")
        print(f"  分段数量: {len(transcription_result.segments)}")
        if total_sentences > 0:
            print(f"  句子数量: {total_sentences}")
        print(f"  提取帧数: {extraction_result.total_extracted}")
        uploaded_count = sum(1 for f in extraction_result.frames if f.oss_url)
        if uploaded_count > 0:
            print(f"  OSS上传: {uploaded_count} 帧")
        print(f"  图像识别: {vision_result.total_succeeded}/{vision_result.total_requested} 成功")
        print(f"{'='*80}\n")

        # 显示前3个字幕段预览
        print("字幕预览（前3段）:")
        for i, segment in enumerate(transcription_result.segments[:3], 1):
            print(f"  [{i}] {segment.start_time:.2f}s - {segment.end_time:.2f}s")
            print(f"      {segment.text[:50]}...")
        print()

        # ============ 输出结果报告 ============
        report_path = output_dir / f"workflow_report_{timestamp}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 全流程集成测试报告\n\n")
            f.write(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## 步骤1: 视频下载\n\n")
            f.write(f"- 来源URL: {TEST_VIDEO_URL}\n")
            f.write(f"- 视频标题: {download_result.title}\n")
            f.write(f"- 本地路径: `{Path(video_path).absolute()}`\n")
            if download_result.duration:
                f.write(f"- 视频时长: {download_result.duration:.2f}秒\n")
            if download_result.file_size:
                f.write(f"- 文件大小: {download_result.file_size / 1024 / 1024:.2f}MB\n")
            f.write("\n")

            f.write("## 步骤2: 音频提取\n\n")
            f.write(f"- 本地路径: `{Path(extracted_audio).absolute()}`\n")
            f.write(f"- 格式: MP3 128kbps\n")
            f.write(f"- 时长: {audio_info.duration:.2f}秒\n")
            f.write(f"- 采样率: {audio_info.sample_rate}Hz\n")
            f.write(f"- 声道数: {audio_info.channels}\n")
            f.write(f"- 文件大小: {audio_info.file_size / 1024 / 1024:.2f}MB\n\n")

            f.write("## 步骤3: 语音识别\n\n")
            f.write(f"- 模型: qwen3-asr-flash-filetrans\n")
            f.write(f"- 识别字符数: {len(transcription_result.text)}\n")
            f.write(f"- 分段数量: {len(transcription_result.segments)}\n")
            if total_sentences > 0:
                f.write(f"- 句子数量: {total_sentences}\n")
            f.write(f"\n前3段预览:\n\n")
            for i, seg in enumerate(transcription_result.segments[:3], 1):
                f.write(f"> [{seg.start_time:.2f}s - {seg.end_time:.2f}s] {seg.text}\n\n")

            f.write("## 步骤4: 结果保存\n\n")
            f.write(f"- 转录文本: `{text_path.absolute()}`\n")
            f.write(f"- SRT字幕: `{srt_path.absolute()}`\n\n")

            f.write("## 步骤5: 视频帧提取\n\n")
            f.write(f"- 输出目录: `{frame_output_dir.absolute()}`\n")
            f.write(f"- 图片格式: JPEG (质量85, 最大宽度1280)\n")
            f.write(f"- 请求帧数: {extraction_result.total_requested}\n")
            f.write(f"- 成功提取: {extraction_result.total_extracted}\n")
            f.write(f"- 时间戳列表: {frame_timestamps}\n\n")
            f.write("| 序号 | 时间戳 | 尺寸 | 大小 | 本地路径 | OSS URL |\n")
            f.write("|------|--------|------|------|----------|--------|\n")
            for frame in extraction_result.frames:
                oss_url = frame.oss_url or "未上传"
                f.write(
                    f"| {frame.index} | {frame.timestamp:.2f}s "
                    f"| {frame.width}x{frame.height} "
                    f"| {frame.file_size/1024:.1f}KB "
                    f"| `{frame.file_path}` "
                    f"| {oss_url} |\n"
                )
            f.write("\n")

            f.write("## 步骤6: 图像识别\n\n")
            f.write(f"- 分析模型: qwen3-vl-flash\n")
            f.write(f"- 分析类型: 场景识别\n")
            f.write(f"- 请求数量: {vision_result.total_requested}\n")
            f.write(f"- 成功数量: {vision_result.total_succeeded}\n")
            f.write(f"- 失败数量: {vision_result.total_failed}\n\n")
            f.write("| 帧序号 | 时间戳 | 场景描述 |\n")
            f.write("|--------|--------|----------|\n")
            for i, vr in enumerate(vision_result.results):
                frame = extraction_result.frames[i]
                desc = vr.description[:100].replace("\n", " ") if vr.success else f"失败: {vr.error}"
                f.write(f"| {frame.index} | {frame.timestamp:.2f}s | {desc} |\n")
            f.write("\n")

            f.write("## 产出文件汇总\n\n")
            f.write("| 类型 | 路径 |\n")
            f.write("|------|------|\n")
            f.write(f"| 视频文件 | `{Path(video_path).absolute()}` |\n")
            f.write(f"| 音频文件 | `{Path(extracted_audio).absolute()}` |\n")
            f.write(f"| 转录文本 | `{text_path.absolute()}` |\n")
            f.write(f"| SRT字幕 | `{srt_path.absolute()}` |\n")
            f.write(f"| 帧图片目录 | `{frame_output_dir.absolute()}` |\n")
            f.write(f"| 图像识别结果 | `{vision_path.absolute()}` |\n")
            f.write(f"| 本报告 | `{report_path.absolute()}` |\n")

        print(f"[OK] 测试报告已保存: {report_path}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
