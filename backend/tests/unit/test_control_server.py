from types import SimpleNamespace

import backend.bootstrap.control_server as control_server


def test_scheduler_uses_real_sheet_when_private_sheet_is_configured(monkeypatch) -> None:
    class FakeFeishu:
        def __init__(self, url, name, dry_run):
            self.url = url
            self.name = name
            self.dry_run = dry_run

    monkeypatch.delenv("WORKBUDDY_USE_REAL_ADAPTERS", raising=False)
    monkeypatch.setattr(
        control_server,
        "Settings",
        lambda: SimpleNamespace(
            use_real_adapters=False,
            feishu_private_sheet_url="https://example.feishu.cn/wiki/private",
            feishu_private_sheet_name="剧目表",
        ),
    )
    monkeypatch.setattr(control_server, "RealFeishuAdapter", FakeFeishu)

    adapter, mode = control_server._build_scheduler_feishu()

    assert mode == "real"
    assert adapter.url == "https://example.feishu.cn/wiki/private"
    assert adapter.dry_run is False
