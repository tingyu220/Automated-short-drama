"""资源清理服务 —— 日志/截图/临时文件保留与清理."""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.infrastructure.database.models.execution import (
    ExecutionArtifactRecord,
)

logger = logging.getLogger(__name__)


@dataclass
class RetentionConfig:
    """日志/产物/临时文件保留策略。"""

    log_retention_days: int = 30
    artifact_retention_days: int = 30
    temp_max_age_hours: int = 24
    max_artifacts_per_task: int = 50


class ResourceCleanupService:
    """按保留策略清理过期资源，物理删除前做路径越界保护。"""

    def __init__(
        self,
        artifacts_root: Path,
        config: RetentionConfig | None = None,
    ) -> None:
        self._artifacts_root = Path(artifacts_root).resolve()
        self._config = config or RetentionConfig()

    def cleanup_expired_artifacts(
        self,
        session: Session,
        now: datetime,
        retention_days: int | None = None,
    ) -> int:
        """删除过期产物行及其物理文件，返回删除行数。

        物理文件必须 resolve 后位于 artifacts 根目录内且不是根目录本身，
        否则跳过文件删除并记录警告；DB 行仍按过期清理。
        """
        if retention_days is None:
            retention_days = self._config.artifact_retention_days
        cutoff = now - timedelta(days=retention_days)
        stmt = select(ExecutionArtifactRecord).where(
            ExecutionArtifactRecord.created_at < cutoff
        )
        records = session.execute(stmt).scalars().all()

        deleted = 0
        for record in records:
            self._safe_delete(Path(record.path), self._artifacts_root)
            session.delete(record)
            deleted += 1
        return deleted

    def cleanup_expired_logs(
        self,
        log_dir: Path,
        now: datetime,
        retention_days: int | None = None,
    ) -> int:
        """按文件 mtime 删除过期日志文件，返回删除数。"""
        if retention_days is None:
            retention_days = self._config.log_retention_days
        cutoff = now - timedelta(days=retention_days)
        root = Path(log_dir).resolve()
        if not root.is_dir():
            return 0

        deleted = 0
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            if self._is_expired(entry, cutoff) and self._safe_delete(entry, root):
                deleted += 1
        return deleted

    def cleanup_temp_files(
        self,
        temp_dir: Path,
        now: datetime,
        max_age_hours: int | None = None,
    ) -> int:
        """按 mtime 删除过期临时文件/目录（仅限目标目录内），返回删除数。"""
        if max_age_hours is None:
            max_age_hours = self._config.temp_max_age_hours
        cutoff = now - timedelta(hours=max_age_hours)
        root = Path(temp_dir).resolve()
        if not root.is_dir():
            return 0

        deleted = 0
        for entry in root.iterdir():
            if self._is_expired(entry, cutoff) and self._safe_delete(entry, root):
                deleted += 1
        return deleted

    def enforce_artifact_limit(
        self,
        session: Session,
        task_id: str,
        max_count: int | None = None,
    ) -> int:
        """按 created_at 保留最新 N 条，删除更旧的行与物理文件，返回删除行数。"""
        if max_count is None:
            max_count = self._config.max_artifacts_per_task
        stmt = (
            select(ExecutionArtifactRecord)
            .where(ExecutionArtifactRecord.task_id == task_id)
            .order_by(
                ExecutionArtifactRecord.created_at.asc(),
                ExecutionArtifactRecord.id.asc(),
            )
        )
        records = session.execute(stmt).scalars().all()
        to_delete = records[:-max_count] if max_count > 0 else records

        deleted = 0
        for record in to_delete:
            self._safe_delete(Path(record.path), self._artifacts_root)
            session.delete(record)
            deleted += 1
        return deleted

    @staticmethod
    def _is_expired(entry: Path, cutoff: datetime) -> bool:
        """按文件/目录 mtime 判断是否早于截止时间。"""
        try:
            mtime = datetime.fromtimestamp(
                entry.stat().st_mtime,
                tz=timezone.utc,
            )
        except OSError:
            return False
        return mtime < cutoff

    @staticmethod
    def _safe_delete(path: Path, root: Path) -> bool:
        """安全删除：resolve 后必须位于 root 内且不是 root 本身。"""
        root = root.resolve()
        target = path if path.is_absolute() else root / path
        target = target.resolve()
        if target == root or not target.is_relative_to(root):
            logger.warning("跳过越界资源删除 path=%s root=%s", path, root)
            return False
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("资源删除失败 path=%s error=%s", target, exc)
            return False
        return True
