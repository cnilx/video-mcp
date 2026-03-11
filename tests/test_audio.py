"""音频处理模块测试 - 完整流程测试"""
import pytest
import asyncio
import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from dashscope.audio.qwen_asr import QwenTranscription
import dashscope

from src.core.audio import (
    AudioProcessor,
    AudioFormat,
    SampleRate,
    AudioInfo,
    TranscriptionResult,
)
from src.utils.oss import OSSUploader

# 加载环境变量
load_dotenv()

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# 测试视频文件路径
TEST_VIDEO = "downloads/底层穷人为什么完不成原始资本积累？.mp4"
TEST_AUDIO_OUTPUT = "downloads/extracted_audio.mp3"
TEST_TRANSCRIPTION_OUTPUT = "downloads/transcription_result.txt"


@pytest.fixture
def audio_processor():
    """创建音频处理器实例"""
    return AudioProcessor()


@pytest.fixture
def audio_processor_with_api():
    """创建带 API Key 的音频处理器实例"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    return AudioProcessor(api_key=api_key)


@pytest.fixture(scope="session", autouse=True)
def cleanup():
    """测试结束后清理生成的文件"""
    yield
    # 测试结束后保留结果文件，只清理临时文件
    print("\n测试完成，结果文件已保存")


class TestCompleteAudioWorkflow:
    """测试完整的音频处理流程：提取 -> 识别 -> 保存"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, audio_processor_with_api):
        """测试完整流程：从视频提取音频 -> 语音识别 -> 保存结果"""

        # 检查 API Key
        if not audio_processor_with_api.api_key:
            pytest.skip("未配置 DASHSCOPE_API_KEY")

        # 检查视频文件
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        print(f"\n{'='*60}")
        print("开始完整音频处理流程测试")
        print(f"{'='*60}")

        # ============ 步骤1: 提取音频 ========W ====
        print(f"\n[步骤1] 从视频提取音频")
        print(f"  视频文件: {TEST_VIDEO}")

        processor = AudioProcessor()
        audio_path = await processor.extract_audio(
            TEST_VIDEO,
            output_path=TEST_AUDIO_OUTPUT,
            audio_format=AudioFormat.MP3,
            audio_bitrate="128k"
        )

        assert audio_path is not None, "音频提取失败"
        assert Path(audio_path).exists(), f"输出文件不存在: {audio_path}"

        print(f"  [OK] 音频提取成功: {audio_path}")

        # 获取音频信息
        info = await processor.get_audio_info(audio_path)
        assert info is not None, "无法获取音频信息"

        print(f"  音频时长: {info.duration:.2f}秒")
        print(f"  采样率: {info.sample_rate}Hz")
        print(f"  声道数: {info.channels}")
        print(f"  文件大小: {info.file_size / 1024 / 1024:.2f}MB")

        # ============ 步骤2: 语音识别 ============
        print(f"\n[步骤2] 语音识别")
        print(f"  开始识别音频...")

        result = await audio_processor_with_api.transcribe_audio(
            audio_path,
            auto_split=True
        )

        assert result.success, f"语音识别失败: {result.error}"
        assert len(result.text) > 0, "识别文本为空"

        print(f"  [OK] 识别成功")
        print(f"  识别字符数: {len(result.text)}")
        print(f"  分段数量: {len(result.segments)}")

        # ============ 步骤3: 保存结果 ============
        print(f"\n[步骤3] 保存识别结果")

        # 生成结果文件
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 保存详细文本结果
        with open(TEST_TRANSCRIPTION_OUTPUT, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("视频语音识别结果\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"视频文件: {TEST_VIDEO}\n")
            f.write(f"音频文件: {audio_path}\n")
            f.write(f"识别时间: {timestamp}\n")
            f.write(f"音频时长: {result.duration:.2f}秒 ({result.duration/60:.1f}分钟)\n")
            f.write(f"识别字符数: {len(result.text)}字符\n")
            f.write(f"分段数量: {len(result.segments)}\n\n")

            f.write("=" * 80 + "\n")
            f.write("完整识别文本\n")
            f.write("=" * 80 + "\n\n")
            f.write(result.text + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("分段详情（带时间戳）\n")
            f.write("=" * 80 + "\n\n")

            for i, segment in enumerate(result.segments, 1):
                f.write(f"【段{i}】\n")
                f.write(f"时间: {segment.start_time:.2f}s - {segment.end_time:.2f}s\n")
                f.write(f"时长: {segment.duration:.2f}秒\n")
                f.write(f"字符数: {len(segment.text)}\n")

                # 显示句子级别的时间戳
                if segment.sentences:
                    f.write(f"句子数量: {len(segment.sentences)}\n\n")
                    for j, sentence in enumerate(segment.sentences, 1):
                        start_sec = sentence.begin_time / 1000
                        end_sec = sentence.end_time / 1000
                        f.write(f"  [{j}] {start_sec:.2f}s - {end_sec:.2f}s\n")
                        f.write(f"      {sentence.text}\n\n")
                else:
                    f.write(f"内容:\n{segment.text}\n")

                f.write("-" * 80 + "\n\n")

        # 保存 SRT 字幕格式
        srt_output = TEST_TRANSCRIPTION_OUTPUT.replace(".txt", ".srt")
        with open(srt_output, "w", encoding="utf-8") as f:
            f.write(result.to_srt())

        assert Path(TEST_TRANSCRIPTION_OUTPUT).exists(), "结果文件保存失败"
        assert Path(srt_output).exists(), "SRT 字幕文件保存失败"

        print(f"  [OK] 文本结果已保存: {TEST_TRANSCRIPTION_OUTPUT}")
        print(f"  [OK] SRT 字幕已保存: {srt_output}")

        # ============ 测试总结 ============
        print(f"\n{'='*60}")
        print("测试完成！")
        print(f"{'='*60}")
        print(f"[OK] 音频文件: {audio_path}")
        print(f"[OK] 文本结果: {TEST_TRANSCRIPTION_OUTPUT}")
        print(f"[OK] SRT 字幕: {srt_output}")
        print(f"[OK] 识别字符数: {len(result.text)}")
        print(f"[OK] 分段数量: {len(result.segments)}")

        # 统计句子数量
        total_sentences = sum(len(seg.sentences) for seg in result.segments if seg.sentences)
        if total_sentences > 0:
            print(f"[OK] 句子数量: {total_sentences}")

        print(f"{'='*60}\n")


class TestAudioInfo:
    """测试音频信息获取"""

    @pytest.mark.asyncio
    async def test_get_audio_info_nonexistent(self, audio_processor):
        """测试获取不存在文件的音频信息"""
        result = await audio_processor.get_audio_info("nonexistent.mp3")
        assert result is None


class TestAudioExtraction:
    """测试音频提取边界情况"""

    @pytest.mark.asyncio
    async def test_extract_audio_nonexistent(self, audio_processor):
        """测试从不存在的视频提取音频"""
        result = await audio_processor.extract_audio("nonexistent.mp4")
        assert result is None


class TestAudioConversion:
    """测试音频格式转换"""

    @pytest.mark.asyncio
    async def test_convert_audio_nonexistent(self, audio_processor):
        """测试转换不存在的音频文件"""
        result = await audio_processor.convert_audio("nonexistent.mp3")
        assert result is None


class TestTranscription:
    """测试语音转文本边界情况"""

    @pytest.mark.asyncio
    async def test_transcribe_without_api_key(self, audio_processor):
        """测试没有 API Key 时的转录"""
        result = await audio_processor.transcribe_audio("test.mp3")
        assert not result.success
        assert "API Key" in result.error

    @pytest.mark.asyncio
    async def test_transcribe_nonexistent_file(self, audio_processor_with_api):
        """测试转录不存在的文件"""
        if not audio_processor_with_api.api_key:
            pytest.skip("未配置 DASHSCOPE_API_KEY")

        result = await audio_processor_with_api.transcribe_audio("nonexistent.mp3")
        assert not result.success
        assert "不存在" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


class TestFiletransWorkflow:
    """测试使用 filetrans 模型的完整转录流程"""

    @pytest.mark.asyncio
    async def test_filetrans_transcription_with_srt(self):
        """测试 filetrans 模型转录并生成 SRT 字幕"""

        # 检查配置
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            pytest.skip("未配置 DASHSCOPE_API_KEY")

        # 检查 OSS 配置
        if not all([
            os.getenv("OSS_ACCESS_KEY_ID"),
            os.getenv("OSS_ACCESS_KEY_SECRET"),
            os.getenv("OSS_ENDPOINT"),
            os.getenv("OSS_BUCKET_NAME")
        ]):
            pytest.skip("未配置 OSS 相关环境变量")

        # 音频文件路径
        audio_path = "downloads/test_short.mp3"
        if not Path(audio_path).exists():
            pytest.skip(f"测试音频不存在: {audio_path}")

        print(f"\n{'='*80}")
        print("测试 filetrans 模型转录和 SRT 生成")
        print(f"{'='*80}")
        print(f"测试音频: {audio_path}")

        # 设置 API
        dashscope.api_key = api_key
        dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

        # 步骤 1: 上传到 OSS
        print(f"\n[步骤1] 上传文件到 OSS")
        oss = OSSUploader()
        assert oss.bucket is not None, "OSS 初始化失败"

        audio_url = oss.upload_file(audio_path)
        assert audio_url is not None, "文件上传失败"
        print(f"  [OK] 上传成功: {audio_url}")

        # 步骤 2: 提交转录任务
        print(f"\n[步骤2] 提交转录任务")
        task_response = QwenTranscription.async_call(
            model='qwen3-asr-flash-filetrans',
            file_url=audio_url,
            enable_itn=True,
            enable_disfluency_removal=False,
            enable_words=True,
        )

        assert task_response.status_code == 200, f"任务提交失败: {task_response.code}"
        task_id = task_response.output.task_id
        print(f"  [OK] 任务已提交，ID: {task_id}")

        # 步骤 3: 等待任务完成
        print(f"\n[步骤3] 等待任务完成")
        import time
        max_wait = 120
        start_time = time.time()
        result = None

        while time.time() - start_time < max_wait:
            result = QwenTranscription.wait(task=task_id)
            status = result.output.task_status

            if status == 'SUCCEEDED':
                print(f"  [OK] 任务成功完成")
                break
            elif status == 'FAILED':
                pytest.fail(f"任务失败: {result.output.message}")

            time.sleep(2)
        else:
            pytest.fail(f"任务超时（{max_wait}秒）")

        # 步骤 4: 下载转录结果
        print(f"\n[步骤4] 下载转录结果")
        transcription_url = result.output.result['transcription_url']
        response = requests.get(transcription_url)
        assert response.status_code == 200, "下载结果失败"

        result_data = response.json()
        print(f"  [OK] 结果下载成功")

        # 步骤 5: 解析结果
        print(f"\n[步骤5] 解析转录结果")
        transcripts = result_data.get("transcripts", [])
        assert len(transcripts) > 0, "没有找到转录结果"

        sentences = transcripts[0].get("sentences", [])
        print(f"  [OK] 找到 {len(sentences)} 个句子")

        # 检查词级别时间戳
        words = transcripts[0].get("words", [])
        if words:
            print(f"  [OK] 找到 {len(words)} 个词")

        # 如果句子太少，按词分组
        if len(sentences) < 3 and words:
            print(f"  句子数量较少，按词分组...")
            grouped_sentences = []
            current_group = []
            words_per_group = 10

            for i, word in enumerate(words):
                if i % words_per_group == 0 and current_group:
                    text = "".join([w.get("text", "") for w in current_group])
                    begin_time = current_group[0].get("begin_time", 0)
                    end_time = current_group[-1].get("end_time", 0)
                    grouped_sentences.append({
                        "text": text,
                        "begin_time": begin_time,
                        "end_time": end_time
                    })
                    current_group = []
                current_group.append(word)

            if current_group:
                text = "".join([w.get("text", "") for w in current_group])
                begin_time = current_group[0].get("begin_time", 0)
                end_time = current_group[-1].get("end_time", 0)
                grouped_sentences.append({
                    "text": text,
                    "begin_time": begin_time,
                    "end_time": end_time
                })

            sentences = grouped_sentences
            print(f"  [OK] 重新分组后: {len(sentences)} 个字幕段")

        assert len(sentences) > 0, "没有生成字幕段"

        # 步骤 6: 生成 SRT 文件
        print(f"\n[步骤6] 生成 SRT 文件")

        def format_time(ms):
            seconds = ms // 1000
            ms_part = ms % 1000
            minutes = seconds // 60
            seconds = seconds % 60
            hours = minutes // 60
            minutes = minutes % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms_part:03d}"

        srt_lines = []
        for i, sent in enumerate(sentences):
            text = sent.get("text", "")
            begin_ms = sent.get("begin_time", 0)
            end_ms = sent.get("end_time", 0)

            srt_lines.append(str(i + 1))
            srt_lines.append(f"{format_time(begin_ms)} --> {format_time(end_ms)}")
            srt_lines.append(text)
            srt_lines.append("")

        srt_content = "\n".join(srt_lines)

        # 保存 SRT 文件
        srt_path = Path(audio_path).with_suffix(".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        assert srt_path.exists(), "SRT 文件保存失败"
        print(f"  [OK] SRT 文件已保存: {srt_path}")

        # 显示统计信息
        print(f"\n{'='*80}")
        print("转录统计")
        print(f"{'='*80}")
        full_text = " ".join([s.get("text", "") for s in sentences])
        print(f"  总句子数: {len(sentences)}")
        print(f"  总字符数: {len(full_text)}")
        print(f"  音频时长: {result.usage.seconds}秒")
        print(f"  SRT 文件: {srt_path}")

        # 显示前 3 个字幕段
        print(f"\n前 3 个字幕段:")
        for i, sent in enumerate(sentences[:3]):
            text = sent.get("text", "")
            begin = sent.get("begin_time", 0)
            end = sent.get("end_time", 0)
            print(f"  [{i+1}] {begin}ms - {end}ms: {text[:40]}...")

        print(f"{'='*80}\n")
