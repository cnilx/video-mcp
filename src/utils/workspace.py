"""
工作空间管理模块

提供视频处理任务的工作空间生命周期管理：
- 创建隔离的任务工作空间（每个任务独立目录）
- 临时文件自动清理
- 工作空间总大小限制
- 过期工作空间自动清理

目录结构:
    base_dir/
    ├── {workspace_id}/          # 每个任务一个工作空间
    │   ├── video/               # 下载的视频文件
    │   ├── audio/               # 提取的音频文件
    │   ├── frames/              # 提取的视频帧
    │   └── output/              # 输出结果（字幕、分析报告等）
    └── ...
"""

import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class WorkspaceInfo:
    """工作空间信息"""
    workspace_id: str
    path: Path
    created_at: float
    size_bytes: int = 0

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    @property
    def age_hours(self) -> float:
        return (time.time() - self.created_at) / 3600


# 工作空间内的子目录
WORKSPACE_SUBDIRS = ["video", "audio", "frames", "output"]


class WorkspaceManager:
    """工作空间管理器"""

    def __init__(
        self,
        base_dir: str = "/data/workspaces",
        max_size_gb: float = 10.0,
        auto_cleanup_days: int = 7,
    ):
        """
        Args:
            base_dir: 工作空间根目录
            max_size_gb: 最大总大小（GB）
            auto_cleanup_days: 自动清理天数
        """
        self.base_dir = Path(base_dir)
        self.max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)
        self.auto_cleanup_days = auto_cleanup_days

        # 确保根目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"工作空间管理器初始化: {self.base_dir}")

    def create(self, workspace_id: Optional[str] = None) -> WorkspaceInfo:
        """
        创建新的工作空间

        Args:
            workspace_id: 自定义 ID，默认自动生成

        Returns:
            WorkspaceInfo
        """
        # 创建前先清理过期空间，腾出容量
        self.cleanup_expired()

        if workspace_id is None:
            workspace_id = self._generate_id()

        ws_path = self.base_dir / workspace_id
        if ws_path.exists():
            logger.warning(f"工作空间已存在，复用: {workspace_id}")
            return self.get_info(workspace_id)

        # 检查总大小限制
        total = self.get_total_size()
        if total >= self.max_size_bytes:
            logger.warning(f"工作空间总大小已达上限 ({total / (1024**3):.2f} GB)，尝试清理最旧的空间")
            self._evict_oldest()

        # 创建目录结构
        for subdir in WORKSPACE_SUBDIRS:
            (ws_path / subdir).mkdir(parents=True, exist_ok=True)

        # 写入创建时间戳
        ts_file = ws_path / ".created_at"
        ts_file.write_text(str(time.time()))

        info = WorkspaceInfo(
            workspace_id=workspace_id,
            path=ws_path,
            created_at=time.time(),
        )
        logger.info(f"创建工作空间: {workspace_id} -> {ws_path}")
        return info

    def get_info(self, workspace_id: str) -> WorkspaceInfo:
        """获取工作空间信息"""
        ws_path = self.base_dir / workspace_id
        if not ws_path.exists():
            raise FileNotFoundError(f"工作空间不存在: {workspace_id}")

        created_at = self._read_created_at(ws_path)
        size = self._calc_dir_size(ws_path)

        return WorkspaceInfo(
            workspace_id=workspace_id,
            path=ws_path,
            created_at=created_at,
            size_bytes=size,
        )

    def get_path(self, workspace_id: str, subdir: Optional[str] = None) -> Path:
        """
        获取工作空间路径

        Args:
            workspace_id: 工作空间 ID
            subdir: 子目录名（video/audio/frames/output）

        Returns:
            目录路径
        """
        ws_path = self.base_dir / workspace_id
        if not ws_path.exists():
            raise FileNotFoundError(f"工作空间不存在: {workspace_id}")
        if subdir:
            p = ws_path / subdir
            p.mkdir(parents=True, exist_ok=True)
            return p
        return ws_path

    def list_workspaces(self) -> list[WorkspaceInfo]:
        """列出所有工作空间，按创建时间排序"""
        workspaces = []
        if not self.base_dir.exists():
            return workspaces

        for item in self.base_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                try:
                    workspaces.append(self.get_info(item.name))
                except Exception as e:
                    logger.warning(f"读取工作空间信息失败 {item.name}: {e}")

        workspaces.sort(key=lambda w: w.created_at)
        return workspaces

    def delete(self, workspace_id: str) -> bool:
        """删除指定工作空间"""
        ws_path = self.base_dir / workspace_id
        if not ws_path.exists():
            logger.warning(f"工作空间不存在: {workspace_id}")
            return False

        try:
            shutil.rmtree(ws_path)
            logger.info(f"已删除工作空间: {workspace_id}")
            return True
        except Exception as e:
            logger.error(f"删除工作空间失败 {workspace_id}: {e}")
            return False

    def cleanup_expired(self) -> int:
        """
        清理过期工作空间

        Returns:
            清理的工作空间数量
        """
        cutoff = time.time() - (self.auto_cleanup_days * 86400)
        removed = 0

        for ws in self.list_workspaces():
            if ws.created_at < cutoff:
                logger.info(f"清理过期工作空间: {ws.workspace_id} (已存在 {ws.age_hours:.1f} 小时)")
                if self.delete(ws.workspace_id):
                    removed += 1

        if removed:
            logger.info(f"共清理 {removed} 个过期工作空间")
        return removed

    def cleanup_subdir(self, workspace_id: str, subdir: str) -> int:
        """
        清理工作空间内指定子目录的所有文件

        Returns:
            清理的文件数量
        """
        target = self.base_dir / workspace_id / subdir
        if not target.exists():
            return 0

        count = 0
        for f in target.iterdir():
            try:
                if f.is_file():
                    f.unlink()
                    count += 1
                elif f.is_dir():
                    shutil.rmtree(f)
                    count += 1
            except Exception as e:
                logger.warning(f"清理文件失败 {f}: {e}")
        logger.info(f"清理 {workspace_id}/{subdir}: {count} 个文件")
        return count

    def get_total_size(self) -> int:
        """获取所有工作空间的总大小（字节）"""
        return self._calc_dir_size(self.base_dir)

    def _generate_id(self) -> str:
        """生成工作空间 ID: 日期前缀 + 短 UUID"""
        date_str = datetime.now().strftime("%Y%m%d")
        short_uuid = uuid.uuid4().hex[:8]
        return f"{date_str}_{short_uuid}"

    def _read_created_at(self, ws_path: Path) -> float:
        """读取工作空间创建时间戳"""
        ts_file = ws_path / ".created_at"
        if ts_file.exists():
            try:
                return float(ts_file.read_text().strip())
            except (ValueError, OSError):
                pass
        # 回退到目录的修改时间
        return ws_path.stat().st_mtime

    def _calc_dir_size(self, path: Path) -> int:
        """递归计算目录大小"""
        total = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        except OSError as e:
            logger.warning(f"计算目录大小出错 {path}: {e}")
        return total

    def _evict_oldest(self) -> bool:
        """淘汰最旧的工作空间以释放空间"""
        workspaces = self.list_workspaces()
        if not workspaces:
            return False

        oldest = workspaces[0]
        logger.info(f"淘汰最旧工作空间: {oldest.workspace_id} ({oldest.size_mb:.1f} MB)")
        return self.delete(oldest.workspace_id)
