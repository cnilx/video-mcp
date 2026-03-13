"""工作空间管理模块单元测试"""

import time
from pathlib import Path

import pytest

from src.utils.workspace import WorkspaceManager, WorkspaceInfo, WORKSPACE_SUBDIRS


@pytest.fixture
def ws_manager(tmp_path):
    """创建使用临时目录的 WorkspaceManager"""
    return WorkspaceManager(
        base_dir=str(tmp_path / "workspaces"),
        max_size_gb=0.001,  # 约 1MB，方便测试大小限制
        auto_cleanup_days=7,
    )


class TestWorkspaceCreate:
    def test_create_auto_id(self, ws_manager):
        info = ws_manager.create()
        assert info.path.exists()
        for subdir in WORKSPACE_SUBDIRS:
            assert (info.path / subdir).is_dir()
        assert (info.path / ".created_at").exists()

    def test_create_custom_id(self, ws_manager):
        info = ws_manager.create(workspace_id="my-task-001")
        assert info.workspace_id == "my-task-001"
        assert info.path.name == "my-task-001"

    def test_create_reuse_existing(self, ws_manager):
        info1 = ws_manager.create(workspace_id="reuse-test")
        # 在 video 子目录放一个文件
        (info1.path / "video" / "test.mp4").write_bytes(b"x" * 100)
        info2 = ws_manager.create(workspace_id="reuse-test")
        assert info2.workspace_id == "reuse-test"
        assert info2.size_bytes >= 100  # 文件还在


class TestWorkspaceGetInfo:
    def test_get_info(self, ws_manager):
        ws_manager.create(workspace_id="info-test")
        info = ws_manager.get_info("info-test")
        assert info.workspace_id == "info-test"
        assert info.size_bytes >= 0
        assert info.age_hours >= 0

    def test_get_info_not_found(self, ws_manager):
        with pytest.raises(FileNotFoundError):
            ws_manager.get_info("nonexistent")


class TestWorkspaceGetPath:
    def test_get_root_path(self, ws_manager):
        ws_manager.create(workspace_id="path-test")
        p = ws_manager.get_path("path-test")
        assert p.exists()

    def test_get_subdir_path(self, ws_manager):
        ws_manager.create(workspace_id="path-test")
        p = ws_manager.get_path("path-test", "video")
        assert p.exists()
        assert p.name == "video"

    def test_get_path_not_found(self, ws_manager):
        with pytest.raises(FileNotFoundError):
            ws_manager.get_path("nonexistent")


class TestWorkspaceList:
    def test_list_empty(self, ws_manager):
        assert ws_manager.list_workspaces() == []

    def test_list_multiple(self, ws_manager):
        ws_manager.create(workspace_id="ws-a")
        ws_manager.create(workspace_id="ws-b")
        result = ws_manager.list_workspaces()
        ids = [w.workspace_id for w in result]
        assert "ws-a" in ids
        assert "ws-b" in ids


class TestWorkspaceDelete:
    def test_delete(self, ws_manager):
        info = ws_manager.create(workspace_id="del-test")
        assert info.path.exists()
        assert ws_manager.delete("del-test") is True
        assert not info.path.exists()

    def test_delete_nonexistent(self, ws_manager):
        assert ws_manager.delete("nonexistent") is False


class TestCleanupExpired:
    def test_cleanup_expired(self, ws_manager):
        ws_manager.auto_cleanup_days = 0  # 立即过期
        info = ws_manager.create(workspace_id="expire-test")
        # 伪造一个过去的时间戳
        ts_file = info.path / ".created_at"
        ts_file.write_text(str(time.time() - 86400 * 2))

        removed = ws_manager.cleanup_expired()
        assert removed == 1
        assert not info.path.exists()

    def test_cleanup_keeps_fresh(self, ws_manager):
        ws_manager.create(workspace_id="fresh-test")
        removed = ws_manager.cleanup_expired()
        assert removed == 0


class TestCleanupSubdir:
    def test_cleanup_subdir(self, ws_manager):
        info = ws_manager.create(workspace_id="subdir-test")
        video_dir = info.path / "video"
        (video_dir / "a.mp4").write_bytes(b"x" * 50)
        (video_dir / "b.mp4").write_bytes(b"x" * 50)

        count = ws_manager.cleanup_subdir("subdir-test", "video")
        assert count == 2
        assert list(video_dir.iterdir()) == []


class TestSizeLimit:
    def test_evict_on_size_limit(self, ws_manager):
        # max_size_gb=0.001 ≈ 1MB
        info1 = ws_manager.create(workspace_id="big-ws")
        # 写入超过 1MB 的数据（模拟下载后的文件）
        (info1.path / "video" / "large.bin").write_bytes(b"x" * (2 * 1024 * 1024))

        # 确认总大小已超限
        assert ws_manager.get_total_size() > ws_manager.max_size_bytes

        # 创建新工作空间应触发淘汰
        info2 = ws_manager.create(workspace_id="new-ws")
        assert info2.path.exists()
        # big-ws 应该被淘汰了
        assert not (ws_manager.base_dir / "big-ws").exists()


class TestGetTotalSize:
    def test_total_size(self, ws_manager):
        info = ws_manager.create(workspace_id="size-test")
        (info.path / "video" / "file.bin").write_bytes(b"x" * 1024)
        total = ws_manager.get_total_size()
        assert total >= 1024

