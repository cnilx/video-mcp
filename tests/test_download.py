"""
视频下载集成测试工具
支持从内置URL列表或命令行参数进行实际下载测试

使用方法:
    # 测试内置URL（YouTube + Bilibili）
    python tests/test_download.py

    # 测试单个URL
    python tests/test_download.py https://www.youtube.com/watch?v=xxxxx

    # 指定下载质量
    python tests/test_download.py --quality low
    python tests/test_download.py <url> --quality high

    # 查看帮助
    python tests/test_download.py --help
"""

import sys
import asyncio
from pathlib import Path
from typing import List

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.downloader import VideoDownloader, VideoQuality, DownloadProgress, DownloadResult


# 内置测试URL列表
DEFAULT_TEST_URLS = [

    # YouTube 测试视频
    "https://www.youtube.com/watch?v=STYdK9myBsE",

    # Bilibili 测试视频
    "https://www.bilibili.com/video/BV1x9PWzuEKc/",

    # 抖音 测试视频
    "https://v.douyin.com/hCKa72AHs0c/",

    "https://v.douyin.com/b4K0rHZc8xo/"
]


def progress_callback(progress: DownloadProgress):
    """下载进度回调"""
    if progress.status == 'downloading':
        print(f"\r  下载中: {progress.percent:.1f}% "
              f"({progress.downloaded_mb:.1f}MB / {progress.total_mb:.1f}MB) "
              f"速度: {progress.speed / (1024*1024):.2f}MB/s "
              f"剩余: {progress.eta}秒", end='', flush=True)
    elif progress.status == 'finished':
        print("\n  下载完成！")


async def download_single_video(
    downloader: VideoDownloader,
    url: str,
    index: int,
    total: int,
    quality: VideoQuality = VideoQuality.MEDIUM
) -> DownloadResult:
    """下载单个视频"""
    print(f"\n[{index}/{total}] 开始下载")
    print(f"  URL: {url}")

    # 检测平台
    platform = downloader.detect_platform(url)
    print(f"  平台: {platform or '未知'}")

    # 先获取视频信息
    print("  获取视频信息...")
    info = await downloader.get_video_info(url)

    if info:
        title = info.get('title', 'N/A')
        duration = info.get('duration', 0)
        filesize = info.get('filesize') or info.get('filesize_approx', 0)

        print(f"  标题: {title}")
        print(f"  时长: {duration}秒")
        if filesize > 0:
            print(f"  预计大小: {filesize / (1024*1024):.2f}MB")
    else:
        print("  警告: 无法获取视频信息，尝试直接下载...")

    # 下载视频
    print(f"  开始下载（质量: {quality.value}）...")
    result = await downloader.download(
        url=url,
        quality=quality,
        format_type="mp4"
    )

    return result


async def test_default_urls(quality: VideoQuality = VideoQuality.MEDIUM):
    """测试内置的默认URL列表"""
    print("=" * 70)
    print("批量视频下载测试（使用内置URL）")
    print("=" * 70)

    urls = DEFAULT_TEST_URLS
    print(f"\n使用内置测试URL，共 {len(urls)} 个\n")

    # 创建下载器
    downloader = VideoDownloader(
        output_dir=str(Path(__file__).parent.parent / "downloads"),
        max_file_size=200 * 1024 * 1024,  # 200MB 限制
        max_retries=3,
        timeout=300
    )
    downloader.set_progress_callback(progress_callback)

    # 下载统计
    results = []
    success_count = 0
    failed_count = 0

    # 逐个下载
    for i, url in enumerate(urls, 1):
        try:
            result = await download_single_video(downloader, url, i, len(urls), quality)
            results.append((url, result))

            if result.success:
                success_count += 1
                print(f"  状态: 成功")
                print(f"  文件: {result.file_path}")
                print(f"  大小: {result.file_size / (1024*1024):.2f}MB")
            else:
                failed_count += 1
                print(f"  状态: 失败")
                print(f"  错误: {result.error}")

        except Exception as e:
            failed_count += 1
            print(f"  状态: 异常")
            print(f"  错误: {str(e)}")
            results.append((url, None))

    # 打印总结
    print_summary(urls, results, success_count, failed_count, downloader)


async def test_single_url(url: str, quality: VideoQuality = VideoQuality.MEDIUM):
    """测试单个URL下载"""
    print("=" * 70)
    print("单个视频下载测试")
    print("=" * 70)
    print(f"\n视频URL: {url}\n")

    # 创建下载器
    downloader = VideoDownloader(
        output_dir=str(Path(__file__).parent.parent / "downloads"),
        max_file_size=200 * 1024 * 1024,
        max_retries=3,
        timeout=300
    )
    downloader.set_progress_callback(progress_callback)

    # 下载视频
    result = await download_single_video(downloader, url, 1, 1, quality)

    # 打印结果
    print("\n" + "=" * 70)
    if result.success:
        print("下载成功！")
        print(f"  文件: {result.file_path}")
        print(f"  标题: {result.title}")
        print(f"  大小: {result.file_size / (1024*1024):.2f}MB")
    else:
        print("下载失败！")
        print(f"  错误: {result.error}")
    print("=" * 70)


def print_summary(urls: List[str], results: List, success_count: int, failed_count: int, downloader: VideoDownloader):
    """打印下载总结"""
    print("\n" + "=" * 70)
    print("下载总结")
    print("=" * 70)
    print(f"总计: {len(urls)} 个视频")
    print(f"成功: {success_count} 个")
    print(f"失败: {failed_count} 个")
    if len(urls) > 0:
        print(f"成功率: {success_count / len(urls) * 100:.1f}%")

    print("\n详细结果:")
    for i, (url, result) in enumerate(results, 1):
        status = "成功" if result and result.success else "失败"
        platform = downloader.detect_platform(url) or "未知"
        print(f"  [{i}] {platform:10s} {status:4s} - {url[:50]}...")
        if result and result.success:
            try:
                filename = Path(result.file_path).name
                print(f"      文件: {filename}")
            except UnicodeEncodeError:
                print(f"      文件: [文件名包含特殊字符]")

    print("=" * 70)


def print_usage():
    """打印使用说明"""
    print("""
使用方法:
    python tests/test_download.py                          # 测试内置的默认URL
    python tests/test_download.py <url>                    # 测试单个URL
    python tests/test_download.py <url> --quality low      # 指定质量

质量选项:
    --quality best      # 最佳质量
    --quality high      # 高清 (1080p)
    --quality medium    # 标清 (720p) [默认]
    --quality low       # 低清 (480p)

示例:
    # 测试内置URL（YouTube + Bilibili）
    python tests/test_download.py

    # 测试单个YouTube视频
    python tests/test_download.py https://www.youtube.com/watch?v=xxxxx

    # 测试Bilibili视频（高质量）
    python tests/test_download.py https://www.bilibili.com/video/BVxxxxx --quality high

内置测试URL:
    - YouTube: https://www.youtube.com/watch?v=dQw4w9WgXcQ
    - Bilibili: https://www.bilibili.com/video/BV1x9PWzuEKc/
""")


async def main():
    """主函数"""
    # 解析命令行参数
    args = sys.argv[1:]

    # 解析质量参数
    quality = VideoQuality.MEDIUM
    if '--quality' in args:
        quality_idx = args.index('--quality')
        if quality_idx + 1 < len(args):
            quality_str = args[quality_idx + 1].lower()
            quality_map = {
                'best': VideoQuality.BEST,
                'high': VideoQuality.HIGH,
                'medium': VideoQuality.MEDIUM,
                'low': VideoQuality.LOW,
            }
            quality = quality_map.get(quality_str, VideoQuality.MEDIUM)
            # 移除质量参数
            args = args[:quality_idx] + args[quality_idx + 2:]

    # 确保下载目录存在（在项目根目录）
    download_dir = Path(__file__).parent.parent / "downloads"
    download_dir.mkdir(exist_ok=True)

    # 根据参数决定测试方式
    if not args:
        # 默认测试内置URL
        await test_default_urls(quality)
    elif args[0] in ['-h', '--help', 'help']:
        print_usage()
    elif args[0].startswith('http://') or args[0].startswith('https://'):
        # 单个URL
        await test_single_url(args[0], quality)
    else:
        print(f"错误: 无效的参数: {args[0]}")
        print_usage()


if __name__ == "__main__":
    asyncio.run(main())

