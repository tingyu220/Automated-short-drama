"""MiniProgram Network Discovery 结果持久化。

将脱敏后的网络捕获数据保存到 artifacts 目录，供人工分析和后续 parser 开发使用。

保存路径：
    data/artifacts/miniprogram/youxuan/network/{task_id}/{timestamp}_{endpoint_type}.json

安全：
- 保存前已经过脱敏（见 network_listener._sanitize_headers / _sanitize_body）
- 不包含 Cookie / Authorization / Token / Password 等敏感信息
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.miniprogram.platforms.youxuan.network.network_listener import (
    NetworkCaptureRecord,
)

logger = logging.getLogger(__name__)


def save_captures_to_artifacts(
    captures: list[NetworkCaptureRecord],
    task_id: str,
    artifacts_root: str | Path | None = None,
) -> Path:
    """将捕获数据保存到 artifacts 目录。

    按端点类型分文件存储，便于分析。

    Args:
        captures: 脱敏后的捕获记录列表
        task_id: 任务 ID
        artifacts_root: artifacts 根目录，默认 data/artifacts/miniprogram/youxuan/network

    Returns:
        本次保存的目录路径
    """
    if artifacts_root is None:
        artifacts_root = _default_artifacts_dir()

    task_dir = Path(artifacts_root) / task_id / _timestamp_dir()
    task_dir.mkdir(parents=True, exist_ok=True)

    # 按端点类型分组保存
    by_type: dict[str, list[NetworkCaptureRecord]] = {}
    for cap in captures:
        by_type.setdefault(cap.endpoint_type, []).append(cap)

    for endpoint_type, caps in by_type.items():
        file_path = task_dir / f"{endpoint_type.lower()}.json"
        data = [_capture_to_dict(c) for c in caps]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(
            "Discovery 保存: %s (%d 条) -> %s",
            endpoint_type,
            len(caps),
            file_path,
        )

    # 总览文件
    summary = {
        "task_id": task_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "capture_count": len(captures),
        "endpoint_counts": {
            et: len(caps) for et, caps in by_type.items()
        },
        "files": [f"{et.lower()}.json" for et in by_type.keys()],
    }
    summary_path = task_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return task_dir


def load_captures_from_artifacts(
    task_id: str,
    artifacts_root: str | Path | None = None,
) -> list[NetworkCaptureRecord]:
    """从 artifacts 加载某任务最近一次的捕获数据。

    Args:
        task_id: 任务 ID
        artifacts_root: artifacts 根目录

    Returns:
        捕获记录列表（按时间倒序，最新的在前）
    """
    if artifacts_root is None:
        artifacts_root = _default_artifacts_dir()

    task_dir = Path(artifacts_root) / task_id
    if not task_dir.is_dir():
        return []

    # 找最新的时间戳目录
    subdirs = sorted([d for d in task_dir.iterdir() if d.is_dir()], reverse=True)
    if not subdirs:
        return []

    latest_dir = subdirs[0]
    captures: list[NetworkCaptureRecord] = []

    for json_file in latest_dir.glob("*.json"):
        if json_file.name.startswith("_"):
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    captures.append(_dict_to_capture(item))
        except Exception:
            logger.warning("加载 Discovery 文件失败: %s", json_file, exc_info=True)

    # 按捕获时间倒序
    captures.sort(key=lambda c: c.captured_at, reverse=True)
    return captures


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _default_artifacts_dir() -> Path:
    """默认 artifacts 目录：data/artifacts/miniprogram/youxuan/network"""
    # 从 backend/src/backend/... 向上找项目根
    here = Path(__file__).resolve()
    project_root = here.parents[5]  # backend/src/backend/miniprogram/platforms/youxuan/
    return project_root / "data" / "artifacts" / "miniprogram" / "youxuan" / "network"


def _timestamp_dir() -> str:
    """生成时间戳目录名。"""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def _capture_to_dict(cap: NetworkCaptureRecord) -> dict[str, Any]:
    """捕获记录转可序列化字典。"""
    return {
        "url": cap.url,
        "method": cap.method,
        "status": cap.status,
        "endpoint_type": cap.endpoint_type,
        "response_body": cap.response_body,
        "request_body_sanitized": cap.request_body_sanitized,
        "sanitized_request_headers": cap.sanitized_request_headers,
        "sanitized_response_headers": cap.sanitized_response_headers,
        "captured_at": cap.captured_at,
    }


def _dict_to_capture(data: dict[str, Any]) -> NetworkCaptureRecord:
    """字典转捕获记录。"""
    return NetworkCaptureRecord(
        url=data.get("url", ""),
        method=data.get("method", "GET"),
        status=data.get("status", 0),
        endpoint_type=data.get("endpoint_type", "UNKNOWN"),
        response_body=data.get("response_body", {}),
        request_body_sanitized=data.get("request_body_sanitized"),
        sanitized_request_headers=data.get("sanitized_request_headers", {}),
        sanitized_response_headers=data.get("sanitized_response_headers", {}),
        captured_at=data.get("captured_at", ""),
    )
