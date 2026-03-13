"""
图像识别模块
集成阿里百炼 Qwen-VL 进行图像分析和描述生成

特性:
- 支持单张和批量图像分析
- 支持本地文件和 URL
- 自动上传本地图片到 OSS
- 结构化的识别结果
- 失败重试机制
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Union
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger
import dashscope

from ..utils.oss import OSSUploader


class AnalysisType(str, Enum):
    """分析类型枚举"""
    GENERAL = "general"  # 通用描述
    DETAILED = "detailed"  # 详细描述
    OBJECTS = "objects"  # 物体识别
    TEXT = "text"  # 文字识别（OCR）
    SCENE = "scene"  # 场景识别
    SMART = "smart"  # 智能识别（自动判断内容类型）


@dataclass
class ImageAnalysisResult:
    """单张图像分析结果"""
    success: bool
    image_path: str = ""
    image_url: str = ""
    description: str = ""
    analysis_type: AnalysisType = AnalysisType.GENERAL
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class BatchAnalysisResult:
    """批量图像分析结果"""
    success: bool
    results: List[ImageAnalysisResult] = field(default_factory=list)
    total_requested: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    error: Optional[str] = None


class VisionAnalyzer:
    """图像识别分析器"""

    # 默认提示词模板
    DEFAULT_PROMPTS = {
        AnalysisType.GENERAL: "请描述这张图片的内容。",
        AnalysisType.DETAILED: "请详细描述这张图片，包括场景、物体、人物、动作、颜色、氛围等所有细节。",
        AnalysisType.OBJECTS: "请识别并列出图片中的所有物体。",
        AnalysisType.TEXT: "请识别并提取图片中的所有文字内容。",
        AnalysisType.SCENE: "请描述图片的场景类型和环境特征。",
        AnalysisType.SMART: (
            "请先判断这张图片属于以下哪种类型，然后按对应要求输出：\n"
            "\n"
            "1. 如果是图表（柱状图、折线图、饼图、表格、数据可视化等）：\n"
            "   请提取图表的标题、坐标轴含义、所有数据项及其数值，并总结图表反映的趋势或结论。\n"
            "\n"
            "2. 如果是PPT/演示文稿/幻灯片：\n"
            "   请提取幻灯片的标题、所有文字内容、要点列表，并概括该页的核心信息。\n"
            "\n"
            "3. 如果是代码/终端/IDE截图：\n"
            "   请识别编程语言，提取完整代码内容，并简要说明代码的功能。\n"
            "\n"
            "4. 如果是文档/网页/文章截图：\n"
            "   请提取所有可见的文字内容，保留原有的层级结构。\n"
            "\n"
            "5. 如果是普通照片/视频截图/实拍画面：\n"
            "   请描述画面中的场景、人物、动作和关键元素。\n"
            "\n"
            "请在回答开头用【类型：xxx】标注你判断的图片类型，然后给出对应的分析内容。"
        ),
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        model: str = "qwen3-vl-flash",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        oss_uploader: Optional[OSSUploader] = None,
        max_retries: int = 3,
    ):
        """
        初始化图像识别分析器

        Args:
            api_key: 阿里百炼 API Key
            base_url: API 基础 URL
            model: 视觉模型名称（qwen3-vl-plus, qwen3-vl-flash, qwen-vl-max, qwen-vl-plus）
            max_tokens: 最大 token 数
            temperature: 温度参数
            oss_uploader: OSS 上传器实例
            max_retries: 失败重试次数
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.oss_uploader = oss_uploader
        self.max_retries = max_retries

        if not self.api_key:
            logger.warning("未提供 API Key，图像识别功能将不可用")
        else:
            # 设置 DashScope API Key 和 base_url
            dashscope.api_key = self.api_key
            dashscope.base_http_api_url = self.base_url
            logger.info(f"图像识别初始化成功: {self.model}")

        # 如果未提供 OSS 上传器，创建一个
        if self.oss_uploader is None:
            self.oss_uploader = OSSUploader()
            if not self.oss_uploader.bucket:
                logger.warning("OSS 未配置，本地图片将无法分析")

    async def analyze_image(
        self,
        image_source: str,
        analysis_type: AnalysisType = AnalysisType.GENERAL,
        custom_prompt: Optional[str] = None,
    ) -> ImageAnalysisResult:
        """
        分析单张图像

        Args:
            image_source: 图片路径或 URL
            analysis_type: 分析类型
            custom_prompt: 自定义提示词（覆盖默认提示词）

        Returns:
            ImageAnalysisResult
        """
        if not self.api_key:
            return ImageAnalysisResult(
                success=False,
                image_path=image_source,
                error="图像识别未初始化",
            )

        try:
            # 判断是本地文件还是 URL
            is_local = not image_source.startswith(("http://", "https://"))

            if is_local:
                # 本地文件需要上传到 OSS
                image_url = await self._upload_image_to_oss(image_source)
                if not image_url:
                    return ImageAnalysisResult(
                        success=False,
                        image_path=image_source,
                        error="上传图片到 OSS 失败",
                    )
            else:
                image_url = image_source

            # 获取提示词
            prompt = custom_prompt or self.DEFAULT_PROMPTS.get(
                analysis_type, self.DEFAULT_PROMPTS[AnalysisType.GENERAL]
            )

            # 调用 API 进行分析
            description = await self._call_vision_api(image_url, prompt)

            if not description:
                return ImageAnalysisResult(
                    success=False,
                    image_path=image_source if is_local else "",
                    image_url=image_url,
                    error="API 调用失败或返回空结果",
                )

            logger.info(f"图像分析成功: {image_source[:50]}...")

            return ImageAnalysisResult(
                success=True,
                image_path=image_source if is_local else "",
                image_url=image_url,
                description=description,
                analysis_type=analysis_type,
            )

        except Exception as e:
            logger.error(f"图像分析失败: {str(e)}")
            return ImageAnalysisResult(
                success=False,
                image_path=image_source,
                error=str(e),
            )

    async def analyze_batch(
        self,
        image_sources: List[str],
        analysis_type: AnalysisType = AnalysisType.GENERAL,
        custom_prompt: Optional[str] = None,
        max_concurrent: int = 3,
    ) -> BatchAnalysisResult:
        """
        批量分析图像

        Args:
            image_sources: 图片路径或 URL 列表
            analysis_type: 分析类型
            custom_prompt: 自定义提示词
            max_concurrent: 最大并发数

        Returns:
            BatchAnalysisResult
        """
        if not self.api_key:
            return BatchAnalysisResult(
                success=False,
                total_requested=len(image_sources),
                error="图像识别未初始化",
            )

        try:
            logger.info(f"开始批量分析 {len(image_sources)} 张图片")

            # 使用信号量控制并发
            semaphore = asyncio.Semaphore(max_concurrent)

            async def _analyze_with_sem(img_src: str) -> ImageAnalysisResult:
                async with semaphore:
                    return await self.analyze_image(img_src, analysis_type, custom_prompt)

            # 并发分析
            tasks = [_analyze_with_sem(img) for img in image_sources]
            results = await asyncio.gather(*tasks)

            # 统计结果
            succeeded = sum(1 for r in results if r.success)
            failed = len(results) - succeeded

            logger.info(f"批量分析完成: {succeeded}/{len(image_sources)} 成功")

            return BatchAnalysisResult(
                success=succeeded > 0,
                results=results,
                total_requested=len(image_sources),
                total_succeeded=succeeded,
                total_failed=failed,
            )

        except Exception as e:
            logger.error(f"批量分析失败: {str(e)}")
            return BatchAnalysisResult(
                success=False,
                total_requested=len(image_sources),
                error=str(e),
            )

    async def analyze_frames(
        self,
        frame_infos: List,  # List[FrameInfo] from frames.py
        analysis_type: AnalysisType = AnalysisType.GENERAL,
        custom_prompt: Optional[str] = None,
        max_concurrent: int = 3,
    ) -> BatchAnalysisResult:
        """
        分析视频帧（使用 FrameInfo 对象）

        Args:
            frame_infos: FrameInfo 对象列表
            analysis_type: 分析类型
            custom_prompt: 自定义提示词
            max_concurrent: 最大并发数

        Returns:
            BatchAnalysisResult
        """
        # 提取 OSS URL 或本地路径
        image_sources = []
        for frame in frame_infos:
            if frame.oss_url:
                image_sources.append(frame.oss_url)
            elif frame.file_path:
                image_sources.append(frame.file_path)
            else:
                logger.warning(f"帧 {frame.index} 没有可用的图片源")

        if not image_sources:
            return BatchAnalysisResult(
                success=False,
                total_requested=len(frame_infos),
                error="没有可用的图片源",
            )

        # 批量分析
        result = await self.analyze_batch(
            image_sources,
            analysis_type,
            custom_prompt,
            max_concurrent,
        )

        # 将分析结果关联到 FrameInfo
        for i, frame in enumerate(frame_infos):
            if i < len(result.results):
                analysis_result = result.results[i]
                # 将描述添加到 frame 的 metadata（如果 FrameInfo 支持）
                if hasattr(frame, 'metadata'):
                    frame.metadata = frame.metadata or {}
                    frame.metadata['description'] = analysis_result.description
                    frame.metadata['analysis_type'] = analysis_result.analysis_type.value

        return result

    # === 内部方法 ===

    async def _upload_image_to_oss(self, image_path: str) -> Optional[str]:
        """上传图片到 OSS"""
        if not self.oss_uploader or not self.oss_uploader.bucket:
            logger.error("OSS 未配置，无法上传图片")
            return None

        try:
            image_path_obj = Path(image_path)
            if not image_path_obj.exists():
                logger.error(f"图片文件不存在: {image_path}")
                return None

            logger.info(f"上传图片到 OSS: {image_path}")

            loop = asyncio.get_event_loop()
            url = await loop.run_in_executor(
                None,
                lambda: self.oss_uploader.upload_file(image_path, folder="images"),
            )

            if url:
                logger.info(f"图片上传成功: {url}")
            else:
                logger.error("图片上传失败")

            return url

        except Exception as e:
            logger.error(f"上传图片异常: {str(e)}")
            return None

    async def _call_vision_api(
        self,
        image_url: str,
        prompt: str,
    ) -> Optional[str]:
        """
        调用视觉 API

        Args:
            image_url: 图片 URL
            prompt: 提示词

        Returns:
            描述文本，失败返回 None
        """
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"调用视觉 API (尝试 {attempt + 1}/{self.max_retries})")

                # 构建消息（使用 DashScope 格式）
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"image": image_url},
                            {"text": prompt},
                        ],
                    }
                ]

                # 调用 API
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: dashscope.MultiModalConversation.call(
                        api_key=self.api_key,
                        model=self.model,
                        messages=messages,
                    ),
                )

                # 检查响应状态
                if response.status_code != 200:
                    error_msg = (
                        f"API 调用失败: status={response.status_code}, "
                        f"code={response.code}, message={response.message}, "
                        f"model={self.model}, base_url={self.base_url}"
                    )
                    logger.error(error_msg)

                    # 如果不是最后一次尝试，等待后重试
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1 * (attempt + 1))
                    continue

                # 提取结果
                if response.output and response.output.get("choices"):
                    choices = response.output["choices"]
                    if choices and len(choices) > 0:
                        message = choices[0].get("message", {})
                        content = message.get("content", [])
                        if content and len(content) > 0:
                            text = content[0].get("text", "")
                            if text:
                                return text.strip()

                logger.warning("API 返回空结果")

                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))

            except Exception as e:
                logger.error(f"API 调用失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")

                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    logger.error("所有重试均失败")

        return None
