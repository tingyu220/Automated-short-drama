"""番茄网络接口发现阶段测试（Phase 5）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.domain.assets.promotion_asset import AcquisitionMethod
from backend.domain.ports.adapters import PromotionLink, TemplateInfo
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.tomato.network.network_listener import (
    NetworkCapture,
    NetworkListener,
    _sanitize_headers,
    _classify_endpoint,
)
from backend.platforms.tomato.providers.network_discovery_provider import (
    NetworkDiscoveryProvider,
)


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# NetworkCapture 数据类
# ---------------------------------------------------------------------------


def test_network_capture_stores_basic_fields() -> None:
    capture = NetworkCapture(
        url="https://example.com/api/promotion/list",
        method="GET",
        status=200,
        endpoint_type="PROMOTION_LIST",
        response_body={"code": 0, "data": {"items": []}},
    )

    assert capture.endpoint_type == "PROMOTION_LIST"
    assert capture.method == "GET"
    assert capture.status == 200
    assert "items" in capture.response_body["data"]


def test_network_capture_has_sanitized_headers_field() -> None:
    capture = NetworkCapture(
        url="https://example.com/api",
        method="POST",
        status=200,
        endpoint_type="UNKNOWN",
        response_body={},
        sanitized_request_headers={"content-type": "application/json"},
        sanitized_response_headers={"content-length": "123"},
    )

    # 确保不含有敏感字段
    assert "authorization" not in {
        k.lower() for k in capture.sanitized_request_headers
    }
    assert "cookie" not in {
        k.lower() for k in capture.sanitized_request_headers
    }
    assert "set-cookie" not in {
        k.lower() for k in capture.sanitized_response_headers
    }


# ---------------------------------------------------------------------------
# Header 脱敏
# ---------------------------------------------------------------------------


def test_sanitize_headers_removes_authorization_and_cookie() -> None:
    raw = {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret-token",
        "Cookie": "session=abc123",
        "X-Trace-Id": "trace-001",
    }

    result = _sanitize_headers(raw)

    assert "content-type" in result
    assert "x-trace-id" in result
    assert "authorization" not in result
    assert "cookie" not in result
    # 确保值也被移除了
    assert all("secret" not in v for v in result.values())
    assert all("abc123" not in v for v in result.values())


def test_sanitize_headers_removes_set_cookie_from_response() -> None:
    raw = {
        "Content-Length": "456",
        "Set-Cookie": "session=new-session; HttpOnly",
        "X-Request-Id": "req-002",
    }

    result = _sanitize_headers(raw)

    assert "set-cookie" not in result
    assert "x-request-id" in result
    assert all("new-session" not in v for v in result.values())


def test_sanitize_headers_handles_empty_and_none_values() -> None:
    raw = {"Authorization": "", "Content-Type": None, "Accept": "text/plain"}

    result = _sanitize_headers(raw)

    assert "authorization" not in result
    assert "accept" in result


# ---------------------------------------------------------------------------
# Endpoint 分类
# ---------------------------------------------------------------------------


def test_classify_promotion_list_endpoint() -> None:
    url = "https://changdupingtai.example.com/api/promotion/list?page=1"
    assert _classify_endpoint(url, "GET") == "PROMOTION_LIST"


def test_classify_promotion_detail_endpoint() -> None:
    url = "https://changdupingtai.example.com/api/promotion/detail?id=123"
    assert _classify_endpoint(url, "GET") == "PROMOTION_DETAIL"


def test_classify_drama_search_endpoint() -> None:
    url = "https://changdupingtai.example.com/api/drama/search?keyword=测试"
    assert _classify_endpoint(url, "GET") == "DRAMA_SEARCH"


def test_classify_template_list_endpoint() -> None:
    url = "https://changdupingtai.example.com/api/template/list"
    assert _classify_endpoint(url, "GET") == "TEMPLATE_LIST"


def test_classify_promotion_create_endpoint() -> None:
    url = "https://changdupingtai.example.com/api/promotion/create"
    assert _classify_endpoint(url, "POST") == "PROMOTION_CREATE"


def test_classify_unknown_endpoint() -> None:
    assert _classify_endpoint("https://example.com/other/path", "GET") == "UNKNOWN"


def test_classify_is_case_insensitive_for_keywords() -> None:
    url = "https://changdupingtai.example.com/api/Promotion/List"
    assert _classify_endpoint(url, "GET") == "PROMOTION_LIST"


# ---------------------------------------------------------------------------
# NetworkListener
# ---------------------------------------------------------------------------


class FakeResponse:
    """模拟 Playwright Response 对象的最小接口。"""

    def __init__(
        self,
        url: str,
        status: int = 200,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        json_body: dict | list | None = None,
        text_body: str = "",
    ) -> None:
        self._url = url
        self._status = status
        self._method = method
        self._headers = headers or {}
        self._json_body = json_body
        self._text_body = text_body

    @property
    def url(self) -> str:
        return self._url

    @property
    def status(self) -> int:
        return self._status

    @property
    def method(self) -> str:
        return self._method

    @property
    def headers_array(self) -> list[dict[str, str]]:
        # Playwright 返回的 headers 是 dict 形式，但我们用 all_headers()
        return []

    def all_headers(self) -> dict[str, str]:
        return dict(self._headers)

    def header_value(self, name: str) -> str | None:
        return self._headers.get(name)

    def json(self) -> dict | list:
        if self._json_body is not None:
            return self._json_body
        if self._text_body:
            return json.loads(self._text_body)
        return {}

    def text(self) -> str:
        if self._json_body is not None:
            return json.dumps(self._json_body, ensure_ascii=False)
        return self._text_body


class FakePage:
    """模拟 Playwright Page，支持 on("response") 注册回调。"""

    def __init__(self) -> None:
        self._response_handlers: list = []
        self._request_handlers: list = []

    def on(self, event: str, handler) -> None:
        if event == "response":
            self._response_handlers.append(handler)
        elif event == "request":
            self._request_handlers.append(handler)

    def remove_listener(self, event: str, handler) -> None:
        if event == "response":
            self._response_handlers = [
                h for h in self._response_handlers if h != handler
            ]

    def emit_response(self, response: FakeResponse) -> None:
        for handler in self._response_handlers:
            try:
                handler(response)
            except Exception:
                # listener 异常不应中断主流程
                pass


def test_network_listener_captures_business_responses() -> None:
    page = FakePage()
    listener = NetworkListener(page, platform_domain_keyword="changdupingtai")

    assert len(listener.captures) == 0

    # 触发一个业务接口响应
    page.emit_response(
        FakeResponse(
            url="https://changdupingtai.example.com/api/promotion/list?page=1",
            status=200,
            method="GET",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
            json_body={"code": 0, "data": {"items": [{"id": 1, "name": "测试剧"}]}},
        )
    )

    assert len(listener.captures) == 1
    assert listener.captures[0].endpoint_type == "PROMOTION_LIST"
    assert listener.captures[0].status == 200
    # 响应体应被保存
    assert listener.captures[0].response_body["code"] == 0
    # 敏感 header 必须被移除
    assert "authorization" not in {
        k.lower() for k in listener.captures[0].sanitized_response_headers
    }


def test_network_listener_ignores_non_platform_domains() -> None:
    page = FakePage()
    listener = NetworkListener(page, platform_domain_keyword="changdupingtai")

    # 第三方统计接口，不属于业务平台
    page.emit_response(
        FakeResponse(
            url="https://analytics.example.com/pixel?event=pageview",
            status=200,
            json_body={"ok": True},
        )
    )

    assert len(listener.captures) == 0


def test_network_listener_ignores_non_json_responses() -> None:
    page = FakePage()
    listener = NetworkListener(page, platform_domain_keyword="changdupingtai")

    # 静态资源
    page.emit_response(
        FakeResponse(
            url="https://changdupingtai.example.com/static/logo.png",
            status=200,
            headers={"Content-Type": "image/png"},
            text_body=b"\x89PNG\r\n".decode("latin-1"),
        )
    )

    assert len(listener.captures) == 0


def test_network_listener_handles_json_parse_errors_gracefully() -> None:
    page = FakePage()
    listener = NetworkListener(page, platform_domain_keyword="changdupingtai")

    page.emit_response(
        FakeResponse(
            url="https://changdupingtai.example.com/api/promotion/list",
            status=500,
            headers={"Content-Type": "text/html"},
            text_body="<html>Server Error</html>",
        )
    )

    # 不应该抛出异常
    assert len(listener.captures) == 0


def test_network_listener_stop_removes_handler() -> None:
    page = FakePage()
    listener = NetworkListener(page, platform_domain_keyword="changdupingtai")

    assert len(page._response_handlers) == 1

    listener.stop()

    assert len(page._response_handlers) == 0

    # 停止后不再捕获
    page.emit_response(
        FakeResponse(
            url="https://changdupingtai.example.com/api/promotion/list",
            json_body={"code": 0},
        )
    )
    assert len(listener.captures) == 0


def test_network_listener_groups_by_endpoint_type() -> None:
    page = FakePage()
    listener = NetworkListener(page, platform_domain_keyword="changdupingtai")

    page.emit_response(
        FakeResponse(
            url="https://changdupingtai.example.com/api/promotion/list",
            json_body={"code": 0, "data": {"items": []}},
        )
    )
    page.emit_response(
        FakeResponse(
            url="https://changdupingtai.example.com/api/promotion/detail?id=1",
            json_body={"code": 0, "data": {"id": 1}},
        )
    )
    page.emit_response(
        FakeResponse(
            url="https://changdupingtai.example.com/api/drama/search?kw=test",
            json_body={"code": 0, "data": []},
        )
    )

    grouped = listener.grouped_captures
    assert "PROMOTION_LIST" in grouped
    assert "PROMOTION_DETAIL" in grouped
    assert "DRAMA_SEARCH" in grouped
    assert len(grouped["PROMOTION_LIST"]) == 1
    assert len(grouped["PROMOTION_DETAIL"]) == 1
    assert len(grouped["DRAMA_SEARCH"]) == 1


# ---------------------------------------------------------------------------
# NetworkDiscoveryProvider
# ---------------------------------------------------------------------------


class RecordingTomato:
    """记录旧链路收到的确定性剧目上下文。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def get_episode_count(self, drama_name, available_time, confirmed_match=None):
        self.calls.append(("episode", drama_name, available_time, confirmed_match))
        return 60

    def extract_iaa_link(
        self,
        drama_name,
        available_time,
        episode_count,
        selected_episode,
        confirmed_match=None,
    ):
        self.calls.append(
            (
                "iaa",
                drama_name,
                available_time,
                episode_count,
                selected_episode,
                confirmed_match,
            )
        )
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAA",
            promotion_url="mock://iaa/测试剧?ep=2",
            source_platform="TOMATO",
            source_entry="FREE",
            acquisition_method="PROMOTION_LIST_VIEW",
        )

    def scan_iap_templates(self, drama_name, available_time, confirmed_match=None):
        self.calls.append(("templates", drama_name, available_time, confirmed_match))
        return [TemplateInfo("tpl-2.9", drama_name, "2.9模板", 2.9, 1)]

    def generate_iap_link(
        self,
        drama_name,
        available_time,
        template,
        confirmed_match=None,
        **kwargs,
    ):
        self.calls.append(
            (
                "iap",
                drama_name,
                available_time,
                template.template_id,
                confirmed_match,
            )
        )
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAP",
            promotion_url="mock://iap/测试剧?tpl=tpl-2.9",
            source_platform="TOMATO",
            source_entry="PAID",
            acquisition_method="PAGE_EXTRACTION",
        )


def _rules() -> list[TemplatePriceRule]:
    return [
        TemplatePriceRule(
            key="iap_2_9",
            target_price=2.9,
            min_price=2.6,
            max_price=5.0,
        )
    ]


def test_discovery_provider_delegates_to_legacy_and_records_network() -> None:
    """Discovery Provider 包装 Legacy，在执行期间监听网络。"""
    tomato = RecordingTomato()
    provider = NetworkDiscoveryProvider(tomato, _rules(), page=None)

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )

    result = provider.acquire(task)

    # Legacy 的结果应该保持不变
    assert result.expected_types == ["IAA", "2.9"]
    assert len(result.candidates) == 2
    # Discovery 方法标记
    assert all(
        asset.acquisition_method == AcquisitionMethod.LEGACY
        for asset in result.candidates
    )
    # diagnostics 中包含 network discovery 信息
    assert "network_discovery" in result.diagnostics


def test_discovery_provider_diagnostics_contains_endpoint_summary() -> None:
    """diagnostics 中应包含各端点类型的发现统计。"""
    tomato = RecordingTomato()
    provider = NetworkDiscoveryProvider(tomato, _rules(), page=None)

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )

    result = provider.acquire(task)
    discovery_info = result.diagnostics["network_discovery"]

    assert "endpoint_counts" in discovery_info
    assert "capture_count" in discovery_info
    assert "provider" in discovery_info
    assert discovery_info["provider"] == "NETWORK_DISCOVERY"
