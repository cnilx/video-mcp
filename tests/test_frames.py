"""视频帧处理模块测试"""
import pytest
import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

from src.core.frames import (
    FrameExtractor,
    FrameConfig,
    FrameInfo,
    ExtractionResult,
    ImageFormat,
)
from src.utils.oss import OSSUploader

# 加载环境变量
load_dotenv()

# 测试视频路径（使用 downloads 目录中已有的视频）
TEST_VIDEO = "downloads/底层穷人为什么完不成原始资本积累？.mp4"


@pytest.fixture
def frame_extractor():
    """创建默认帧提取器"""
    return FrameExtractor()


@pytest.fixture
def frame_config():
    """创建自定义配置"""
    return FrameConfig(
        image_format=ImageFormat.JPEG,
        quality=90,
        max_width=1280,
        max_concurrent=2,
    )

class TestFrameConfig:
    """测试帧配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = FrameConfig()
        assert config.image_format == ImageFormat.JPEG
        assert config.quality == 85
        assert config.max_width is None
        assert config.max_height is None
        assert config.max_concurrent == 4

    def test_custom_config(self, frame_config):
        """测试自定义配置"""
        assert frame_config.quality == 90
        assert frame_config.max_width == 1280
        assert frame_config.max_concurrent == 2


class TestQualityConversion:
    """测试质量值转换"""

    def test_quality_to_qscale_high(self):
        """高质量 -> 低 qscale"""
        assert FrameExtractor._quality_to_qscale(100) == 1

    def test_quality_to_qscale_low(self):
        """低质量 -> 高 qscale"""
        result = FrameExtractor._quality_to_qscale(1)
        assert result >= 28  # 接近最大值

    def test_quality_to_qscale_mid(self):
        """中等质量"""
        result = FrameExtractor._quality_to_qscale(50)
        assert 1 <= result <= 31

    def test_quality_to_qscale_clamp(self):
        """超出范围的值应被钳制"""
        low = FrameExtractor._quality_to_qscale(0)
        high = FrameExtractor._quality_to_qscale(200)
        assert low >= 28  # 接近最大值
        assert high == 1   # 最高质量


class TestExtractFramesEdgeCases:
    """测试帧提取边界情况"""

    @pytest.mark.asyncio
    async def test_nonexistent_video(self, frame_extractor):
        """测试不存在的视频文件"""
        result = await frame_extractor.extract_frames(
            "nonexistent.mp4", "/tmp/out", [1.0, 2.0]
        )
        assert not result.success
        assert "不存在" in result.error
        assert result.total_requested == 2

    @pytest.mark.asyncio
    async def test_empty_timestamps(self, frame_extractor):
        """测试空时间戳列表"""
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        result = await frame_extractor.extract_frames(
            TEST_VIDEO, "/tmp/out", []
        )
        # 空列表 -> 所有时间戳超出范围
        assert not result.success


class TestExtractFramesIntegration:
    """集成测试 - 需要真实视频文件"""

    @pytest.mark.asyncio
    async def test_extract_single_frame(self):
        """测试提取单帧"""
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = FrameExtractor()
            result = await extractor.extract_frames(
                TEST_VIDEO, tmpdir, [5.0]
            )

            assert result.success
            assert result.total_requested == 1
            assert result.total_extracted == 1
            assert len(result.frames) == 1
            assert result.video_duration > 0

            frame = result.frames[0]
            assert frame.timestamp == 5.0
            assert Path(frame.file_path).exists()
            assert frame.file_size > 0
            assert frame.width > 0
            assert frame.height > 0

            print(f"\n提取帧: {frame.width}x{frame.height}, "
                  f"{frame.file_size/1024:.1f}KB")

    @pytest.mark.asyncio
    async def test_extract_multiple_frames(self):
        """测试批量提取多帧"""
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = FrameExtractor()
            timestamps = [2.0, 10.0, 30.0, 60.0]
            result = await extractor.extract_frames(
                TEST_VIDEO, tmpdir, timestamps
            )

            assert result.success
            assert result.total_requested == 4
            assert result.total_extracted > 0

            for frame in result.frames:
                assert Path(frame.file_path).exists()
                print(f"  帧 {frame.index}: {frame.timestamp:.2f}s "
                      f"({frame.width}x{frame.height}, "
                      f"{frame.file_size/1024:.1f}KB)")

    @pytest.mark.asyncio
    async def test_extract_with_scale(self):
        """测试带缩放的帧提取"""
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        with tempfile.TemporaryDirectory() as tmpdir:
            config = FrameConfig(max_width=640)
            extractor = FrameExtractor(config=config)
            result = await extractor.extract_frames(
                TEST_VIDEO, tmpdir, [5.0]
            )

            assert result.success
            frame = result.frames[0]
            assert frame.width <= 640
            print(f"\n缩放后: {frame.width}x{frame.height}")

    @pytest.mark.asyncio
    async def test_extract_png_format(self):
        """测试 PNG 格式输出"""
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        with tempfile.TemporaryDirectory() as tmpdir:
            config = FrameConfig(image_format=ImageFormat.PNG)
            extractor = FrameExtractor(config=config)
            result = await extractor.extract_frames(
                TEST_VIDEO, tmpdir, [5.0]
            )

            assert result.success
            assert result.frames[0].file_path.endswith(".png")

    @pytest.mark.asyncio
    async def test_invalid_timestamps_filtered(self):
        """测试无效时间戳被过滤"""
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = FrameExtractor()
            # 包含一个超大时间戳和一个负数
            timestamps = [-1.0, 5.0, 999999.0]
            result = await extractor.extract_frames(
                TEST_VIDEO, tmpdir, timestamps
            )

            assert result.success
            assert result.total_requested == 3
            assert result.total_extracted == 1  # 只有 5.0 有效


class TestOSSUpload:
    """测试 OSS 上传集成"""

    @pytest.mark.asyncio
    async def test_extract_and_upload(self):
        """测试提取帧并上传到 OSS"""
        if not Path(TEST_VIDEO).exists():
            pytest.skip(f"测试视频不存在: {TEST_VIDEO}")

        # 检查 OSS 配置
        if not all([
            os.getenv("OSS_ACCESS_KEY_ID"),
            os.getenv("OSS_ACCESS_KEY_SECRET"),
            os.getenv("OSS_ENDPOINT"),
            os.getenv("OSS_BUCKET_NAME"),
        ]):
            pytest.skip("未配置 OSS 相关环境变量")

        with tempfile.TemporaryDirectory() as tmpdir:
            oss = OSSUploader()
            extractor = FrameExtractor(oss_uploader=oss)
            result = await extractor.extract_frames(
                TEST_VIDEO, tmpdir, [5.0, 15.0]
            )

            assert result.success
            for frame in result.frames:
                assert frame.oss_url, f"帧 {frame.index} 缺少 OSS URL"
                print(f"  帧 {frame.index}: {frame.oss_url}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
