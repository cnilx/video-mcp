"""
视频下载模块测试
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.core.downloader import (
    VideoDownloader,
    VideoQuality,
    DownloadProgress,
    DownloadResult,
)


@pytest.fixture
def temp_output_dir(tmp_path):
    """临时输出目录"""
    return str(tmp_path / "downloads")


@pytest.fixture
def downloader(temp_output_dir):
    """视频下载器实例"""
    return VideoDownloader(
        output_dir=temp_output_dir,
        max_file_size=100 * 1024 * 1024,  # 100MB
        max_retries=2,
        timeout=60,
    )


class TestVideoDownloader:
    """视频下载器测试"""

    def test_init(self, downloader, temp_output_dir):
        """测试初始化"""
        assert downloader.output_dir == Path(temp_output_dir)
        assert downloader.output_dir.exists()
        assert downloader.max_file_size == 100 * 1024 * 1024
        assert downloader.max_retries == 2
        assert downloader.timeout == 60

    def test_detect_platform(self, downloader):
        """测试平台检测"""
        # YouTube
        assert downloader.detect_platform("https://www.youtube.com/watch?v=xxx") == "youtube"
        assert downloader.detect_platform("https://youtu.be/xxx") == "youtube"

        # Bilibili
        assert downloader.detect_platform("https://www.bilibili.com/video/BVxxx") == "bilibili"
        assert downloader.detect_platform("https://b23.tv/xxx") == "bilibili"

        # Douyin
        assert downloader.detect_platform("https://www.douyin.com/video/xxx") == "douyin"

        # TikTok
        assert downloader.detect_platform("https://www.tiktok.com/@user/video/xxx") == "tiktok"

        # 不支持的平台
        assert downloader.detect_platform("https://example.com/video") is None

    def test_progress_callback(self, downloader):
        """测试进度回调"""
        progress_data = []

        def callback(progress: DownloadProgress):
            progress_data.append(progress)

        downloader.set_progress_callback(callback)

        # 模拟下载进度
        downloader._progress_hook({
            'status': 'downloading',
            'downloaded_bytes': 50 * 1024 * 1024,
            'total_bytes': 100 * 1024 * 1024,
            'speed': 1024 * 1024,
            'eta': 50,
        })

        assert len(progress_data) == 1
        progress = progress_data[0]
        assert progress.status == 'downloading'
        assert progress.downloaded_bytes == 50 * 1024 * 1024
        assert progress.total_bytes == 100 * 1024 * 1024
        assert progress.percent == 50.0

    def test_get_ydl_opts(self, downloader):
        """测试 yt-dlp 配置生成"""
        opts = downloader._get_ydl_opts(
            quality=VideoQuality.HIGH,
            format_type='mp4'
        )

        assert 'format' in opts
        assert 'outtmpl' in opts
        assert 'progress_hooks' in opts
        assert opts['socket_timeout'] == 60
        assert opts['retries'] == 2
        assert opts['max_filesize'] == 100 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_download_success(self, downloader, temp_output_dir):
        """测试成功下载"""
        mock_info = {
            'title': 'Test Video',
            'duration': 120,
            'ext': 'mp4',
            'filesize': 10 * 1024 * 1024,
        }

        # 创建模拟的下载文件
        test_file = Path(temp_output_dir) / "Test Video.mp4"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("test content")

        with patch('yt_dlp.YoutubeDL') as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.return_value = mock_info
            mock_ydl.prepare_filename.return_value = str(test_file)
            mock_ydl.download.return_value = None

            result = await downloader.download(
                "https://www.youtube.com/watch?v=test",
                quality=VideoQuality.HIGH
            )

            assert result.success is True
            assert result.file_path == str(test_file)
            assert result.title == "Test Video"
            assert result.duration == 120

    @pytest.mark.asyncio
    async def test_download_file_too_large(self, downloader):
        """测试文件过大"""
        mock_info = {
            'title': 'Large Video',
            'filesize': 200 * 1024 * 1024,  # 200MB，超过限制
        }

        with patch('yt_dlp.YoutubeDL') as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.return_value = mock_info

            result = await downloader.download("https://www.youtube.com/watch?v=test")

            assert result.success is False
            assert "超过限制" in result.error

    @pytest.mark.asyncio
    async def test_get_video_info(self, downloader):
        """测试获取视频信息"""
        mock_info = {
            'title': 'Test Video',
            'duration': 120,
            'ext': 'mp4',
            'filesize': 10 * 1024 * 1024,
            'description': 'Test description',
        }

        with patch('yt_dlp.YoutubeDL') as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.return_value = mock_info

            info = await downloader.get_video_info("https://www.youtube.com/watch?v=test")

            assert info is not None
            assert info['title'] == 'Test Video'
            assert info['duration'] == 120


class TestDownloadProgress:
    """下载进度测试"""

    def test_progress_properties(self):
        """测试进度属性"""
        progress = DownloadProgress(
            status='downloading',
            downloaded_bytes=50 * 1024 * 1024,
            total_bytes=100 * 1024 * 1024,
        )

        assert progress.downloaded_mb == 50.0
        assert progress.total_mb == 100.0


class TestDownloadResult:
    """下载结果测试"""

    def test_success_result(self):
        """测试成功结果"""
        result = DownloadResult(
            success=True,
            file_path="/path/to/video.mp4",
            title="Test Video",
            duration=120,
            file_size=10 * 1024 * 1024,
            format="mp4",
        )

        assert result.success is True
        assert result.file_path == "/path/to/video.mp4"
        assert result.error is None

    def test_error_result(self):
        """测试错误结果"""
        result = DownloadResult(
            success=False,
            error="Download failed"
        )

        assert result.success is False
        assert result.error == "Download failed"
        assert result.file_path is None
