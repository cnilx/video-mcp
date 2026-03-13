"""配置管理模块"""
import json
import os
from pathlib import Path
from typing import Optional, Any
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field, field_validator


class ServerConfig(BaseModel):
    """服务器配置"""
    host: str = Field(default="0.0.0.0", description="服务器主机地址")
    port: int = Field(default=8000, ge=1, le=65535, description="服务器端口")
    timeout: int = Field(default=3600, ge=1, description="服务器超时时间（秒）")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("端口号必须在 1-65535 之间")
        return v


class SpeechConfig(BaseModel):
    """语音识别配置"""
    model: str = Field(default="qwen3-asr-flash-filetrans", description="语音识别模型")
    language: Optional[str] = Field(default="zh", description="语言代码（zh, en, ja, ko 等）")


class OSSConfig(BaseModel):
    """阿里云 OSS 配置"""
    endpoint: str = Field(default="", description="OSS Endpoint（如 oss-cn-hangzhou.aliyuncs.com）")
    bucket_name: str = Field(default="", description="OSS Bucket 名称")


class VisionConfig(BaseModel):
    """图像识别配置"""
    base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1",
        description="API 基础 URL（DashScope 原生 SDK 端点）"
    )
    model: str = Field(default="qwen3-vl-flash", description="图像识别模型")
    max_tokens: int = Field(default=2000, ge=1, description="最大 token 数")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")


class WorkspaceConfig(BaseModel):
    """工作空间配置"""
    base_dir: str = Field(default="/data/workspaces", description="工作目录基础路径")
    auto_cleanup_days: int = Field(default=7, ge=1, description="自动清理天数")
    max_size_gb: float = Field(default=10.0, gt=0, description="工作空间最大总大小（GB）")


class DownloadConfig(BaseModel):
    """下载配置"""
    default_quality: str = Field(default="best", description="默认视频质量")
    max_file_size_gb: int = Field(default=5, ge=1, description="最大文件大小（GB）")

    @field_validator("default_quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        allowed = ["best", "worst", "720p", "1080p", "480p"]
        if v not in allowed:
            logger.warning(f"不支持的视频质量: {v}，使用默认值 'best'")
            return "best"
        return v


class AppConfig(BaseModel):
    """应用配置"""
    server: ServerConfig = Field(default_factory=ServerConfig)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    oss: OSSConfig = Field(default_factory=OSSConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)


class Config:
    """配置管理类"""

    def __init__(self, config_path: Optional[str] = None, auto_reload: bool = False):
        """
        初始化配置

        Args:
            config_path: 配置文件路径，默认为 config/config.json
            auto_reload: 是否启用自动重载
        """
        # 加载环境变量
        load_dotenv()

        # 确定配置文件路径
        if config_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            config_path = os.getenv("CONFIG_PATH", str(project_root / "config" / "config.json"))

        self.config_path = Path(config_path)
        self.auto_reload = auto_reload
        self._last_modified: Optional[float] = None

        # 加载配置
        self._config = self._load_and_validate_config()

        # 加载敏感信息（从环境变量）
        self.api_key = os.getenv("API_KEY")
        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
        self.oss_access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
        self.oss_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")

        # 验证必需的配置
        self._validate_env()

    def _load_config_dict(self) -> dict:
        """加载配置文件为字典"""
        if not self.config_path.exists():
            logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 记录文件修改时间
            self._last_modified = self.config_path.stat().st_mtime

            logger.info(f"成功加载配置文件: {self.config_path}")
            return config
        except json.JSONDecodeError as e:
            logger.error(f"配置文件 JSON 格式错误: {e}，使用默认配置")
            return {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return {}

    def _load_and_validate_config(self) -> AppConfig:
        """加载并验证配置"""
        config_dict = self._load_config_dict()

        try:
            # 使用 Pydantic 验证配置
            app_config = AppConfig(**config_dict)
            logger.info("配置验证成功")
            return app_config
        except Exception as e:
            logger.error(f"配置验证失败: {e}，使用默认配置")
            return AppConfig()

    def _validate_env(self):
        """验证环境变量"""
        if not self.api_key:
            logger.warning("未设置 API_KEY 环境变量，服务将无法进行认证")

        if not self.dashscope_api_key:
            logger.warning("未设置 DASHSCOPE_API_KEY 环境变量，语音识别和图像识别功能将不可用")

        if not self.oss_access_key_id or not self.oss_access_key_secret:
            logger.warning("未设置 OSS 环境变量，使用 filetrans 模型时需要 OSS 支持")

    def reload(self) -> bool:
        """
        重新加载配置

        Returns:
            是否成功重载
        """
        try:
            logger.info("开始重新加载配置...")

            # 重新加载环境变量
            load_dotenv(override=True)

            # 重新加载配置文件
            new_config = self._load_and_validate_config()

            # 更新配置
            self._config = new_config
            self.api_key = os.getenv("API_KEY")
            self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
            self.oss_access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
            self.oss_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")

            self._validate_env()

            logger.info("配置重新加载成功")
            return True
        except Exception as e:
            logger.error(f"配置重新加载失败: {e}")
            return False

    def check_and_reload(self) -> bool:
        """
        检查配置文件是否修改，如果修改则重新加载

        Returns:
            是否进行了重载
        """
        if not self.auto_reload:
            return False

        if not self.config_path.exists():
            return False

        try:
            current_mtime = self.config_path.stat().st_mtime
            if self._last_modified is None or current_mtime > self._last_modified:
                logger.info("检测到配置文件变化，开始重新加载...")
                return self.reload()
        except Exception as e:
            logger.error(f"检查配置文件修改时间失败: {e}")

        return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项

        Args:
            key: 配置键，支持点号分隔的路径，如 "server.host"
            default: 默认值

        Returns:
            配置值
        """
        # 如果启用了自动重载，检查配置文件
        if self.auto_reload:
            self.check_and_reload()

        keys = key.split(".")
        value = self._config.model_dump()

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    # 服务器配置属性
    @property
    def server_host(self) -> str:
        """服务器主机地址"""
        return self._config.server.host

    @property
    def server_port(self) -> int:
        """服务器端口"""
        return self._config.server.port

    @property
    def server_timeout(self) -> int:
        """服务器超时时间（秒）"""
        return self._config.server.timeout

    # 语音识别配置属性
    @property
    def speech_model(self) -> str:
        """语音识别模型"""
        return self._config.speech.model

    @property
    def speech_language(self) -> str:
        """语音识别语言"""
        return self._config.speech.language

    # OSS 配置属性
    @property
    def oss_endpoint(self) -> str:
        """OSS Endpoint"""
        return self._config.oss.endpoint

    @property
    def oss_bucket_name(self) -> str:
        """OSS Bucket 名称"""
        return self._config.oss.bucket_name

    # 图像识别配置属性
    @property
    def vision_base_url(self) -> str:
        """图像识别 API 基础 URL"""
        return self._config.vision.base_url

    @property
    def vision_model(self) -> str:
        """图像识别模型"""
        return self._config.vision.model

    @property
    def vision_max_tokens(self) -> int:
        """图像识别最大 token 数"""
        return self._config.vision.max_tokens

    @property
    def vision_temperature(self) -> float:
        """图像识别温度参数"""
        return self._config.vision.temperature

    # 工作空间配置属性
    @property
    def workspace_base_dir(self) -> str:
        """工作目录基础路径"""
        return self._config.workspace.base_dir

    @property
    def workspace_auto_cleanup_days(self) -> int:
        """工作目录自动清理天数"""
        return self._config.workspace.auto_cleanup_days

    @property
    def workspace_max_size_gb(self) -> float:
        """工作空间最大总大小（GB）"""
        return self._config.workspace.max_size_gb

    # 下载配置属性
    @property
    def download_default_quality(self) -> str:
        """默认视频质量"""
        return self._config.download.default_quality

    @property
    def download_max_file_size_gb(self) -> int:
        """最大文件大小（GB）"""
        return self._config.download.max_file_size_gb


# 全局配置实例
config = Config()
