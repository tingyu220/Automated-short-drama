"""剧目任务的稳定来源标识。"""
from __future__ import annotations

import hashlib
import unicodedata

from backend.domain.tasks.end_type import EndType


_PLATFORM_ALIASES = {
    "番茄": "TOMATO",
    "TOMATO": "TOMATO",
    "剧变": "JUBIAN",
    "JUBIAN": "JUBIAN",
}


def build_task_source_key(
    drama_name: str,
    platform: str,
    raw_time: str,
    end_type: str = EndType.NATIVE,
) -> str:
    """以剧名、平台、端类型与表内 E 列原文构建跨插行稳定的业务键。"""
    parts = (
        _normalize(drama_name),
        _PLATFORM_ALIASES.get(_normalize(platform).upper(), _normalize(platform)),
        EndType.validate(end_type),
        raw_time.strip(),
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().lower().split())
