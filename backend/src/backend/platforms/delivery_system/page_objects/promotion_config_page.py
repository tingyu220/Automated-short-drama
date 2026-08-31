"""投放系统推广内容配置页面对象."""
from __future__ import annotations

import logging
from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError

logger = logging.getLogger(__name__)

DEFAULT_DISTRIBUTOR = "微智造"
PROMOTION_LINK_DRAMA_MISMATCH = "PROMOTION_LINK_DRAMA_MISMATCH"
RESULT_UNCERTAIN = "RESULT_UNCERTAIN"
SESSION_EXPIRED = "SESSION_EXPIRED"
_WAIT_TIMEOUT = 30000
_SEARCH_RETRIES = 3
_SEARCH_WAIT_MS = 2000
_POST_SAVE_RETRIES = 3


class PromotionConfigPage:
    """推广内容配置操作：搜索缺失项、创建并校验主剧与链接匹配."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

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

    def search(self, name: str) -> list[str]:
        """按配置名称搜索，返回名称匹配的搜索结果行文本."""
        resp = self._page.goto(
            self._selectors["config_page_url"], wait_until="networkidle"
        )
        if resp and resp.status >= 500:
            raise ExternalAdapterError(
                f"投放系统服务器错误 (HTTP {resp.status})，请稍后重试",
                code="SERVER_ERROR",
                details={"url": self._selectors["config_page_url"], "status": resp.status},
            )
        self._check_session()
        self._wait_stable(self._selectors["config_search_input"])
        row_selector = self._selectors.get("config_row", ".el-table__row")
        for attempt in range(_SEARCH_RETRIES):
            self._page.locator(self._selectors["config_search_input"]).fill(name)
            self._trigger_search()
            try:
                self._page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            self._page.wait_for_timeout(_SEARCH_WAIT_MS)
            raw_rows = self._page.locator(row_selector).evaluate_all(
                "(rows) => rows.map(row => row.innerText.trim())"
            )
            matched = [row for row in raw_rows if name in row]
            if matched:
                return matched
            if attempt < _SEARCH_RETRIES - 1:
                logger.debug(
                    "搜索第 %d 次未找到匹配（表格 %d 行），重试 name=%s",
                    attempt + 1, len(raw_rows), name,
                )
        logger.warning(
            "搜索 %d 次后仍未找到匹配 name=%s url=%s row_count=%d",
            _SEARCH_RETRIES, name, self._page.url, len(raw_rows) if raw_rows else 0,
        )
        return []

    def _trigger_search(self) -> None:
        """触发搜索：优先点击搜索按钮，回退 Enter 键。"""
        search_btn_selector = self._selectors.get("config_search_button")
        if search_btn_selector:
            try:
                btn = self._page.locator(search_btn_selector)
                if btn.is_visible(timeout=2000):
                    btn.click()
                    return
            except Exception:
                pass
        self._page.locator(self._selectors["config_search_input"]).press("Enter")

    def _fill_select_input(self, selector: str, value: str, fill_value: str = "") -> None:
        """Element UI el-select：先在输入框中过滤再选择匹配项.

        Args:
            selector: el-select input 的 CSS 选择器.
            value: 用于匹配下拉选项的完整文本.
            fill_value: 用于在输入框中过滤的短文本，默认与 value 相同.
        """
        loc = self._page.locator(selector)
        loc.evaluate("(el) => { const s = el.closest('.el-select'); if (s) s.click(); else el.click(); }")
        self._page.wait_for_timeout(2000)

        search_term = fill_value or value
        loc.evaluate(
            """(el, val) => {
                el.removeAttribute('readonly');
                el.value = val;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            search_term,
        )
        self._page.wait_for_timeout(2000)

        visible_items = self._page.locator(".el-select-dropdown__item:visible")
        count = visible_items.count()
        if count >= 1:
            target = visible_items.first
            if count > 1:
                for i in range(count):
                    item_text = visible_items.nth(i).inner_text(timeout=1000)
                    if value in item_text:
                        target = visible_items.nth(i)
                        break
            target.click(timeout=5000)
        self._page.wait_for_timeout(500)

    def create_missing(
        self, name: str, link: str, drama_name: str, link_type: str = ""
    ) -> str:
        """只创建缺失配置；保存后重新搜索验证创建成功."""
        existing = self.search(name)
        if existing:
            return name
        btn = self._page.locator(self._selectors["config_create_button"])
        btn.click()
        self._page.wait_for_timeout(2000)
        dialog = self._page.locator(".el-dialog:visible").first
        if not dialog.is_visible(timeout=1000):
            self._page.wait_for_timeout(3000)
            dialog = self._page.locator(".el-dialog:visible").first
        self._wait_stable(self._selectors["config_name_input"])
        self._page.locator(self._selectors["config_name_input"]).fill(name)
        drama_short = drama_name.split("，")[0] if "，" in drama_name else drama_name[:4]
        self._fill_select_input(self._selectors["config_main_drama"], drama_name, drama_short)
        ad_type = "IAA" if link_type.upper() == "IAA" else "付费"
        self._fill_select_input(self._selectors["config_ad_type"], ad_type)
        self._fill_select_input(self._selectors["config_distributor"], DEFAULT_DISTRIBUTOR)
        self._page.locator(self._selectors["config_link_input"]).fill(link)
        self._page.locator(self._selectors["config_save_button"]).click()
        self._page.wait_for_timeout(3000)
        # 对话框关闭即视为保存成功（Element UI 验证失败时对话框不会关闭）
        try:
            dialog_still_open = self._page.locator(
                ".el-dialog:visible"
            ).first.is_visible(timeout=1000)
        except Exception:
            dialog_still_open = False
        if dialog_still_open:
            try:
                form_errors = self._page.locator(
                    ".el-form-item__error"
                ).evaluate_all("(els) => els.map(el => el.innerText.trim())")
            except Exception:
                form_errors = []
            raise ExternalAdapterError(
                "推广内容配置保存失败，对话框未关闭",
                code=RESULT_UNCERTAIN,
                details={
                    "searched_name": name,
                    "drama_name": drama_name,
                    "form_errors": form_errors,
                    "page_url": self._page.url,
                },
            )
        # 对话框已关闭，保存成功，重新搜索验证（带重试）
        verified: list[str] = []
        last_row_count = 0
        for attempt in range(_POST_SAVE_RETRIES):
            if attempt > 0:
                logger.info("推广配置保存后第 %d 次重试搜索 name=%s", attempt + 1, name)
                self._page.wait_for_timeout(2000)
            verified = self.search(name)
            if verified:
                return name
            try:
                last_row_count = self._page.locator(
                    self._selectors.get("config_row", ".el-table__row")
                ).count()
            except Exception:
                pass
        raise ExternalAdapterError(
            "推广内容配置保存后搜索未找到记录",
            code=RESULT_UNCERTAIN,
            details={
                "searched_name": name,
                "drama_name": drama_name,
                "page_url": self._page.url,
                "row_count": last_row_count,
                "retries": _POST_SAVE_RETRIES,
            },
        )
