"""番茄剧目列表唯一选择与详情二次复核。"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.domain.common.timezones import SHANGHAI_TZ
from backend.domain.errors.domain_error import DramaMismatchError
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.domain.rules.drama_match import (
    DramaCandidate,
    match_unique_drama,
    normalize_drama_name,
    shanghai_minute,
)

_TIME_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y-%m-%d %H:%M ",
    "%Y/%m/%d %H:%M ",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
)
logger = logging.getLogger(__name__)


class DramaSelectionPage:
    """只负责从页面读取候选、打开唯一候选并复核详情。"""

    def __init__(
        self,
        page: Any,
        selectors: dict[str, str],
        artifact_dir: Path | None = None,
    ) -> None:
        self._page = page
        self._selectors = selectors
        self._artifact_dir = artifact_dir
        self._search_diag: dict[str, Any] = {}

    def select_and_verify(
        self,
        drama_name: str,
        available_time: datetime,
        confirmed_match: ConfirmedDramaMatch | None = None,
    ) -> DramaCandidate:
        """执行列表唯一匹配与详情复核，任一不确定结果均抛错。"""
        self._search(drama_name)
        try:
            candidates = self._read_candidates(available_time)
            selected = (
                _match_confirmed(drama_name, confirmed_match, candidates)
                if confirmed_match is not None
                else match_unique_drama(drama_name, available_time, candidates)
            )
        except DramaMismatchError as exc:
            raise self._with_evidence(exc, "LIST") from exc

        detail_selector = (
            f'{self._selectors["detail_link"]}'
            f'[href="{_escape_css_attribute(selected.locator_key)}"]'
        )
        self._page.locator(detail_selector).click(timeout=15000)
        try:
            detail = self._read_detail(drama_name, selected.locator_key)
            if confirmed_match is not None:
                _match_confirmed(drama_name, confirmed_match, [detail])
            else:
                match_unique_drama(drama_name, available_time, [detail])
        except DramaMismatchError as exc:
            raise self._with_evidence(exc, "DETAIL") from exc
        return selected

    def _search(self, drama_name: str) -> None:
        self._page.goto(
            self._selectors["login_url"],
            wait_until="domcontentloaded",
            timeout=60000,
        )
        diag: dict[str, Any] = {"target_name": drama_name}
        # 等待搜索框出现并记录搜索前状态
        search_input = self._page.locator(self._selectors["search_input"])
        diag["search_selector"] = self._selectors["search_input"]
        try:
            search_input.wait_for(state="visible", timeout=15000)
            diag["search_input_visible"] = True
        except Exception as exc:
            diag["search_input_visible"] = False
            diag["search_input_error"] = str(exc)
            self._search_diag = diag
            raise
        # 记录搜索前的首行剧名
        row_selector = self._selectors["result_row"]
        name_selector = self._selectors["result_drama_name"]
        try:
            first_name_before = (
                self._page.locator(name_selector).first.text_content()
                or ""
            ).strip()
            diag["first_name_before_search"] = first_name_before
            diag["row_count_before"] = self._page.locator(row_selector).count()
        except Exception:
            pass
        # 使用 type 方法逐字输入（比 fill 更能触发组件的 input 事件）
        search_input.click()
        self._page.wait_for_timeout(100)
        search_input.fill("")
        self._page.wait_for_timeout(100)
        search_input.type(drama_name, delay=50)
        # 验证输入是否生效
        try:
            filled_value = search_input.input_value()
            diag["filled_value"] = filled_value
            diag["fill_succeeded"] = filled_value == drama_name
        except Exception as exc:
            diag["fill_check_error"] = str(exc)
        # 先按回车搜索，失败再点按钮
        search_triggered = False
        try:
            search_input.press("Enter")
            diag["enter_pressed"] = True
            search_triggered = True
        except Exception as exc:
            diag["enter_error"] = str(exc)
        if not search_triggered:
            try:
                self._page.locator(self._selectors["search_button"]).click()
                diag["search_button_clicked"] = True
            except Exception as exc:
                diag["search_button_error"] = str(exc)
                self._search_diag = diag
                raise
        # 等待搜索结果：首行剧名变化或出现无结果提示
        for i in range(15):
            try:
                first_name_after = (
                    self._page.locator(name_selector).first.text_content()
                    or ""
                ).strip()
                diag[f"first_name_after_{i}"] = first_name_after
                if drama_name in first_name_after or first_name_after in drama_name:
                    diag["search_succeeded"] = True
                    diag["search_attempts"] = i + 1
                    break
            except Exception:
                pass
            self._page.wait_for_timeout(500)
        else:
            diag["search_succeeded"] = False
            diag["search_attempts"] = 15
        self._search_diag = diag

    def _read_candidates(self, fallback_time: datetime) -> list[DramaCandidate]:
        rows_locator = self._page.locator(self._selectors["result_row"])
        for attempt in range(3):
            rows = self._read_candidate_rows(rows_locator)
            # 番茄搜索提交后会短暂保留上一页的占位行（发布时间为 "-"）。
            # 只对该已知异步状态重读，其他数据异常仍按原规则立即阻断。
            if not any(len(row) > 1 and str(row[1]).strip() == "-" for row in rows):
                return self._to_candidates(rows, fallback_time=fallback_time)
            if attempt < 2:
                self._page.wait_for_timeout(300)
        # 番茄列表页会在部分剧目上长期显示“-”；此时只能把列表时间
        # 当作未知，借助唯一剧名进入详情页，再以详情时间作最终核对。
        return self._to_candidates(rows, fallback_time=fallback_time)

    def _read_candidate_rows(self, rows_locator: Any) -> list[list[Any]]:
        return rows_locator.evaluate_all(
            """
            (items, selectors) => items.map((item, index) => {
              const name = item.querySelector(selectors.drama_name);
              const time = item.querySelector(selectors.available_time);
              const detail = item.querySelector(selectors.detail_link);
              return [
                name ? name.textContent.trim() : "",
                time ? time.textContent.trim() : "",
                detail ? detail.getAttribute("href") || "" : "",
                index
              ];
            })
            """,
            {
                "drama_name": self._selectors["result_drama_name"],
                "available_time": self._selectors["result_available_time"],
                "detail_link": self._selectors["detail_link"],
            },
        )

    def _to_candidates(
        self, rows: list[list[Any]], *, fallback_time: datetime | None = None
    ) -> list[DramaCandidate]:
        candidates: list[DramaCandidate] = []
        for page_order, row in enumerate(rows):
            if len(row) < 3 or not row[0] or not row[1] or not row[2]:
                continue
            raw_time = str(row[1]).strip()
            available_time = (
                fallback_time
                if raw_time == "-" and fallback_time is not None
                else _parse_time(raw_time)
            )
            candidates.append(
                DramaCandidate(
                    drama_name=str(row[0]),
                    available_time=available_time,
                    locator_key=str(row[2]),
                    raw_time=raw_time,
                    page_order=int(row[3]) if len(row) > 3 else page_order,
                )
            )
        return candidates

    def _read_detail(
        self, expected_name: str, locator_key: str
    ) -> DramaCandidate:
        last_exc = None
        for attempt in range(3):
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            self._page.wait_for_timeout(1000 * (attempt + 1))
            try:
                raw_name = self._page.get_by_text(
                    expected_name, exact=True
                ).text_content(timeout=10000)
                raw_time = self._page.locator(
                    self._selectors["detail_available_time"]
                ).text_content(timeout=10000)
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    continue
                raise DramaMismatchError(
                    "番茄详情剧名或时间读取失败",
                    details={
                        "reason": "DETAIL_READ_FAILED",
                        "error_type": type(exc).__name__,
                        "attempts": attempt + 1,
                    },
                ) from exc
            if not raw_name or not raw_time:
                last_exc = DramaMismatchError(
                    "番茄详情缺少剧名或时间",
                    details={
                        "reason": "INVALID_DETAIL",
                        "raw_name": raw_name or "",
                        "raw_time": raw_time or "",
                    },
                )
                if attempt < 2:
                    continue
                raise last_exc
            return DramaCandidate(
                drama_name=raw_name.strip(),
                available_time=_parse_time(raw_time.strip()),
                locator_key=locator_key,
                raw_time=raw_time.strip(),
                page_order=0,
            )
        raise last_exc  # type: ignore[misc]

    def _with_evidence(
        self, error: DramaMismatchError, stage: str
    ) -> DramaMismatchError:
        details = {**error.details, "stage": stage}
        if self._search_diag:
            details["search_diag"] = self._search_diag
        screenshot_path = self._capture_screenshot(stage)
        if screenshot_path is not None:
            details["screenshot_path"] = str(screenshot_path)
        return DramaMismatchError(error.message, details=details)

    def _capture_screenshot(self, stage: str) -> Path | None:
        if self._artifact_dir is None:
            return None
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self._artifact_dir / (
            f"drama-mismatch-{stage.lower()}-{uuid4().hex}.png"
        )
        try:
            self._page.screenshot(path=str(path), full_page=True)
        except Exception:
            logger.warning("同名剧匹配失败截图保存失败", exc_info=True)
            return None
        return path


def _parse_time(raw: str) -> datetime:
    for pattern in _TIME_FORMATS:
        try:
            return datetime.strptime(raw.strip(), pattern).replace(
                tzinfo=SHANGHAI_TZ
            )
        except ValueError:
            continue
    raise DramaMismatchError(
        "番茄剧目时间格式无法解析",
        details={"reason": "INVALID_TIME_FORMAT", "raw_time": raw},
    )


def _match_confirmed(
    expected_name: str,
    confirmation: ConfirmedDramaMatch,
    candidates: list[DramaCandidate],
) -> DramaCandidate:
    """只复核人工确认的原候选，不允许按列表顺序替换候选。"""
    matches = [
        item for item in candidates if item.locator_key == confirmation.locator_key
    ]
    if (
        len(matches) != 1
        or normalize_drama_name(matches[0].drama_name)
        != normalize_drama_name(expected_name)
        or shanghai_minute(matches[0].available_time)
        != shanghai_minute(confirmation.available_minute)
    ):
        raise DramaMismatchError(
            "已确认候选已变化",
            details={"reason": "CONFIRMED_CANDIDATE_CHANGED"},
        )
    return matches[0]


def _escape_css_attribute(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
