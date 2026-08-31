"""投放系统剧目资源页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError
from backend.domain.ports.adapters import DramaAsset


RESULT_UNCERTAIN = "RESULT_UNCERTAIN"
SESSION_EXPIRED = "SESSION_EXPIRED"
_WAIT_TIMEOUT = 30000


class DramaAssetPage:
    """剧目资源操作：搜索、创建、按名称幂等获取."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def _check_session(self) -> None:
        """检查是否被重定向到登录页或会话失效。"""
        current_url = self._page.url
        url_lower = current_url.lower()
        if any(kw in url_lower for kw in ("login", "passport", "auth", "sso")):
            raise ExternalAdapterError(
                "投放系统登录态已失效，请重新登录",
                code=SESSION_EXPIRED,
                details={"current_url": current_url},
            )
        try:
            has_login_form = self._page.locator(
                "input[type='password']"
            ).first.is_visible(timeout=1000)
        except Exception:
            has_login_form = False
        if has_login_form:
            raise ExternalAdapterError(
                "投放系统登录态已失效（检测到登录表单），请重新登录",
                code=SESSION_EXPIRED,
                details={"current_url": current_url},
            )

    def _wait_stable(self, selector: str) -> None:
        """显式等待元素可见后额外等待 SPA 渲染沉淀。

        先用短超时（5s）快速探测，失败后再做会话检测，
        避免会话失效时傻等 30 秒才报 TimeoutError。
        """
        self._check_session()
        loc = self._page.locator(selector)
        try:
            loc.wait_for(state="visible", timeout=5000)
        except Exception:
            self._check_session()
            body_text = ""
            try:
                body_text = self._page.locator("body").inner_text(timeout=2000)
            except Exception:
                pass
            if any(
                kw in body_text
                for kw in ("登录", "登陆", "请重新登录", "未登录", "身份已过期")
            ):
                raise ExternalAdapterError(
                    "投放系统登录态已失效（页面提示重新登录），请重新登录",
                    code=SESSION_EXPIRED,
                    details={
                        "current_url": self._page.url,
                        "body_snippet": body_text[:200],
                    },
                )
            loc.wait_for(state="visible", timeout=_WAIT_TIMEOUT)
        self._page.wait_for_timeout(2000)

    def search(self, drama_name: str) -> bool:
        resp = self._page.goto(
            self._selectors["asset_page_url"],
            wait_until="networkidle",
            timeout=60000,
        )
        if resp and resp.status >= 500:
            raise ExternalAdapterError(
                f"投放系统服务器错误 (HTTP {resp.status})，请稍后重试",
                code="SERVER_ERROR",
                details={"url": self._selectors["asset_page_url"], "status": resp.status},
            )
        if resp and resp.status >= 300 and resp.status != 304:
            raise ExternalAdapterError(
                f"投放系统返回异常状态码 (HTTP {resp.status})",
                code="SERVER_ERROR",
                details={"url": self._selectors["asset_page_url"], "status": resp.status},
            )
        self._wait_stable(self._selectors["asset_search_input"])
        self._page.locator(self._selectors["asset_search_input"]).fill(drama_name)
        self._page.locator(self._selectors["asset_search_button"]).click()
        self._page.wait_for_timeout(2000)
        rows = self._page.locator(
            self._selectors.get("config_row", ".el-table__row")
        ).evaluate_all("(rows) => rows.map(row => row.innerText.trim())")
        return any(drama_name in row for row in rows)

    def create(self, drama_name: str, link: str) -> DramaAsset:
        """创建剧目资源：填剧目名称 + 链接，保存前读取专辑ID."""
        self._page.locator(self._selectors["asset_create_button"]).click()
        self._wait_stable(self._selectors["asset_drama_name_input"])
        self._page.locator(self._selectors["asset_drama_name_input"]).fill(drama_name)
        self._page.locator(self._selectors["asset_link_input"]).fill(link)
        self._page.wait_for_timeout(2000)
        album_id = (
            self._page.locator(self._selectors["album_id_field"]).input_value() or ""
        ).strip()
        self._page.locator(self._selectors["asset_save_button"]).click()
        self._page.wait_for_timeout(2000)
        delivery_drama_id = album_id
        if not delivery_drama_id:
            raise ExternalAdapterError(
                "剧目资源创建后未读到 delivery_drama_id，结果不确定",
                code=RESULT_UNCERTAIN,
            )
        return DramaAsset(
            delivery_drama_id=delivery_drama_id,
            drama_name=drama_name,
            link=link,
            album_id=album_id,
        )

    def find_or_create(self, drama_name: str, link: str) -> DramaAsset:
        """存在则复用，不存在则创建，保证按名称幂等."""
        if self.search(drama_name):
            delivery_drama_id = self._extract_drama_id_from_row(drama_name)
            return DramaAsset(
                delivery_drama_id=delivery_drama_id,
                drama_name=drama_name,
                link=link,
                album_id=delivery_drama_id,
            )
        return self.create(drama_name, link)

    def _extract_drama_id_from_row(self, drama_name: str) -> str:
        """从搜索结果表格中提取剧目ID（纯数字，15-20位）。"""
        import re
        rows = self._page.locator(
            self._selectors.get("config_row", ".el-table__row")
        )
        count = rows.count()
        for i in range(count):
            row = rows.nth(i)
            text = row.inner_text(timeout=2000)
            if drama_name in text:
                match = re.search(r"\b(\d{15,20})\b", text)
                if match:
                    return match.group(1)
        return ""
