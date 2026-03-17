"""
视频下载模块
使用 yt-dlp 实现多平台视频下载功能

支持的视频平台:
- YouTube (youtube.com, youtu.be) - 支持多种质量选项
- Bilibili (bilibili.com, b23.tv) - 支持多种质量选项
- 抖音 (douyin.com, v.douyin.com) - 自动解析短链，提取视频标题

特性:
- 自动平台识别
- 多质量选项 (best/high/medium/low)
- 进度回调支持
- 文件大小限制
- 自动重试机制
- Cookie 支持（可选）
- Windows 文件名兼容
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

import yt_dlp
from loguru import logger


class VideoQuality(str, Enum):
    """视频质量枚举"""
    BEST = "best"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class DownloadProgress:
    """下载进度信息"""
    status: str  # downloading, finished, error
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0  # bytes/s
    eta: int = 0  # seconds
    percent: float = 0.0

    @property
    def downloaded_mb(self) -> float:
        """已下载大小（MB）"""
        return self.downloaded_bytes / (1024 * 1024)

    @property
    def total_mb(self) -> float:
        """总大小（MB）"""
        return self.total_bytes / (1024 * 1024)


@dataclass
class DownloadResult:
    """下载结果"""
    success: bool
    file_path: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[float] = None  # seconds
    file_size: Optional[int] = None  # bytes
    format: Optional[str] = None
    error: Optional[str] = None


class VideoDownloader:
    """视频下载器"""

    # 支持的平台
    SUPPORTED_PLATFORMS = {
        'youtube': ['youtube.com', 'youtu.be'],
        'bilibili': ['bilibili.com', 'b23.tv'],
        'douyin': ['douyin.com', 'v.douyin.com'],
    }

    # 质量配置映射 - 通用格式
    QUALITY_FORMATS = {
        VideoQuality.BEST: 'bestvideo+bestaudio/best',
        VideoQuality.HIGH: 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        VideoQuality.MEDIUM: 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        VideoQuality.LOW: 'bestvideo[height<=480]+bestaudio/best[height<=480]',
    }

    # 平台特定格式配置
    PLATFORM_FORMATS = {
        'youtube': {
            # YouTube 使用更简单的格式选择
            VideoQuality.BEST: 'best',
            VideoQuality.HIGH: 'best[height<=1080]',
            VideoQuality.MEDIUM: 'best[height<=720]',
            VideoQuality.LOW: 'best[height<=480]',
        },
        'bilibili': {
            # B站格式选择 - 避免选择需要会员的格式
            VideoQuality.BEST: 'bestvideo[height<=1080][vcodec^=avc]+bestaudio/best[height<=1080]',
            VideoQuality.HIGH: 'bestvideo[height<=1080][vcodec^=avc]+bestaudio/best[height<=1080]',
            VideoQuality.MEDIUM: 'bestvideo[height<=720][vcodec^=avc]+bestaudio/best[height<=720]',
            VideoQuality.LOW: 'bestvideo[height<=480][vcodec^=avc]+bestaudio/best[height<=480]',
        },
        'douyin': {
            # 抖音使用更简单的格式选择
            VideoQuality.BEST: 'best',
            VideoQuality.HIGH: 'best',
            VideoQuality.MEDIUM: 'best',
            VideoQuality.LOW: 'worst',
        },
    }

    # 格式回退列表 - 当主格式失败时尝试
    FORMAT_FALLBACKS = [
        'best',
        'bestvideo+bestaudio',
        'bestvideo+bestaudio/best',
        'worst',
    ]

    def __init__(
        self,
        output_dir: str = "./downloads",
        max_file_size: Optional[int] = None,  # bytes
        max_retries: int = 3,
        timeout: int = 300,  # seconds
        cookies_from_browser: Optional[str] = None,  # 从浏览器导入 Cookie
        cookiefile: Optional[str] = None,  # Cookie 文件路径
    ):
        """
        初始化视频下载器

        Args:
            output_dir: 下载文件保存目录
            max_file_size: 最大文件大小限制（字节），None 表示不限制
            max_retries: 下载失败最大重试次数
            timeout: 下载超时时间（秒）
            cookies_from_browser: 从浏览器导入 Cookie (chrome, edge, firefox, safari 等)
            cookiefile: Cookie 文件路径
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max_file_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.cookies_from_browser = cookies_from_browser
        self.cookiefile = cookiefile
        self._progress_callback: Optional[Callable[[DownloadProgress], None]] = None

    def set_progress_callback(self, callback: Callable[[DownloadProgress], None]):
        """设置下载进度回调函数"""
        self._progress_callback = callback

    def _progress_hook(self, d: Dict[str, Any]):
        """yt-dlp 进度钩子"""
        if not self._progress_callback:
            return

        status = d.get('status', 'unknown')
        progress = DownloadProgress(status=status)

        if status == 'downloading':
            progress.downloaded_bytes = d.get('downloaded_bytes', 0)
            progress.total_bytes = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            progress.speed = d.get('speed', 0.0) or 0.0
            progress.eta = d.get('eta', 0) or 0

            if progress.total_bytes > 0:
                progress.percent = (progress.downloaded_bytes / progress.total_bytes) * 100

        elif status == 'finished':
            progress.percent = 100.0

        self._progress_callback(progress)

    def _get_ydl_opts(
        self,
        quality: VideoQuality = VideoQuality.LOW,
        format_type: str = 'mp4',
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取 yt-dlp 配置选项

        Args:
            quality: 视频质量
            format_type: 输出格式
            platform: 平台名称（用于平台特定配置）

        Returns:
            yt-dlp 配置字典
        """
        # 选择格式字符串
        if platform and platform in self.PLATFORM_FORMATS:
            format_str = self.PLATFORM_FORMATS[platform].get(quality, 'best')
        else:
            format_str = self.QUALITY_FORMATS.get(quality, 'best')

        opts = {
            'format': format_str,
            'outtmpl': str(self.output_dir / '%(title).20s.%(ext)s'),  # 限制标题长度为20字符，避免中文字符超过文件系统限制
            'progress_hooks': [self._progress_hook],
            'socket_timeout': self.timeout,
            'retries': self.max_retries,
            'fragment_retries': self.max_retries,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'merge_output_format': format_type,
            # 添加更好的 User-Agent
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # Windows 文件名兼容性
            'windowsfilenames': True,  # 移除 Windows 不支持的字符
            'restrictfilenames': False,  # 保留 Unicode 字符，但移除特殊符号
        }

        # 添加 Cookie 支持
        if self.cookies_from_browser:
            opts['cookiesfrombrowser'] = (self.cookies_from_browser,)
        elif self.cookiefile:
            opts['cookiefile'] = self.cookiefile

        # 对于抖音，强制使用 Generic 提取器
        if platform == 'douyin':
            opts['default_search'] = 'auto'
            opts['force_generic_extractor'] = True

        # 平台特定配置
        if platform == 'bilibili':
            # Bilibili 特定配置 - 防止 WBI 签名失败和412错误
            opts.update({
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/',
                    'Origin': 'https://www.bilibili.com',
                    'Accept': '*/*',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Sec-Ch-Ua': '"Chromium";v="131", "Not_A Brand";v="24"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-site',
                    # 添加关键的Cookie头，即使为空也要发送
                    'Cookie': '',
                },
                # 添加更宽松的错误处理和重试
                'ignoreerrors': False,
                'nocheckcertificate': True,
                # 增加重试次数
                'extractor_retries': 5,
                'fragment_retries': 10,
                # 添加延迟避免触发反爬
                'sleep_interval': 1,
                'max_sleep_interval': 3,
                # 尝试从浏览器获取Cookie（如果可用）
                'cookiesfrombrowser': None,  # 可以设置为 ('chrome',) 或 ('edge',) 等
            })
        elif platform == 'douyin':
            # 抖音特定配置
            # 参考成功案例：让短链解析到 douyinvod.com 直链，使用 Generic 提取器
            opts.update({
                'http_headers': {
                    # 使用标准桌面浏览器 User-Agent
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.douyin.com/',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                },
                # 允许跟随重定向，让短链解析到真实资源地址
                'nocheckcertificate': True,
            })
        elif platform == 'youtube':
            # YouTube 特定配置
            opts.update({
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'skip': ['hls', 'dash'],
                    }
                },
            })

        # 文件大小限制
        if self.max_file_size:
            opts['max_filesize'] = self.max_file_size

        return opts

    def detect_platform(self, url: str) -> Optional[str]:
        """
        检测视频平台

        Args:
            url: 视频URL

        Returns:
            平台名称，如果不支持则返回 None
        """
        url_lower = url.lower()
        for platform, domains in self.SUPPORTED_PLATFORMS.items():
            if any(domain in url_lower for domain in domains):
                return platform
        return None

    async def _resolve_douyin_url(self, url: str) -> Optional[tuple[str, str]]:
        """
        解析抖音短链接，获取真实视频播放 URL 和标题

        Args:
            url: 抖音短链接或完整链接

        Returns:
            (视频播放 URL, 视频标题) 元组，失败返回 None
        """
        import httpx
        import json
        import re

        try:
            # 使用移动端 User-Agent 访问，获取包含视频信息的页面
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }

            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                final_url = str(response.url)
                html = response.text

                logger.info(f"短链接解析: {url} -> {final_url}")

                # 从页面中提取 JSON 数据
                # 抖音移动端页面包含 window._ROUTER_DATA
                json_pattern = r'<script[^>]*>\s*window\._ROUTER_DATA\s*=\s*({.*?})\s*</script>'
                matches = re.findall(json_pattern, html, re.DOTALL)

                if not matches:
                    logger.warning("未找到视频数据")
                    return None

                # 解析 JSON
                data = json.loads(matches[0])

                # 提取视频信息
                # 路径: loaderData -> video_(id)/page -> videoInfoRes -> item_list[0]
                try:
                    item = data['loaderData']['video_(id)/page']['videoInfoRes']['item_list'][0]

                    # 提取视频播放地址
                    video_info = item['video']
                    play_addr = video_info['play_addr']['url_list'][0]

                    # 提取视频标题（描述）
                    title = item.get('desc', 'douyin_video')
                    # 清理标题中的特殊字符
                    title = re.sub(r'[<>:"/\\|?*]', '', title)  # 移除 Windows 不支持的字符
                    title = title.strip()[:100]  # 限制长度

                    if not title:
                        title = 'douyin_video'

                    logger.info(f"提取到视频播放地址: {play_addr[:100]}...")
                    logger.info(f"提取到视频标题: {title}")
                    return (play_addr, title)

                except (KeyError, IndexError) as e:
                    logger.error(f"提取视频信息失败: {str(e)}")
                    return None

        except Exception as e:
            logger.error(f"解析抖音 URL 失败: {str(e)}")
            return None

    async def download(
        self,
        url: str,
        quality: VideoQuality = VideoQuality.LOW,
        format_type: str = 'mp4',
    ) -> DownloadResult:
        """
        下载视频

        Args:
            url: 视频URL
            quality: 视频质量
            format_type: 输出格式

        Returns:
            下载结果
        """
        platform = self.detect_platform(url)
        if not platform:
            logger.warning(f"未识别的视频平台: {url}")

        logger.info(f"开始下载视频: {url} (质量: {quality}, 格式: {format_type})")

        # 对于抖音，先解析出真实的视频播放地址和标题
        download_url = url
        douyin_title = None
        if platform == 'douyin':
            logger.info("检测到抖音链接，正在解析视频播放地址...")
            result = await self._resolve_douyin_url(url)
            if result:
                download_url, douyin_title = result
                logger.info(f"使用解析后的视频地址下载")
            else:
                logger.warning("解析视频地址失败，尝试使用原始 URL")

        ydl_opts = self._get_ydl_opts(quality, format_type, platform)

        # 如果是抖音且有标题，使用自定义文件名（限制长度）
        if platform == 'douyin' and douyin_title:
            # 限制标题长度为20字符，避免文件名过长
            safe_title = douyin_title[:20]
            ydl_opts['outtmpl'] = str(self.output_dir / f'{safe_title}.%(ext)s')

        try:
            # 在线程池中运行 yt-dlp（避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._download_sync,
                download_url,
                ydl_opts,
                platform
            )
            return result

        except Exception as e:
            logger.error(f"下载失败: {str(e)}")
            return DownloadResult(
                success=False,
                error=str(e)
            )

    def _download_sync(self, url: str, ydl_opts: Dict[str, Any], platform: Optional[str] = None) -> DownloadResult:
        """
        同步下载（在线程池中执行）

        Args:
            url: 视频URL
            ydl_opts: yt-dlp 配置
            platform: 平台名称

        Returns:
            下载结果
        """
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 获取视频信息
                info = ydl.extract_info(url, download=False)
                if not info:
                    return DownloadResult(
                        success=False,
                        error="无法获取视频信息"
                    )

                # 检查文件大小
                filesize = info.get('filesize') or info.get('filesize_approx')
                if self.max_file_size and filesize and filesize > self.max_file_size:
                    return DownloadResult(
                        success=False,
                        error=f"文件大小 ({filesize / (1024*1024):.2f}MB) 超过限制 ({self.max_file_size / (1024*1024):.2f}MB)"
                    )

                # 下载视频
                try:
                    ydl.download([url])
                except yt_dlp.utils.DownloadError as e:
                    # 如果下载失败，尝试使用回退格式
                    error_msg = str(e)
                    if 'format' in error_msg.lower() or 'not available' in error_msg.lower():
                        logger.warning(f"主格式下载失败，尝试回退格式: {error_msg}")
                        return self._download_with_fallback(url, ydl_opts, platform)
                    raise

                # 构建文件路径
                filename = ydl.prepare_filename(info)
                file_path = Path(filename)

                # 检查文件是否存在
                if not file_path.exists():
                    return DownloadResult(
                        success=False,
                        error="下载完成但文件不存在"
                    )

                return DownloadResult(
                    success=True,
                    file_path=str(file_path),
                    title=info.get('title'),
                    duration=info.get('duration'),
                    file_size=file_path.stat().st_size,
                    format=info.get('ext'),
                )

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"yt-dlp 下载错误: {error_msg}")

            # 如果是格式问题，尝试回退
            if 'format' in error_msg.lower() or 'not available' in error_msg.lower():
                logger.info("尝试使用回退格式重新下载")
                return self._download_with_fallback(url, ydl_opts, platform)

            return DownloadResult(
                success=False,
                error=f"下载错误: {error_msg}"
            )
        except Exception as e:
            logger.error(f"未知错误: {str(e)}")
            return DownloadResult(
                success=False,
                error=f"未知错误: {str(e)}"
            )

    def _download_with_fallback(self, url: str, base_opts: Dict[str, Any], platform: Optional[str] = None) -> DownloadResult:
        """
        使用回退格式尝试下载

        Args:
            url: 视频URL
            base_opts: 基础配置
            platform: 平台名称

        Returns:
            下载结果
        """
        for fallback_format in self.FORMAT_FALLBACKS:
            try:
                logger.info(f"尝试回退格式: {fallback_format}")

                # 复制配置并修改格式
                opts = base_opts.copy()
                opts['format'] = fallback_format

                # 对于某些平台，使用更宽松的配置
                if platform in ['douyin', 'youtube']:
                    opts['ignoreerrors'] = True
                    opts['no_check_certificate'] = True

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        continue

                    # 尝试下载
                    ydl.download([url])

                    # 构建文件路径
                    filename = ydl.prepare_filename(info)
                    file_path = Path(filename)

                    if file_path.exists():
                        logger.info(f"使用回退格式 {fallback_format} 下载成功")
                        return DownloadResult(
                            success=True,
                            file_path=str(file_path),
                            title=info.get('title'),
                            duration=info.get('duration'),
                            file_size=file_path.stat().st_size,
                            format=info.get('ext'),
                        )

            except Exception as e:
                logger.warning(f"回退格式 {fallback_format} 失败: {str(e)}")
                continue

        return DownloadResult(
            success=False,
            error="所有格式尝试均失败"
        )

    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        获取视频信息（不下载）

        Args:
            url: 视频URL

        Returns:
            视频信息字典，失败返回 None
        """
        try:
            platform = self.detect_platform(url)

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'ignoreerrors': True,  # 忽略错误，继续获取信息
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }

            # 平台特定配置 - 不指定格式，避免格式错误
            if platform == 'youtube':
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'skip': ['hls', 'dash'],
                    }
                }

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                None,
                self._get_info_sync,
                url,
                ydl_opts
            )
            return info

        except Exception as e:
            logger.error(f"获取视频信息失败: {str(e)}")
            return None

    def _get_info_sync(self, url: str, ydl_opts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """同步获取视频信息"""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            logger.error(f"获取信息错误: {str(e)}")
            return None
