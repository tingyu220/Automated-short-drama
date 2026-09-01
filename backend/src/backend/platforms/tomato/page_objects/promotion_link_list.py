"""番茄推广链接列表查询与查看。"""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError

logger = logging.getLogger(__name__)


def _drama_name_matches(row_name: str, drama_name: str) -> bool:
    """剧名模糊匹配：行名包含剧名 或 剧名包含行名。

    应对番茄推广链列表中剧名前后可能有空格、状态标签等差异。
    空字符串不匹配，避免误中。
    """
    if not row_name or not drama_name:
        return False
    return drama_name in row_name or row_name in drama_name


def _row_matches_drama(row_name: str, row_detail: str, drama_name: str) -> bool:
    """剧名匹配：name 列有值时用模糊匹配，为空时回退到 detail 文本包含。"""
    if row_name:
        return _drama_name_matches(row_name, drama_name)
    return bool(drama_name) and drama_name in row_detail


class PromotionLinkListPage:
    """按漫剧名和选集/模板唯一复用已生成链接。"""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def find_existing(self, drama_name: str, identity: str) -> str | None:
        """按历史兼容字段查找；行文本包含身份时也视为命中。多条匹配时取第一条。"""
        rows = self._search(drama_name)
        matches = [
            row
            for row in rows
            if _row_matches_drama(row[0].strip(), row[3].strip() if len(row) > 3 else "", drama_name.strip())
            and (
                row[1].strip() == identity.strip()
                or identity.strip() in row[3]
            )
        ]
        if not matches:
            return None
        if len(matches) > 1:
            logger.warning(
                "推广链列表存在 %d 条匹配记录，取第一条 drama=%s identity=%s",
                len(matches), drama_name, identity,
            )
        return self._view(int(matches[0][2]), drama_name, identity)[0]

    def find_iaa(self, drama_name: str, episode: int) -> str | None:
        """按推广链详情中的广告起始集数，从前往后命中第一条 IAA 链接。"""
        rows = self._search(drama_name)
        marker = re.compile(rf"(?<!\d)(?:第\s*)?{episode}\s*集(?!\d)")
        for row in rows:
            row_name = row[0].strip()
            row_detail = row[3].strip() if len(row) > 3 else ""
            if row_name:
                if drama_name.strip() not in row_name and row_name not in drama_name.strip():
                    continue
            else:
                if drama_name.strip() not in row_detail:
                    continue
            if not marker.search(row[3]):
                continue
            link, _ = self._view(int(row[2]), drama_name, f"{episode}集")
            return link
        return None

    def find_iap(self, drama_name: str, target_price: float) -> str | None:
        """按详情首档金额匹配目标 IAP 档位，命中第一条即停止。"""
        rows = self._search(drama_name)
        for row in rows:
            row_name = row[0].strip()
            row_detail = row[3].strip() if len(row) > 3 else ""
            if row_name:
                if drama_name.strip() not in row_name and row_name not in drama_name.strip():
                    continue
            else:
                if drama_name.strip() not in row_detail:
                    continue
            link, detail_text = self._view(
                int(row[2]), drama_name, str(target_price)
            )
            if _matches_target_price(detail_text, row[3], target_price):
                return link
        return None

    def list_iap(
        self, drama_name: str, *, search_type_name: str | None = "漫剧名称"
    ) -> list[tuple[float, str, str]]:
        """返回所有已生成的 IAP 链接 (档位, 链接, 标识)；档位无法判定时为 0.0。"""
        rows = self._search(drama_name, search_type_name=search_type_name)
        result: list[tuple[float, str, str]] = []
        for row in rows:
            row_name = row[0].strip()
            row_detail = row[3].strip() if len(row) > 3 else ""
            if row_name:
                if not _drama_name_matches(row_name, drama_name.strip()):
                    continue
            else:
                if drama_name.strip() not in row_detail:
                    continue
            try:
                link, detail_text = self._view(int(row[2]), drama_name, "IAP")
            except Exception as exc:
                logger.warning(
                    "list_iap 查看链接失败 row_name=%s identity=%s: %s",
                    row[0][:40],
                    row[1][:40] if len(row) > 1 else "",
                    str(exc)[:100],
                )
                result.append((-1.0, "", row[1].strip() if len(row) > 1 else ""))
                continue
            price = _classify_price(detail_text, row[3]) or 0.0
            print(
                f"[DEBUG list_iap] drama={drama_name} price={price} "
                f"identity={row[1][:60]} "
                f"row_text={row[3][:200].replace(chr(10), ' ')} "
                f"detail={detail_text[:300].replace(chr(10), ' ')}",
                flush=True,
            )
            logger.info(
                "list_iap 分类 price=%.1f identity=%s row_text_preview=%s detail_preview=%s",
                price,
                row[1][:40] if len(row) > 1 else "",
                row[3][:80].replace("\n", " ") if len(row) > 3 else "",
                detail_text[:80].replace("\n", " "),
            )
            result.append((price, link, row[1].strip()))
        return result

    def find_episode_count(self, drama_name: str) -> int | None:
        """从推广列表行的漫剧信息回退读取总集数。"""
        rows = self._search(drama_name)
        counts = []
        for row in rows:
            row_name = row[0].strip()
            row_detail = row[3].strip() if len(row) > 3 else ""
            if not _row_matches_drama(row_name, row_detail, drama_name.strip()):
                continue
            match = re.search(r"总集数\s*[:：]?\s*(\d+)\s*集", row[3])
            if match:
                counts.append(int(match.group(1)))
        return max(counts) if counts else None

    def debug_search_rows(self, drama_name: str) -> dict:
        """返回搜索结果的结构化信息，便于诊断匹配失败原因。"""
        page_url = self._page.url
        page_title = ""
        try:
            page_title = self._page.title()
        except Exception:
            pass
        rows = self._search(drama_name)
        # 额外诊断：页面文本、选择器计数、body 文本
        page_body_text = ""
        try:
            page_body_text = (
                self._page.locator("body").inner_text() or ""
            )[:1000]
        except Exception:
            pass
        row_selector = self._selectors["promotion_link_row"]
        row_count_on_page = 0
        try:
            row_count_on_page = self._page.locator(row_selector).count()
        except Exception:
            pass
        # 统计页面上所有 table/tr 元素数量
        table_count = 0
        tr_count = 0
        try:
            table_count = self._page.locator("table").count()
            tr_count = self._page.locator("tr").count()
        except Exception:
            pass
        # 诊断：获取所有 tr 的类名和文本预览
        tr_diag: list[dict] = []
        try:
            tr_infos = self._page.locator("tr").evaluate_all(
                """
                rows => rows.map((row, i) => ({
                    index: i,
                    className: row.className || "",
                    textPreview: (row.innerText || "").substring(0, 100),
                    childCount: row.children.length
                }))
                """
            )
            tr_diag = [dict(info) for info in tr_infos[:10]]
        except Exception:
            pass
        # 诊断：查找包含"查看"按钮的元素
        view_button_count = 0
        view_buttons_parent_classes: list[str] = []
        try:
            view_buttons = self._page.get_by_text("查看", exact=True)
            view_button_count = view_buttons.count()
            for i in range(min(view_button_count, 5)):
                try:
                    parent_class = view_buttons.nth(i).evaluate(
                        """
                        btn => {
                            let el = btn.parentElement;
                            let depth = 0;
                            while (el && depth < 5) {
                                if (el.className) return el.className;
                                el = el.parentElement;
                                depth++;
                            }
                            return "";
                        }
                        """
                    )
                    view_buttons_parent_classes.append(str(parent_class))
                except Exception:
                    pass
        except Exception:
            pass
        result_rows = []
        for row in rows:
            row_name = str(row[0]).strip()
            identity = str(row[1]).strip()
            index = int(row[2])
            detail = str(row[3]).strip()
            result_rows.append({
                "index": index,
                "row_name": row_name,
                "identity": identity,
                "detail_preview": detail[:200],
                "name_match": _drama_name_matches(row_name, drama_name.strip()),
            })
        return {
            "page_url": page_url,
            "page_title": page_title,
            "row_count_via_evaluate": len(result_rows),
            "row_count_via_count": row_count_on_page,
            "table_count": table_count,
            "tr_count": tr_count,
            "tr_details": tr_diag,
            "view_button_count": view_button_count,
            "view_button_parent_classes": view_buttons_parent_classes,
            "body_text_preview": page_body_text,
            "rows": result_rows,
        }

    def get_search_type_options(self) -> list[str]:
        """获取搜索类型下拉框的所有选项（诊断用）。"""
        search_type = self._selectors.get("promotion_link_search_type")
        if not search_type:
            return []
        type_index = int(self._selectors.get("promotion_link_search_type_index", 0))
        type_selector = self._page.locator(search_type).nth(type_index)
        try:
            type_selector.wait_for(state="visible", timeout=10000)
            type_selector.click()
            self._page.wait_for_timeout(500)
            options = self._page.locator(".arco-select-option").evaluate_all(
                "opts => opts.map(o => o.textContent.trim())"
            )
            # 点击空白处关闭下拉
            self._page.mouse.click(10, 10)
            self._page.wait_for_timeout(300)
            return [str(o) for o in options]
        except Exception:
            return []

    def _search(
        self, drama_name: str, *, search_type_name: str | None = "漫剧名称"
    ) -> list[tuple[str, str, int, str]]:
        self._page.goto(
            self._selectors["promotion_link_list_url"],
            wait_until="domcontentloaded",
            timeout=60000,
        )
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        current_url = self._page.url
        page_title = ""
        try:
            page_title = self._page.title()
        except Exception:
            pass
        print(f"[DEBUG _search] after goto: url={current_url} title={page_title[:50]}", flush=True)
        if search_type_name:
            search_type = self._selectors.get("promotion_link_search_type")
            if search_type:
                try:
                    type_index = int(self._selectors.get("promotion_link_search_type_index", 0))
                    type_selector = self._page.locator(search_type).nth(type_index)
                    type_selector.wait_for(state="visible", timeout=15000)
                    type_selector.click()
                    option = self._page.get_by_text(search_type_name, exact=True)
                    option.wait_for(state="visible", timeout=10000)
                    option.click()
                    print(f"[DEBUG _search] search_type selected: {search_type_name}", flush=True)
                except Exception as exc:
                    print(f"[DEBUG _search] search_type failed: {type(exc).__name__}: {str(exc)[:100]}", flush=True)
        try:
            search_input = self._page.locator(
                self._selectors["promotion_link_search_input"]
            )
            search_input.wait_for(state="visible", timeout=15000)
            search_input.click()
            search_input.fill("")
            search_input.type(drama_name)
            self._page.wait_for_timeout(500)
            self._page.locator(
                self._selectors["promotion_link_search_button"]
            ).click()
            print(f"[DEBUG _search] search submitted: drama={drama_name}", flush=True)
        except Exception as exc:
            print(f"[DEBUG _search] search input/button failed: {type(exc).__name__}: {str(exc)[:100]}", flush=True)
            return []
        row_selector = self._selectors["promotion_link_row"]
        for attempt in range(15):
            try:
                self._page.wait_for_selector(row_selector, timeout=2000)
                break
            except Exception:
                if attempt < 14:
                    self._page.wait_for_timeout(1000)
        self._page.wait_for_timeout(1000)
        raw_rows = self._page.locator(row_selector).evaluate_all(
            """
            (items, selectors) => items.map((item, index) => {
              const name = item.querySelector(selectors.name);
              let nameText = name ? name.textContent.trim() : "";
              const identity = item.querySelector(selectors.identity);
              const innerText = item.innerText || item.textContent || "";
              if (!nameText) {
                const m = innerText.match(/剧名[：:]\\s*(.+)/);
                if (m) nameText = m[1].trim();
              }
              return [
                nameText,
                identity ? identity.textContent.trim() : "",
                index,
                innerText
              ];
            })
            """,
            {
                "name": self._selectors["promotion_link_row_name"],
                "identity": self._selectors["promotion_link_row_identity"],
            },
        )
        print(f"[DEBUG _search] initial search raw_rows={len(raw_rows)} search_type={search_type_name}", flush=True)
        if not raw_rows:
            for _retry in range(2):
                self._page.wait_for_timeout(2000)
                search_input.click()
                search_input.fill("")
                search_input.type(drama_name)
                self._page.wait_for_timeout(500)
                self._page.keyboard.press("Enter")
                self._page.wait_for_timeout(2000)
                for attempt in range(10):
                    try:
                        self._page.wait_for_selector(row_selector, timeout=2000)
                        break
                    except Exception:
                        if attempt < 9:
                            self._page.wait_for_timeout(1000)
                self._page.wait_for_timeout(1000)
                raw_rows = self._page.locator(row_selector).evaluate_all(
                    """
                    (items, selectors) => items.map((item, index) => {
                      const name = item.querySelector(selectors.name);
                      let nameText = name ? name.textContent.trim() : "";
                      const identity = item.querySelector(selectors.identity);
                      const innerText = item.innerText || item.textContent || "";
                      if (!nameText) {
                        const m = innerText.match(/剧名[：:]\\s*(.+)/);
                        if (m) nameText = m[1].trim();
                      }
                      return [
                        nameText,
                        identity ? identity.textContent.trim() : "",
                        index,
                        innerText
                      ];
                    })
                    """,
                    {
                        "name": self._selectors["promotion_link_row_name"],
                        "identity": self._selectors["promotion_link_row_identity"],
                    },
                )
                if raw_rows:
                    break
        return [
            (
                str(row[0]).strip(),
                str(row[1]).strip(),
                int(row[2]),
                str(row[3] if len(row) > 3 else "").strip(),
            )
            for row in raw_rows
            if len(row) >= 3
        ]

    def _view(self, row_index: int, drama_name: str, identity: str) -> tuple[str, str]:
        row_selector = self._selectors["promotion_link_row"]
        view_selectors = [
            "button:has-text('查看')",
            "a:has-text('查看')",
            "[role='button']:has-text('查看')",
            ".arco-btn:has-text('查看')",
            "td:last-child button",
            "td:last-child a",
            "td:last-child .arco-btn",
            "text=查看",
        ]
        last_error = None
        for attempt in range(3):
            try:
                self._close_any_open_drawer()
                self._page.wait_for_timeout(1000 * (attempt + 1))
                row = self._page.locator(row_selector).nth(row_index)
                row.wait_for(state="visible", timeout=10000)

                view_btn = None
                for sel in view_selectors:
                    try:
                        btn = row.locator(sel).first
                        btn.wait_for(state="visible", timeout=3000)
                        view_btn = btn
                        break
                    except Exception:
                        continue

                if view_btn is None:
                    try:
                        btn = self._page.locator(
                            f"{row_selector}:nth-child({row_index + 1}) >> button:has-text('查看')"
                        ).first
                        btn.wait_for(state="visible", timeout=3000)
                        view_btn = btn
                    except Exception:
                        pass

                if view_btn is None:
                    try:
                        row_text = row.inner_text()
                        btn = self._page.locator(
                            f"tr:has-text('{drama_name}') button:has-text('查看')"
                        ).first
                        btn.wait_for(state="visible", timeout=3000)
                        view_btn = btn
                    except Exception:
                        pass

                if view_btn is None:
                    if attempt < 2:
                        continue
                    diag = {"row_index": row_index, "drama_name": drama_name, "identity": identity}
                    try:
                        row_html = row.inner_html()
                        diag["row_html_preview"] = row_html[:500]
                    except Exception as row_exc:
                        diag["row_error"] = str(row_exc)
                    try:
                        all_btns = row.locator("button, a, [role='button']").count()
                        diag["row_clickable_count"] = all_btns
                    except Exception:
                        pass
                    raise ExternalAdapterError(
                        "番茄推广链接查看按钮未找到",
                        code="TOMATO_VIEW_BUTTON_NOT_FOUND",
                        details=diag,
                    )

                view_btn.click()

                detail_locator = self._page.locator(
                    self._selectors["promotion_link_detail"]
                ).first
                try:
                    detail_locator.wait_for(state="visible", timeout=15000)
                except Exception:
                    detail_locator.wait_for(state="attached", timeout=5000)
                link = (detail_locator.text_content() or "").strip()
                if not link:
                    if attempt < 2:
                        try:
                            self._page.keyboard.press("Escape")
                        except Exception:
                            pass
                        continue
                    raise ExternalAdapterError(
                        "番茄推广链接查看结果为空",
                        code="TOMATO_LINK_VIEW_EMPTY",
                        details={"drama_name": drama_name, "identity": identity},
                    )
                detail_selector = self._selectors.get(
                    "promotion_link_detail_container",
                    self._selectors["promotion_link_detail"],
                )
                detail_text = (
                    self._page.locator(detail_selector).first.text_content() or ""
                ).strip()
                self._close_any_open_drawer()
                return link, detail_text
            except ExternalAdapterError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    try:
                        self._page.keyboard.press("Escape")
                    except Exception:
                        pass
                    continue
                raise

        raise ExternalAdapterError(
            "番茄推广链接查看多次重试后仍失败",
            code="TOMATO_VIEW_BUTTON_NOT_FOUND",
            details={
                "row_index": row_index,
                "drama_name": drama_name,
                "identity": identity,
                "last_error": str(last_error) if last_error else "",
            },
        )

    def _close_any_open_drawer(self) -> None:
        """关闭可能残留的推广详情抽屉，并等待其完全消失。"""
        close_selector = self._selectors.get("promotion_link_close_button")
        if close_selector:
            try:
                btn = self._page.locator(close_selector)
                if btn.is_visible(timeout=1000):
                    btn.click(timeout=5000)
            except Exception:
                pass
        try:
            self._page.keyboard.press("Escape")
        except Exception:
            pass
        detail_selector = self._selectors.get(
            "promotion_link_detail_container",
            self._selectors.get("promotion_link_detail", ""),
        )
        if detail_selector:
            try:
                self._page.locator(detail_selector).first.wait_for(
                    state="hidden", timeout=3000
                )
            except Exception:
                pass
            self._page.wait_for_timeout(500)


def _matches_target_price(detail_text: str, row_text: str, target: float) -> bool:
    return _classify_price(detail_text, row_text) == target


def _classify_price(detail_text: str, row_text: str) -> float | None:
    """从详情文本和行文本中识别 IAP 档位价格。

    优先匹配带"元"单位或明确价格标签的数值，避免纯数字匹配误伤
    （如"第9集"、"9.9万字"等）。按从高到低顺序匹配，避免 2.9 档
    详情中出现"原价9.9"时被错误识别为 9.9 档。
    """
    text = f"{detail_text} {row_text}"
    # 优先匹配带明确 IAP 档位价格标签：用户支付金额、首充金额
    # "单集价格"是每集单价，不是 IAP 档位价，不应参与分类
    labeled_patterns = [
        r"(?:用户支付金额|支付金额|首充金额)\s*[:：]?\s*(\d+(?:\.\d+)?)",
        r"首充\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元",
        r"(\d+(?:\.\d+)?)\s*元\s*(?:/部|起)(?!集)",
    ]
    labeled_values = []
    for pattern in labeled_patterns:
        for match in re.finditer(pattern, text):
            labeled_values.append(float(match.group(1)))
    if labeled_values:
        value = max(labeled_values)  # 取最大的支付金额作为档位判定依据
        nearest = min((2.9, 9.9), key=lambda target: abs(target - value))
        if abs(nearest - value) <= 2.0:
            return nearest

    # 回退：匹配独立的价格数字（必须前后不是数字，且带"元"或在价格上下文中）
    # 注意：9\.9 必须转义点号，避免 9x9 等误匹配
    for target in (9.9, 2.9):
        escaped = re.escape(str(target))
        if re.search(rf"(?<!\d){escaped}\s*元(?!\d)", text):
            return target
        if re.search(rf"(?:首充|用户支付金额|支付金额)\s*[:：]?\s*{escaped}(?!\d)", text):
            return target

    # 更宽泛的回退：匹配任意"X元"格式的价格（排除"X元/集"单价）
    # 适用场景：详情文本含"10.3元"但没有明确标签前缀
    price_matches = re.findall(
        r"(?<!\d)(\d+(?:\.\d+)?)\s*元(?!/集|\d)", text
    )
    iap_values = [float(m) for m in price_matches if 2.0 <= float(m) <= 50.0]
    if iap_values:
        value = max(iap_values)
        nearest = min((2.9, 9.9), key=lambda t: abs(t - value))
        if abs(nearest - value) <= 3.0:
            return nearest

    # 回退：从配置名称前缀提取价格（如"9.9-番茄-剧名"、"2.9-番茄-剧名"）
    name_price_match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(?:番茄|巨量|抖音)", row_text)
    if name_price_match:
        value = float(name_price_match.group(1))
        nearest = min((2.9, 9.9), key=lambda t: abs(t - value))
        if abs(nearest - value) <= 2.0:
            return nearest

    return None
