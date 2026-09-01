"""Playwright 网络响应监听器与业务接口识别。

Phase 5: 只做发现与记录，不解析业务数据、不替代 DOM。
所有敏感头（Authorization / Cookie / Set-Cookie）在记录前必须脱敏。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
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
}

# 业务端点关键字 → 端点类型
# URL 路径中包含这些关键字时归类到对应端点类型
_ENDPOINT_PATTERNS: list[tuple[str, str]] = [
    # 推广链接相关
    ("promotion/list", "PROMOTION_LIST"),
    ("promotion/detail", "PROMOTION_DETAIL"),
    ("promotion/create", "PROMOTION_CREATE"),
    ("promotionlink/list", "PROMOTION_LIST"),
    ("promotionlink/detail", "PROMOTION_DETAIL"),
    ("promotionlink/create", "PROMOTION_CREATE"),
    # 模板相关
    ("template/list", "TEMPLATE_LIST"),
    ("template/detail", "TEMPLATE_DETAIL"),
    # 剧目搜索
    ("drama/search", "DRAMA_SEARCH"),
    ("drama/list", "DRAMA_SEARCH"),
    ("playlet/search", "DRAMA_SEARCH"),
    ("playlet/list", "DRAMA_SEARCH"),
]


@dataclass
class NetworkCapture:
    """一次脱敏后的业务网络响应记录。"""

    url: str
    method: str
    status: int
    endpoint_type: str
    response_body: dict[str, Any] | list[Any] = field(default_factory=dict)
    sanitized_request_headers: dict[str, str] = field(default_factory=dict)
    sanitized_response_headers: dict[str, str] = field(default_factory=dict)
    captured_at: str = ""


class NetworkListener:
    """挂载到 Playwright Page 上，监听并记录业务接口响应。

    只保留 JSON 格式的业务响应，自动跳过静态资源和非平台域名请求。
    所有 header 在保存前经过脱敏，不含 Authorization / Cookie / Set-Cookie。
    """

    def __init__(
        self,
        page: Any,
        *,
        platform_domain_keyword: str = "changdupingtai",
    ) -> None:
        self._page = page
        self._domain_keyword = platform_domain_keyword
        self._captures: list[NetworkCapture] = []
        self._handler = self._on_response
        if page is not None:
            page.on("response", self._handler)

    @property
    def captures(self) -> list[NetworkCapture]:
        """所有已捕获的业务响应。"""
        return list(self._captures)

    @property
    def grouped_captures(self) -> dict[str, list[NetworkCapture]]:
        """按端点类型分组的捕获结果。"""
        groups: dict[str, list[NetworkCapture]] = {}
        for cap in self._captures:
            groups.setdefault(cap.endpoint_type, []).append(cap)
        return groups

    def summary(self) -> dict[str, Any]:
        """返回发现摘要，供 diagnostics 使用。"""
        grouped = self.grouped_captures
        return {
            "capture_count": len(self._captures),
            "endpoint_counts": {
                endpoint_type: len(caps)
                for endpoint_type, caps in grouped.items()
            },
            "endpoint_types": sorted(grouped.keys()),
        }

    def stop(self) -> None:
        """停止监听，从 page 上移除回调。"""
        if self._page is not None:
            try:
                self._page.remove_listener("response", self._handler)
            except Exception:
                logger.debug("移除 network response listener 失败", exc_info=True)

    # ------------------------------------------------------------------
    # 内部：响应处理
    # ------------------------------------------------------------------

    def _on_response(self, response: Any) -> None:
        """Playwright response 事件回调。"""
        try:
            self._try_capture(response)
        except Exception:
            # 监听失败不能影响主流程
            logger.debug("网络响应捕获失败: %s", response.url, exc_info=True)

    def _try_capture(self, response: Any) -> bool:
        url = getattr(response, "url", "")
        if not url:
            return False

        # 域名过滤：只保留业务平台的请求
        if self._domain_keyword and self._domain_keyword.lower() not in url.lower():
            return False

        # 只捕获成功的 JSON 响应
        status = getattr(response, "status", 0)
        if status < 200 or status >= 300:
            return False

        # 检查 Content-Type
        try:
            content_type = response.header_value("content-type") or ""
        except Exception:
            content_type = ""
        if "json" not in content_type.lower() and "javascript" not in content_type.lower():
            # 尝试解析 JSON，如果失败就跳过
            pass

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

        # 读取并脱敏 headers
        try:
            resp_headers_raw = response.all_headers() or {}
        except Exception:
            resp_headers_raw = {}
        resp_headers = _sanitize_headers(resp_headers_raw)

        # 获取请求方法（Playwright Response 有 request 属性）
        method = "GET"
        try:
            req = response.request
            if req is not None:
                method = getattr(req, "method", "GET") or "GET"
                try:
                    req_headers_raw = req.all_headers() or {}
                except Exception:
                    req_headers_raw = {}
                req_headers = _sanitize_headers(req_headers_raw)
            else:
                req_headers = {}
        except Exception:
            req_headers = {}

        endpoint_type = _classify_endpoint(url, method)

        capture = NetworkCapture(
            url=url,
            method=method.upper(),
            status=status,
            endpoint_type=endpoint_type,
            response_body=body,
            sanitized_request_headers=req_headers,
            sanitized_response_headers=resp_headers,
        )
        self._captures.append(capture)
        logger.info(
            "NetworkDiscovery 捕获接口: %s %s status=%d type=%s",
            method,
            url[:120],
            status,
            endpoint_type,
        )
        return True


# ---------------------------------------------------------------------------
# 模块级辅助函数
# ---------------------------------------------------------------------------


def _sanitize_headers(headers: dict[str, str] | Any) -> dict[str, str]:
    """移除敏感 header，返回全小写 key 的新字典。

    移除：Authorization, Cookie, Set-Cookie, X-Auth-Token, Token, Session 等。
    值为空的也一并移除。
    """
    if not isinstance(headers, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str):
            continue
        key_lower = key.lower()
        if key_lower in _SENSITIVE_HEADERS:
            continue
        # 也检查 key 中包含敏感词的情况
        if any(sens in key_lower for sens in _SENSITIVE_HEADERS):
            continue
        if value is None:
            continue
        result[key_lower] = str(value)
    return result


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
