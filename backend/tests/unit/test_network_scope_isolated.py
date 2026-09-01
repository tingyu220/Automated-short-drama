"""验证 Network Scope 隔离：不同任务的 captures 不混入。"""
from __future__ import annotations

from backend.platforms.tomato.network.network_listener import NetworkListener


class _FakePage:
    def __init__(self):
        self._listeners = {}

    def on(self, event, handler):
        self._listeners.setdefault(event, []).append(handler)

    def remove_listener(self, event, handler):
        if event in self._listeners:
            self._listeners[event] = [h for h in self._listeners[event] if h is not handler]


class _FakeResponse:
    def __init__(self, url, body, status=200):
        self.url = url
        self.status = status
        self._body = body
        self.request = type("Req", (), {"method": "GET", "all_headers": lambda: {}})()

    def header_value(self, name):
        return "application/json"

    def json(self):
        return self._body

    def text(self):
        return ""


class TestNetworkScopeIsolation:
    """Phase 5: NetworkListener 的 scope 隔离。"""

    def test_begin_scope_clears_previous_captures(self):
        """begin_scope 清除前一个任务的 captures。"""
        page = _FakePage()
        listener = NetworkListener(page)

        listener._on_response(
            _FakeResponse("https://changdupingtai.com/api/promotion/list", {"data": []})
        )
        assert len(listener.captures) == 1

        listener.begin_scope("task-B")
        assert len(listener.captures) == 0

    def test_captures_between_tasks_are_isolated(self):
        """任务 A 的 captures 不会出现在任务 B 中。"""
        page = _FakePage()
        listener = NetworkListener(page)

        listener.begin_scope("task-A")
        listener._on_response(
            _FakeResponse("https://changdupingtai.com/api/promotion/list", {"data": [{"id": "A1"}]})
        )
        assert len(listener.captures) == 1

        listener.end_scope()
        listener.begin_scope("task-B")
        listener._on_response(
            _FakeResponse("https://changdupingtai.com/api/promotion/list", {"data": [{"id": "B1"}]})
        )

        captures = listener.captures
        assert len(captures) == 1
        body = captures[0].response_body
        assert body["data"][0]["id"] == "B1"

    def test_end_scope_stops_recording(self):
        """end_scope 后不记录新 capture。"""
        page = _FakePage()
        listener = NetworkListener(page)

        listener.begin_scope("task-A")
        listener._on_response(
            _FakeResponse("https://changdupingtai.com/api/promotion/list", {"data": []})
        )
        listener.end_scope()

        listener._on_response(
            _FakeResponse("https://changdupingtai.com/api/promotion/list", {"data": [{"id": "X"}]})
        )
        assert len(listener.captures) == 1

    def test_scope_task_id_tracked(self):
        """begin_scope 记录当前 task_id。"""
        page = _FakePage()
        listener = NetworkListener(page)

        listener.begin_scope("task-A")
        assert listener.scope_task_id == "task-A"

        listener.end_scope()
        assert listener.scope_task_id is None
