"""结构化 JSON 日志，支持敏感字段脱敏。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(token|password|cookie|secret|api_key)",
    re.IGNORECASE,
)

_HANDLER_INSTALLED = False


class _SanitizingFormatter(logging.Formatter):
    """JSON 格式化器，对敏感键值进行脱敏。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 合并 extra 字段，排除 LogRecord 内置属性
        _BUILTIN_ATTRS = {
            "args", "asctime", "created", "exc_info", "exc_text",
            "filename", "funcName", "levelname", "levelno",
            "lineno", "module", "msecs", "msg", "name", "pathname",
            "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName",
        }
        for key, value in record.__dict__.items():
            if key not in _BUILTIN_ATTRS:
                log_entry[key] = value

        log_entry = _sanitize_entry(log_entry)
        return json.dumps(log_entry, ensure_ascii=False, default=str)


def _sanitize_entry(entry: dict[str, object]) -> dict[str, object]:
    """递归遍历，将敏感键对应的值替换为 ***。"""
    sanitized: dict[str, object] = {}
    for key, value in entry.items():
        if isinstance(key, str) and _SENSITIVE_KEY_PATTERN.search(key):
            sanitized[key] = "***"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_entry(value)
        else:
            sanitized[key] = value
    return sanitized


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger，可重复调用不重复添加 handler。"""
    global _HANDLER_INSTALLED

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not _HANDLER_INSTALLED:
        _HANDLER_INSTALLED = True
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(_SanitizingFormatter())

        # 清除根 logger 的默认 handler，避免重复输出
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

        logger.addHandler(handler)
        logger.propagate = False

    return logger
