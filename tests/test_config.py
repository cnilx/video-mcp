"""配置管理模块测试"""
import os
import json
import tempfile
from pathlib import Path
import pytest
from src.utils.config import (
    Config,
    ServerConfig,
    SpeechConfig,
    VisionConfig,
    WorkspaceConfig,
    DownloadConfig,
    AppConfig
)


class TestConfigModels:
    """测试配置模型"""

    def test_server_config_default(self):
        """测试服务器配置默认值"""
        config = ServerConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.timeout == 3600

    def test_server_config_custom(self):
        """测试服务器配置自定义值"""
        config = ServerConfig(host="127.0.0.1", port=9000, timeout=7200)
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.timeout == 7200

    def test_server_config_invalid_port(self):
        """测试无效端口号"""
        with pytest.raises(ValueError):
            ServerConfig(port=0)

        with pytest.raises(ValueError):
            ServerConfig(port=65536)

    def test_speech_config_default(self):
        """测试语音识别配置默认值"""
        config = SpeechConfig()
        assert config.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert config.model == "qwen3-asr-flash"
        assert config.enable_itn is False
        assert config.language is None

    def test_vision_config_default(self):
        """测试图像识别配置默认值"""
        config = VisionConfig()
        assert config.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert config.model == "qwen3-vl-flash"
        assert config.max_tokens == 2000
        assert config.temperature == 0.7

    def test_workspace_config_default(self):
        """测试工作空间配置默认值"""
        config = WorkspaceConfig()
        assert config.base_dir == "/data/workspaces"
        assert config.auto_cleanup_days == 7

    def test_download_config_default(self):
        """测试下载配置默认值"""
        config = DownloadConfig()
        assert config.default_quality == "best"
        assert config.max_file_size_gb == 5

    def test_download_config_invalid_quality(self):
        """测试无效视频质量"""
        # 无效的质量会被自动修正为 "best"
        config = DownloadConfig(default_quality="invalid")
        assert config.default_quality == "best"

    def test_app_config_default(self):
        """测试应用配置默认值"""
        config = AppConfig()
        assert isinstance(config.server, ServerConfig)
        assert isinstance(config.speech, SpeechConfig)
        assert isinstance(config.vision, VisionConfig)
        assert isinstance(config.workspace, WorkspaceConfig)
        assert isinstance(config.download, DownloadConfig)


class TestConfig:
    """测试配置管理类"""

    @pytest.fixture
    def temp_config_file(self):
        """创建临时配置文件"""
        config_data = {
            "server": {
                "host": "127.0.0.1",
                "port": 9000,
                "timeout": 7200
            },
            "speech": {
                "base_url": "https://test.api.com/v1",
                "model": "test-model",
                "enable_itn": True,
                "language": "zh"
            },
            "vision": {
                "base_url": "https://test.api.com/v1",
                "model": "test-vision-model",
                "max_tokens": 3000,
                "temperature": 0.5
            },
            "workspace": {
                "base_dir": "/tmp/workspaces",
                "auto_cleanup_days": 3
            },
            "download": {
                "default_quality": "720p",
                "max_file_size_gb": 10
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name

        yield temp_path

        # 清理临时文件
        Path(temp_path).unlink(missing_ok=True)

    @pytest.fixture
    def temp_env_file(self):
        """创建临时环境变量文件"""
        env_data = """
API_KEY=test-api-key
DASHSCOPE_API_KEY=test-dashscope-key
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_data)
            temp_path = f.name

        yield temp_path

        # 清理临时文件
        Path(temp_path).unlink(missing_ok=True)

    def test_config_default(self):
        """测试默认配置"""
        config = Config(config_path="non_existent_file.json")
        assert config.server_host == "0.0.0.0"
        assert config.server_port == 8000
        assert config.server_timeout == 3600

    def test_config_from_file(self, temp_config_file):
        """测试从文件加载配置"""
        config = Config(config_path=temp_config_file)
        assert config.server_host == "127.0.0.1"
        assert config.server_port == 9000
        assert config.server_timeout == 7200
        assert config.speech_model == "test-model"
        assert config.vision_model == "test-vision-model"

    def test_config_get_method(self, temp_config_file):
        """测试 get 方法"""
        config = Config(config_path=temp_config_file)
        assert config.get("server.host") == "127.0.0.1"
        assert config.get("server.port") == 9000
        assert config.get("non.existent.key", "default") == "default"

    def test_config_properties(self, temp_config_file):
        """测试配置属性"""
        config = Config(config_path=temp_config_file)

        # 服务器配置
        assert config.server_host == "127.0.0.1"
        assert config.server_port == 9000
        assert config.server_timeout == 7200

        # 语音识别配置
        assert config.speech_base_url == "https://test.api.com/v1"
        assert config.speech_model == "test-model"
        assert config.speech_enable_itn is True
        assert config.speech_language == "zh"

        # 图像识别配置
        assert config.vision_base_url == "https://test.api.com/v1"
        assert config.vision_model == "test-vision-model"
        assert config.vision_max_tokens == 3000
        assert config.vision_temperature == 0.5

        # 工作空间配置
        assert config.workspace_base_dir == "/tmp/workspaces"
        assert config.workspace_auto_cleanup_days == 3

        # 下载配置
        assert config.download_default_quality == "720p"
        assert config.download_max_file_size_gb == 10

    def test_config_reload(self, temp_config_file):
        """测试配置重载"""
        config = Config(config_path=temp_config_file)
        original_port = config.server_port

        # 修改配置文件
        with open(temp_config_file, 'r') as f:
            config_data = json.load(f)
        config_data['server']['port'] = 10000
        with open(temp_config_file, 'w') as f:
            json.dump(config_data, f)

        # 重新加载配置
        success = config.reload()
        assert success is True
        assert config.server_port == 10000
        assert config.server_port != original_port

    def test_config_check_and_reload(self, temp_config_file):
        """测试检查并重载配置"""
        config = Config(config_path=temp_config_file, auto_reload=True)
        original_port = config.server_port

        # 修改配置文件
        import time
        time.sleep(0.1)  # 确保文件修改时间不同
        with open(temp_config_file, 'r') as f:
            config_data = json.load(f)
        config_data['server']['port'] = 11000
        with open(temp_config_file, 'w') as f:
            json.dump(config_data, f)

        # 检查并重载
        reloaded = config.check_and_reload()
        assert reloaded is True
        assert config.server_port == 11000

    def test_config_auto_reload_disabled(self, temp_config_file):
        """测试禁用自动重载"""
        config = Config(config_path=temp_config_file, auto_reload=False)

        # 修改配置文件
        with open(temp_config_file, 'r') as f:
            config_data = json.load(f)
        config_data['server']['port'] = 12000
        with open(temp_config_file, 'w') as f:
            json.dump(config_data, f)

        # 检查并重载（应该不会重载）
        reloaded = config.check_and_reload()
        assert reloaded is False

    def test_config_invalid_json(self):
        """测试无效的 JSON 配置文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            # 应该使用默认配置
            assert config.server_host == "0.0.0.0"
            assert config.server_port == 8000
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_config_env_variables(self, monkeypatch):
        """测试环境变量"""
        monkeypatch.setenv("API_KEY", "test-api-key")
        monkeypatch.setenv("DASHSCOPE_API_KEY", "test-dashscope-key")

        config = Config(config_path="non_existent_file.json")
        assert config.api_key == "test-api-key"
        assert config.dashscope_api_key == "test-dashscope-key"

    def test_config_missing_env_variables(self, monkeypatch):
        """测试缺少环境变量"""
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

        config = Config(config_path="non_existent_file.json")
        assert config.api_key is None
        assert config.dashscope_api_key is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
