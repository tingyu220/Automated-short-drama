"""优选平台网络响应监听器（M0-6 Discovery 阶段）。

只做发现与记录，不执行任何创建/修改操作。
所有敏感头（Authorization / Cookie / Set-Cookie / Token）在记录前必须脱敏。

监听目标：
- 剧名搜索
- 剧目版本列表
- 小程序列表
- 充值模板列表
- Promotion 查询
- Promotion 创建请求/响应
- 小程序路径
- 小程序链接
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# 敏感 header 名称（小写匹配）
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-auth-token",
    "token",
    "session",
    "session-id",
    "x-csrf-token",
    "csrf-token",
}

# 敏感 body 字段（响应/请求体中的敏感 key）
_SENSITIVE_BODY_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "private_key",
}

# 优选业务端点模式 → 端点类型
# M0 先按关键词粗分类，后续随 Discovery 深入再细化
_ENDPOINT_PATTERNS: list[tuple[str, str]] = [
    # 剧目搜索 / 列表
    ("drama/search", "DRAMA_SEARCH"),
    ("drama/list", "DRAMA_LIST"),
    ("playlet/search", "DRAMA_SEARCH"),
    ("playlet/list", "DRAMA_LIST"),
    ("album/search", "DRAMA_SEARCH"),
    ("album/list", "DRAMA_LIST"),
    # 剧目版本
    ("version/list", "DRAMA_VERSION_LIST"),
    ("version/detail", "DRAMA_VERSION_DETAIL"),
    # 小程序
    ("miniprogram/list", "MINIPROGRAM_LIST"),
    ("miniprogram/detail", "MINIPROGRAM_DETAIL"),
    ("mini_program/list", "MINIPROGRAM_LIST"),
    ("mini_program/detail", "MINIPROGRAM_DETAIL"),
    ("weapp/list", "MINIPROGRAM_LIST"),
    ("weapp/detail", "MINIPROGRAM_DETAIL"),
    # 充值模板
    ("recharge/list", "TEMPLATE_LIST"),
    ("recharge/detail", "TEMPLATE_DETAIL"),
    ("template/list", "TEMPLATE_LIST"),
    ("template/detail", "TEMPLATE_DETAIL"),
    # Promotion
    ("promotion/list", "PROMOTION_LIST"),
    ("promotion/detail", "PROMOTION_DETAIL"),
    ("promotion/create", "PROMOTION_CREATE"),
    ("promotion/update", "PROMOTION_UPDATE"),
    ("promotionlink/list", "PROMOTION_LIST"),
    ("promotionlink/create", "PROMOTION_CREATE"),
    # 小程序路径 / 链接
    ("path/list", "MINIPROGRAM_PATH"),
    ("link/list", "MINIPROGRAM_LINK"),
    ("miniprogram/path", "MINIPROGRAM_PATH"),
    ("miniprogram/link", "MINIPROGRAM_LINK"),
]


@dataclass
class NetworkCaptureRecord:
    """一次脱敏后的业务网络响应记录。"""

    url: str
    method: str
    status: int
    endpoint_type: str
    response_body: dict[str, Any] | list[Any] = field(default_factory=dict)
    request_body_sanitized: dict[str, Any] | list[Any] | None = None
    sanitized_request_headers: dict[str, str] = field(default_factory=dict)
    sanitized_response_headers: dict[str, str] = field(default_factory=dict)
    captured_at: str = ""


class YouxuanNetworkListener:
    """挂载到 Playwright Page 上，监听并记录优选平台业务接口响应。

    安全要求（M0 只读）：
    - 只监听 response 事件，不修改、不提交
    - 自动脱敏所有敏感 header 和 body 字段
    - 只保留优选平台域名的 JSON 响应

    page 为 None 时安全降级为空实现。
    """

    def __init__(
        self,
        page: Any = None,
        *,
        platform_domain_keyword: str = "youxuan",
    ) -> None:
        self._page = page
        self._domain_keyword = platform_domain_keyword
        self._captures: list[NetworkCaptureRecord] = []
        self._handler = self._on_response
        if page is not None:
            page.on("response", self._handler)
            logger.info(
                "YouxuanNetworkListener 已挂载，domain_keyword=%s",
                platform_domain_keyword,
            )

    @property
    def captures(self) -> list[NetworkCaptureRecord]:
        """所有已捕获的业务响应（副本）。"""
        return list(self._captures)

    @property
    def grouped_captures(self) -> dict[str, list[NetworkCaptureRecord]]:
        """按端点类型分组。"""
        groups: dict[str, list[NetworkCaptureRecord]] = {}
        for cap in self._captures:
            groups.setdefault(cap.endpoint_type, []).append(cap)
        return groups

    def summary(self) -> dict[str, Any]:
        """发现摘要。"""
        grouped = self.grouped_captures
        return {
            "capture_count": len(self._captures),
            "endpoint_counts": {
                et: len(caps) for et, caps in grouped.items()
            },
            "endpoint_types": sorted(grouped.keys()),
        }

    def stop(self) -> None:
        """停止监听。"""
        if self._page is not None:
            try:
                self._page.remove_listener("response", self._handler)
            except Exception:
                logger.debug("移除 network response listener 失败", exc_info=True)
            logger.info("YouxuanNetworkListener 已停止，共捕获 %d 条", len(self._captures))

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_response(self, response: Any) -> None:
        """Playwright response 事件回调。"""
        try:
            self._try_capture(response)
        except Exception:
            logger.debug("网络响应捕获失败: %s", getattr(response, "url", "?"), exc_info=True)

    def _try_capture(self, response: Any) -> bool:
        url = getattr(response, "url", "")
        if not url:
            return False

        # 域名过滤
        if self._domain_keyword and self._domain_keyword.lower() not in url.lower():
            return False

        status = getattr(response, "status", 0)
        if status < 200 or status >= 500:  # 4xx 也保留，便于分析
            return False

        # 尝试读取响应体
        try:
            body = response.json()
        except Exception:
            try:
                text = response.text()
                if not text or not text.strip().startswith(("{", "[")):
                    return False
                body = json.loads(text)
            except Exception:
                return False

        if not isinstance(body, (dict, list)):
            return False

        # 脱敏响应 body
        sanitized_body = _sanitize_body(body)

        # 读取并脱敏 headers
        try:
            resp_headers_raw = response.all_headers() or {}
        except Exception:
            resp_headers_raw = {}
        resp_headers = _sanitize_headers(resp_headers_raw)

        # 请求信息
        method = "GET"
        req_headers: dict[str, str] = {}
        req_body_sanitized: dict | list | None = None
        try:
            req = response.request
            if req is not None:
                method = getattr(req, "method", "GET") or "GET"
                try:
                    req_headers_raw = req.all_headers() or {}
                except Exception:
                    req_headers_raw = {}
                req_headers = _sanitize_headers(req_headers_raw)
                # 请求体也脱敏保存（用于分析创建接口参数）
                try:
                    post_data = getattr(req, "post_data", None)
                    if callable(post_data):
                        post_data = post_data()
                    if post_data:
                        try:
                            req_body = json.loads(post_data)
                            req_body_sanitized = _sanitize_body(req_body)
                        except Exception:
                            req_body_sanitized = None
                except Exception:
                    pass
        except Exception:
            pass

        endpoint_type = _classify_endpoint(url, method)

        capture = NetworkCaptureRecord(
            url=url,
            method=method.upper(),
            status=status,
            endpoint_type=endpoint_type,
            response_body=sanitized_body,
            request_body_sanitized=req_body_sanitized,
            sanitized_request_headers=req_headers,
            sanitized_response_headers=resp_headers,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )
        self._captures.append(capture)
        logger.info(
            "Youxuan Discovery 捕获: %s %s status=%d type=%s",
            method,
            url[:120],
            status,
            endpoint_type,
        )
        return True


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _sanitize_headers(headers: dict[str, str] | Any) -> dict[str, str]:
    """移除敏感 header，返回全小写 key 的新字典。"""
    if not isinstance(headers, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str):
            continue
        key_lower = key.lower()
        if key_lower in _SENSITIVE_HEADERS:
            continue
        if any(sens in key_lower for sens in _SENSITIVE_HEADERS):
            continue
        if value is None:
            continue
        result[key_lower] = str(value)
    return result


def _sanitize_body(body: Any) -> Any:
    """递归移除 body 中的敏感字段。

    对字典中匹配敏感 key 的字段值替换为 "***"。
    """
    if isinstance(body, dict):
        result: dict[str, Any] = {}
        for key, value in body.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_BODY_KEYS:
                result[key] = "***"
            else:
                result[key] = _sanitize_body(value)
        return result
    if isinstance(body, list):
        return [_sanitize_body(item) for item in body]
    return body


def _classify_endpoint(url: str, method: str) -> str:
    """根据 URL 路径和 HTTP 方法归类业务端点类型。

    未匹配时返回 UNKNOWN。
    """
    if not url:
        return "UNKNOWN"
    url_lower = url.lower()
    for keyword, endpoint_type in _ENDPOINT_PATTERNS:
        if keyword.lower() in url_lower:
            return endpoint_type
    return "UNKNOWN"
