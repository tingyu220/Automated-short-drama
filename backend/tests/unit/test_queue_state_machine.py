"""测试 QueueStateMachine - 合法迁移与非法迁移."""
from __future__ import annotations

import pytest

from backend.domain.errors.domain_error import ConflictError
from backend.domain.queue.state_machine import QueueStateMachine


class TestQueueStateMachine:

    @pytest.mark.parametrize(
        "current, target",
        [
            ("WAITING_TIME", "QUEUED"),
            ("QUEUED", "CLAIMED"),
            ("QUEUED", "PAUSED"),
            ("QUEUED", "CANCELLED"),
            ("CLAIMED", "RUNNING"),
            ("CLAIMED", "COMPLETED"),
            ("CLAIMED", "PAUSED"),
            ("CLAIMED", "CANCELLED"),
            ("RUNNING", "COMPLETED"),
            ("RUNNING", "RETRY_WAIT"),
            ("RUNNING", "PAUSED"),
            ("RUNNING", "MANUAL_REVIEW"),
            ("RUNNING", "FAILED"),
            ("RUNNING", "CANCELLED"),
            ("FAILED", "QUEUED"),
            ("RETRY_WAIT", "QUEUED"),
            ("RETRY_WAIT", "MANUAL_REVIEW"),
            ("PAUSED", "QUEUED"),
            ("PAUSED", "RUNNING"),
            ("PAUSED", "CANCELLED"),
            ("MANUAL_REVIEW", "QUEUED"),
            ("MANUAL_REVIEW", "CANCELLED"),
        ],
    )
    def test_legal_transitions(self, current: str, target: str) -> None:
        """合法迁移 can_transition 返回 True，transition 返回 target。"""
        assert QueueStateMachine.can_transition(current, target) is True
        assert QueueStateMachine.transition(current, target) == target

    @pytest.mark.parametrize(
        "current, target",
        [
            ("WAITING_TIME", "CLAIMED"),
            ("WAITING_TIME", "COMPLETED"),
            ("QUEUED", "RUNNING"),
            ("QUEUED", "COMPLETED"),
            ("COMPLETED", "QUEUED"),
            ("COMPLETED", "RUNNING"),
            ("CANCELLED", "QUEUED"),
            ("CANCELLED", "RUNNING"),
            ("FAILED", "RUNNING"),
        ],
    )
    def test_illegal_transitions_raise_conflict_error(self, current: str, target: str) -> None:
        """非法迁移抛 ConflictError。"""
        assert QueueStateMachine.can_transition(current, target) is False
        with pytest.raises(ConflictError):
            QueueStateMachine.transition(current, target)

    @pytest.mark.parametrize("terminal", ["COMPLETED", "CANCELLED"])
    def test_terminal_states_cannot_transition(self, terminal: str) -> None:
        """终态不能迁往任何目标。"""
        assert QueueStateMachine.can_transition(terminal, "QUEUED") is False
        with pytest.raises(ConflictError):
            QueueStateMachine.transition(terminal, "QUEUED")
