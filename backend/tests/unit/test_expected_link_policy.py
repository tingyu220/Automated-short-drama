"""验证 ExpectedLinkPolicy 正确判断各档位预期状态。"""
from __future__ import annotations

from backend.domain.rules.native_expected_link_policy import (
    ExpectedLinkPolicy,
    LinkExpectation,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule


def _rules(*targets):
    return [
        TemplatePriceRule(target_price=t, min_price=t - 1.0, max_price=t + 1.0, key=f"iap_{str(t).replace('.', '_')}")
        for t in targets
    ]


class TestExpectedLinkPolicy:
    """Phase 3: ExpectedLinkPolicy 判断各档位 EXPECTED / EXPECTED_ABSENT。"""

    def test_iaa_always_expected(self):
        """IAA 永远 EXPECTED。"""
        policy = ExpectedLinkPolicy(_rules())
        assert policy.get_expectation("IAA") == LinkExpectation.EXPECTED

    def test_2_9_expected_when_rule_exists(self):
        """存在 2.9 价格规则 → 2.9 EXPECTED。"""
        policy = ExpectedLinkPolicy(_rules(2.9, 9.9))
        assert policy.get_expectation("2.9") == LinkExpectation.EXPECTED
        assert policy.get_expectation("9.9") == LinkExpectation.EXPECTED

    def test_2_9_absent_when_no_rule(self):
        """无 2.9 价格规则 → 2.9 EXPECTED_ABSENT。"""
        policy = ExpectedLinkPolicy(_rules(9.9))
        assert policy.get_expectation("2.9") == LinkExpectation.EXPECTED_ABSENT
        assert policy.get_expectation("9.9") == LinkExpectation.EXPECTED

    def test_all_absent_except_iaa(self):
        """无任何 IAP 规则 → 只有 IAA EXPECTED。"""
        policy = ExpectedLinkPolicy(_rules())
        assert policy.get_expectation("IAA") == LinkExpectation.EXPECTED
        assert policy.get_expectation("2.9") == LinkExpectation.EXPECTED_ABSENT
        assert policy.get_expectation("9.9") == LinkExpectation.EXPECTED_ABSENT

    def test_expected_types_returns_all_expected(self):
        """expected_types 返回所有 EXPECTED 的档位列表。"""
        policy = ExpectedLinkPolicy(_rules(2.9))
        expected = policy.expected_types()
        assert "IAA" in expected
        assert "2.9" in expected
        assert "9.9" not in expected

    def test_is_satisfied_all_expected_found(self):
        """所有 EXPECTED 档位都有 FOUND → satisfied。"""
        policy = ExpectedLinkPolicy(_rules(2.9, 9.9))
        statuses = {"IAA": "FOUND", "2.9": "FOUND", "9.9": "FOUND"}
        assert policy.is_satisfied(statuses) is True

    def test_not_satisfied_when_expected_missing(self):
        """EXPECTED 档位有 NOT_FOUND → not satisfied。"""
        policy = ExpectedLinkPolicy(_rules(2.9, 9.9))
        statuses = {"IAA": "FOUND", "2.9": "FOUND", "9.9": "NOT_FOUND"}
        assert policy.is_satisfied(statuses) is False

    def test_satisfied_when_expected_absent_and_not_found(self):
        """EXPECTED_ABSENT 档位 NOT_FOUND → satisfied。"""
        policy = ExpectedLinkPolicy(_rules(2.9))
        statuses = {"IAA": "FOUND", "2.9": "FOUND", "9.9": "NOT_FOUND"}
        assert policy.is_satisfied(statuses) is True

    def test_not_satisfied_when_expected_absent_but_found(self):
        """EXPECTED_ABSENT 档位 FOUND → not satisfied（需要人工确认）。"""
        policy = ExpectedLinkPolicy(_rules(2.9))
        statuses = {"IAA": "FOUND", "2.9": "FOUND", "9.9": "FOUND"}
        assert policy.is_satisfied(statuses) is False
