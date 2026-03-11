"""
阿里云 OSS 上传模块
用于将本地文件上传到 OSS，获取公网可访问的 URL
"""

import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

import oss2
from loguru import logger


class OSSUploader:
    """阿里云 OSS 上传器"""

    def __init__(
        self,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
        endpoint: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        """
        初始化 OSS 上传器

        Args:
            access_key_id: 阿里云 AccessKey ID
            access_key_secret: 阿里云 AccessKey Secret
            endpoint: OSS Endpoint（如 oss-cn-hangzhou.aliyuncs.com）
            bucket_name: OSS Bucket 名称
        """
        self.access_key_id = access_key_id or os.getenv("OSS_ACCESS_KEY_ID")
        self.access_key_secret = access_key_secret or os.getenv("OSS_ACCESS_KEY_SECRET")
        self.endpoint = endpoint or os.getenv("OSS_ENDPOINT")
        self.bucket_name = bucket_name or os.getenv("OSS_BUCKET_NAME")

        # 验证配置
        if not all([self.access_key_id, self.access_key_secret, self.endpoint, self.bucket_name]):
            logger.warning("OSS 配置不完整，上传功能将不可用")
            self.bucket = None
        else:
            try:
                # 创建认证对象
                auth = oss2.Auth(self.access_key_id, self.access_key_secret)
                # 创建 Bucket 对象
                self.bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)
                logger.info(f"OSS 初始化成功: {self.bucket_name}")
            except Exception as e:
                logger.error(f"OSS 初始化失败: {str(e)}")
                self.bucket = None

    def upload_file(
        self,
        local_path: str,
        object_name: Optional[str] = None,
        folder: str = "audio",
    ) -> Optional[str]:
        """
        上传文件到 OSS

        Args:
            local_path: 本地文件路径
            object_name: OSS 对象名称，None 则使用文件名
            folder: OSS 文件夹路径

        Returns:
            公网访问 URL，失败返回 None
        """
        if not self.bucket:
            logger.error("OSS 未初始化，无法上传文件")
            return None

        try:
            local_path = Path(local_path)
            if not local_path.exists():
                logger.error(f"文件不存在: {local_path}")
                return None

            # 生成对象名称
            if object_name is None:
                # 使用时间戳 + 原文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                object_name = f"{timestamp}_{local_path.name}"

            # 完整的对象路径
            object_key = f"{folder}/{object_name}" if folder else object_name

            logger.info(f"开始上传文件: {local_path} -> {object_key}")

            # 上传文件
            with open(local_path, "rb") as f:
                result = self.bucket.put_object(object_key, f)

            if result.status == 200:
                # 生成公网访问 URL（使用 HTTPS）
                url = f"https://{self.bucket_name}.{self.endpoint}/{object_key}"
                logger.info(f"文件上传成功: {url}")
                return url
            else:
                logger.error(f"文件上传失败: HTTP {result.status}")
                return None

        except Exception as e:
            logger.error(f"上传文件异常: {str(e)}")
            return None

    def upload_file_with_signed_url(
        self,
        local_path: str,
        object_name: Optional[str] = None,
        folder: str = "audio",
        expires: int = 3600,
    ) -> Optional[str]:
        """
        上传文件并生成签名 URL（用于私有 Bucket）

        Args:
            local_path: 本地文件路径
            object_name: OSS 对象名称，None 则使用文件名
            folder: OSS 文件夹路径
            expires: 签名 URL 有效期（秒），默认 1 小时

        Returns:
            签名 URL，失败返回 None
        """
        if not self.bucket:
            logger.error("OSS 未初始化，无法上传文件")
            return None

        try:
            local_path = Path(local_path)
            if not local_path.exists():
                logger.error(f"文件不存在: {local_path}")
                return None

            # 生成对象名称
            if object_name is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                object_name = f"{timestamp}_{local_path.name}"

            # 完整的对象路径
            object_key = f"{folder}/{object_name}" if folder else object_name

            logger.info(f"开始上传文件: {local_path} -> {object_key}")

            # 上传文件
            with open(local_path, "rb") as f:
                result = self.bucket.put_object(object_key, f)

            if result.status == 200:
                # 生成签名 URL
                signed_url = self.bucket.sign_url("GET", object_key, expires)
                logger.info(f"文件上传成功，签名 URL 有效期: {expires}秒")
                return signed_url
            else:
                logger.error(f"文件上传失败: HTTP {result.status}")
                return None

        except Exception as e:
            logger.error(f"上传文件异常: {str(e)}")
            return None

    def delete_file(self, object_key: str) -> bool:
        """
        删除 OSS 文件

        Args:
            object_key: OSS 对象路径

        Returns:
            是否成功
        """
        if not self.bucket:
            logger.error("OSS 未初始化，无法删除文件")
            return False

        try:
            result = self.bucket.delete_object(object_key)
            if result.status == 204:
                logger.info(f"文件删除成功: {object_key}")
                return True
            else:
                logger.error(f"文件删除失败: HTTP {result.status}")
                return False

        except Exception as e:
            logger.error(f"删除文件异常: {str(e)}")
            return False

    def file_exists(self, object_key: str) -> bool:
        """
        检查文件是否存在

        Args:
            object_key: OSS 对象路径

        Returns:
            是否存在
        """
        if not self.bucket:
            return False

        try:
            return self.bucket.object_exists(object_key)
        except Exception as e:
            logger.error(f"检查文件存在性异常: {str(e)}")
            return False
