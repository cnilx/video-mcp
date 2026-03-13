"""
图像识别模块测试
"""

import os
import pytest
from pathlib import Path

from src.core.vision import (
    VisionAnalyzer,
    AnalysisType,
    ImageAnalysisResult,
    BatchAnalysisResult,
)
from src.utils.oss import OSSUploader


# 测试图片 URL（公开可访问）
TEST_IMAGE_URL = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"


@pytest.fixture
def api_key():
    """获取 API Key"""
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        pytest.skip("未设置 DASHSCOPE_API_KEY 环境变量")
    return key


@pytest.fixture
def oss_uploader():
    """创建 OSS 上传器"""
    return OSSUploader()


@pytest.fixture
def analyzer(api_key, oss_uploader):
    """创建图像识别分析器"""
    return VisionAnalyzer(
        api_key=api_key,
        model="qwen3-vl-flash",
        oss_uploader=oss_uploader,
    )


class TestVisionAnalyzer:
    """图像识别分析器测试"""

    @pytest.mark.asyncio
    async def test_analyze_image_url(self, analyzer):
        """测试分析图片 URL"""
        result = await analyzer.analyze_image(
            image_source=TEST_IMAGE_URL,
            analysis_type=AnalysisType.GENERAL,
        )

        assert result.success is True
        assert result.image_url == TEST_IMAGE_URL
        assert len(result.description) > 0
        assert result.error is None

        print(f"\n图片描述: {result.description}")

    @pytest.mark.asyncio
    async def test_analyze_image_detailed(self, analyzer):
        """测试详细描述"""
        result = await analyzer.analyze_image(
            image_source=TEST_IMAGE_URL,
            analysis_type=AnalysisType.DETAILED,
        )

        assert result.success is True
        assert len(result.description) > 0
        assert result.analysis_type == AnalysisType.DETAILED

        print(f"\n详细描述: {result.description}")

    @pytest.mark.asyncio
    async def test_analyze_image_custom_prompt(self, analyzer):
        """测试自定义提示词"""
        custom_prompt = "请用一句话描述这张图片。"

        result = await analyzer.analyze_image(
            image_source=TEST_IMAGE_URL,
            custom_prompt=custom_prompt,
        )

        assert result.success is True
        assert len(result.description) > 0

        print(f"\n自定义提示词结果: {result.description}")

    @pytest.mark.asyncio
    async def test_analyze_batch(self, analyzer):
        """测试批量分析"""
        image_urls = [
            TEST_IMAGE_URL,
            "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg",
        ]

        result = await analyzer.analyze_batch(
            image_sources=image_urls,
            analysis_type=AnalysisType.GENERAL,
            max_concurrent=2,
        )

        assert result.success is True
        assert result.total_requested == len(image_urls)
        assert result.total_succeeded > 0
        assert len(result.results) == len(image_urls)

        print(f"\n批量分析结果: 成功 {result.total_succeeded}/{result.total_requested}")
        for i, r in enumerate(result.results):
            if r.success:
                print(f"图片 {i+1}: {r.description[:100]}...")

    @pytest.mark.asyncio
    async def test_analyze_invalid_url(self, analyzer):
        """测试无效 URL"""
        result = await analyzer.analyze_image(
            image_source="https://invalid-url.com/image.jpg",
            analysis_type=AnalysisType.GENERAL,
        )

        # API 可能返回错误或空结果
        assert result.success is False or len(result.description) == 0

    @pytest.mark.asyncio
    async def test_analyze_without_api_key(self, oss_uploader):
        """测试未设置 API Key"""
        analyzer = VisionAnalyzer(
            api_key=None,
            oss_uploader=oss_uploader,
        )

        result = await analyzer.analyze_image(
            image_source=TEST_IMAGE_URL,
            analysis_type=AnalysisType.GENERAL,
        )

        assert result.success is False
        assert "未初始化" in result.error

    @pytest.mark.asyncio
    async def test_analyze_local_image(self, analyzer, tmp_path):
        """测试分析本地图片（需要 OSS）"""
        # 跳过测试如果 OSS 未配置
        if not analyzer.oss_uploader or not analyzer.oss_uploader.bucket:
            pytest.skip("OSS 未配置")

        # 创建一个测试图片（实际应该是真实图片）
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"fake image data")

        result = await analyzer.analyze_image(
            image_source=str(test_image),
            analysis_type=AnalysisType.GENERAL,
        )

        # 由于是假图片，上传可能成功但识别会失败
        # 这里主要测试流程
        print(f"\n本地图片分析结果: success={result.success}, error={result.error}")


class TestAnalysisTypes:
    """测试不同的分析类型"""

    @pytest.mark.asyncio
    async def test_objects_detection(self, analyzer):
        """测试物体识别"""
        result = await analyzer.analyze_image(
            image_source=TEST_IMAGE_URL,
            analysis_type=AnalysisType.OBJECTS,
        )

        assert result.success is True
        print(f"\n物体识别: {result.description}")

    @pytest.mark.asyncio
    async def test_scene_recognition(self, analyzer):
        """测试场景识别"""
        result = await analyzer.analyze_image(
            image_source=TEST_IMAGE_URL,
            analysis_type=AnalysisType.SCENE,
        )

        assert result.success is True
        print(f"\n场景识别: {result.description}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
