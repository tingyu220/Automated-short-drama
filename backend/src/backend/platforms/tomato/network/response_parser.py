"""番茄平台网络响应解析器。

Phase 5: 将 Playwright 捕获的业务接口 JSON 响应解析为标准化的
推广链接候选数据。

设计原则：
- 启发式匹配常见字段命名（snake_case / camelCase）
- 不确定的字段留空，不猜
- 保留完整 raw_data 供后续核对
- 等真实 API 样本确认后，替换为精确映射
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 字段名别名映射：用于启发式解析
# ---------------------------------------------------------------------------

_PROMOTION_ID_KEYS = (
    "promotion_id", "promotionId", "id", "link_id", "linkId",
    "promo_id", "promoId",
)
_DRAMA_ID_KEYS = (
    "drama_id", "dramaId", "playlet_id", "playletId",
    "novel_id", "novelId", "item_id", "itemId",
    "book_id", "bookId",
)
_DRAMA_NAME_KEYS = (
    "drama_name", "dramaName", "playlet_name", "playletName",
    "novel_name", "novelName", "name", "title",
    "drama_title", "dramaTitle", "book_name", "bookName",
)
_EPISODE_KEYS = (
    "episode", "episodes", "episode_num", "episodeNum",
    "episode_count", "episodeCount", "ep",
)
_TEMPLATE_ID_KEYS = (
    "template_id", "templateId", "tpl_id", "tplId",
    "temp_id", "tempId",
)
_TEMPLATE_NAME_KEYS = (
    "template_name", "templateName", "tpl_name", "tplName",
    "temp_name", "tempName", "template_title", "templateTitle",
)
_PRICE_KEYS = (
    "price", "amount", "price_amount", "priceAmount",
    "pay_amount", "payAmount", "total_price", "totalPrice",
)
_URL_KEYS = (
    "promotion_url", "promotionUrl", "share_url", "shareUrl",
    "link_url", "linkUrl", "url", "short_url", "shortUrl",
    "promo_url", "promoUrl",
)
_TYPE_KEYS = (
    "type", "link_type", "linkType", "promotion_type", "promotionType",
    "category", "kind",
)

_IAA_TYPE_VALUES = {"free", "iaa", "advert", "ad", "广告", "免费"}
_PAID_TYPE_VALUES = {"paid", "iap", "付费", "充值", "解锁"}


@dataclass
class ParsedPromotion:
    """从网络响应解析出的标准化推广链接候选。"""

    external_drama_id: str | None = None
    promotion_id: str | None = None
    drama_name: str = ""
    link_type: str = "UNKNOWN"  # IAA / 2.9 / 9.9 / UNKNOWN
    episode: int | None = None
    template_id: str | None = None
    template_name: str | None = None
    price: float | None = None
    promotion_url: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    """安全转换为 float，失败返回 None。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    """安全转换为 int，失败返回 None。"""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _pick(data: dict, keys: tuple[str, ...]) -> Any:
    """按优先级从 dict 中取第一个存在的值。"""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _extract_list_items(response: Any) -> list[dict]:
    """从各种格式的列表响应中提取原始 item 列表。

    支持：
    - { data: { list: [...] } }
    - { data: { items: [...] } }
    - { data: [...] }
    - { list: [...] }
    - [...]
    """
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]

    if not isinstance(response, dict):
        return []

    data = response.get("data")

    # { data: { list: [...] } } 或 { data: { items: [...] } }
    if isinstance(data, dict):
        for key in ("list", "items", "records", "rows", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        return []

    # { data: [...] }
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    # 顶层有 list/items
    for key in ("list", "items", "records", "rows", "results"):
        val = response.get(key)
        if isinstance(val, list):
            return [item for item in val if isinstance(item, dict)]

    return []


def _classify_link_type(item: dict) -> str:
    """根据推广项字段判断链接类型：IAA / 2.9 / 9.9 / UNKNOWN。

    优先级：
    1. 明确的 type 字段（FREE/IA A → IAA, PAID/IAP → 付费）
    2. 价格字段 → 匹配 2.9 / 9.9 档位
    3. 模板名包含价格 → 推断档位
    4. 有集数字段且无价格 → IAA
    5. 都不确定 → UNKNOWN
    """
    type_val = str(_pick(item, _TYPE_KEYS) or "").strip().upper()
    price = _safe_float(_pick(item, _PRICE_KEYS))
    template_name = str(_pick(item, _TEMPLATE_NAME_KEYS) or "")
    episode = _safe_int(_pick(item, _EPISODE_KEYS))

    # 明确 IAA 类型
    if any(v in type_val.lower() for v in _IAA_TYPE_VALUES) and episode is not None:
        return "IAA"

    # 有价格 → 按价格档位分类
    if price is not None and price > 0:
        if 2.0 <= price <= 5.0:
            return "2.9"
        if 7.0 <= price <= 15.0:
            return "9.9"
        return f"PRICE_{price}"

    # 从模板名推断价格
    if template_name:
        tpl_lower = template_name.lower()
        if "2.9" in tpl_lower or "2块9" in tpl_lower or "2.9元" in tpl_lower:
            return "2.9"
        if "9.9" in tpl_lower or "9块9" in tpl_lower or "9.9元" in tpl_lower:
            return "9.9"

    # 有集数且是免费类型 → IAA
    if episode is not None and episode > 0:
        if any(v in type_val.lower() for v in _IAA_TYPE_VALUES) or not type_val:
            return "IAA"

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------


class TomatoResponseParser:
    """番茄平台网络响应解析器。

    当前使用启发式字段匹配，等真实 API 样本确认后替换为精确映射。
    解析失败时返回空列表 / None，不抛异常。
    """

    def parse_promotion_list(self, response: Any) -> list[ParsedPromotion]:
        """解析推广列表响应。"""
        items = _extract_list_items(response)
        results: list[ParsedPromotion] = []
        for item in items:
            parsed = self._parse_item(item)
            if parsed is not None:
                results.append(parsed)
        return results

    def parse_promotion_detail(self, response: Any) -> ParsedPromotion | None:
        """解析推广详情响应。"""
        if not isinstance(response, dict):
            return None

        data = response.get("data")
        if isinstance(data, dict):
            return self._parse_item(data)

        # 响应本身就是详情对象
        if response.get("id") or response.get("promotion_id"):
            return self._parse_item(response)

        return None

    def _parse_item(self, item: dict) -> ParsedPromotion | None:
        """将单个推广 item 解析为 ParsedPromotion。"""
        if not isinstance(item, dict):
            return None

        promotion_id = str(_pick(item, _PROMOTION_ID_KEYS) or "")
        drama_id = str(_pick(item, _DRAMA_ID_KEYS) or "") if _pick(item, _DRAMA_ID_KEYS) else None
        drama_name = str(_pick(item, _DRAMA_NAME_KEYS) or "")
        episode = _safe_int(_pick(item, _EPISODE_KEYS))
        template_id = str(_pick(item, _TEMPLATE_ID_KEYS) or "") if _pick(item, _TEMPLATE_ID_KEYS) else None
        template_name = str(_pick(item, _TEMPLATE_NAME_KEYS) or "") if _pick(item, _TEMPLATE_NAME_KEYS) else None
        price = _safe_float(_pick(item, _PRICE_KEYS))
        url = str(_pick(item, _URL_KEYS) or "")
        link_type = _classify_link_type(item)

        # 至少要有 promotion_id 或 url 才算有效
        if not promotion_id and not url:
            return None

        return ParsedPromotion(
            external_drama_id=drama_id,
            promotion_id=promotion_id or None,
            drama_name=drama_name,
            link_type=link_type,
            episode=episode,
            template_id=template_id,
            template_name=template_name,
            price=price,
            promotion_url=url,
            raw_data=dict(item),
        )
