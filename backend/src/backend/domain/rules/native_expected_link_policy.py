"""Native 链接预期策略：判断各档位应该 EXPECTED 还是 EXPECTED_ABSENT。

规则：
- IAA 永远 EXPECTED
- 2.9 / 9.9 根据 TemplatePriceRule 判断
  - 存在对应价格区间的规则 → EXPECTED
  - 不存在 → EXPECTED_ABSENT
"""
from __future__ import annotations

from backend.domain.rules.template_price_rule import TemplatePriceRule


class LinkExpectation:
    """档位预期状态。"""

    EXPECTED = "EXPECTED"
    EXPECTED_ABSENT = "EXPECTED_ABSENT"


class ExpectedLinkPolicy:
    """判断 Native 链接各档位的预期状态。"""

    IAA_TYPE = "IAA"

    def __init__(self, price_rules: list[TemplatePriceRule]) -> None:
        self._rule_keys = {r.key for r in price_rules}
        self._price_rules = list(price_rules)

    def get_expectation(self, link_type: str) -> str:
        """返回档位的预期状态。"""
        if link_type == self.IAA_TYPE:
            return LinkExpectation.EXPECTED

        normalized_key = f"iap_{link_type.replace('.', '_')}"
        if normalized_key in self._rule_keys:
            return LinkExpectation.EXPECTED

        for rule in self._price_rules:
            normalized = rule.key.replace("iap_", "").replace("_", ".")
            if normalized == link_type:
                return LinkExpectation.EXPECTED

        return LinkExpectation.EXPECTED_ABSENT

    def expected_types(self) -> list[str]:
        """返回所有 EXPECTED 的档位列表。"""
        result = [self.IAA_TYPE]
        for rule in self._price_rules:
            normalized = rule.key.replace("iap_", "").replace("_", ".")
            if normalized != self.IAA_TYPE and normalized not in result:
                result.append(normalized)
        return result

    def is_satisfied(self, statuses: dict[str, str]) -> bool:
        """判断实际状态是否满足预期。

        Args:
            statuses: {link_type: status} 状态字典
                      status ∈ FOUND / NOT_FOUND / AMBIGUOUS / ACQUISITION_FAILED 等

        Returns:
            True 当且仅当：
            - 所有 EXPECTED 档位 = FOUND
            - 所有 EXPECTED_ABSENT 档位 ≠ FOUND
        """
        all_types = {self.IAA_TYPE, "2.9", "9.9"}
        for link_type in all_types:
            expectation = self.get_expectation(link_type)
            actual = statuses.get(link_type, "NOT_FOUND")

            if expectation == LinkExpectation.EXPECTED:
                if actual != "FOUND":
                    return False
            elif expectation == LinkExpectation.EXPECTED_ABSENT:
                if actual == "FOUND":
                    return False

        return True
