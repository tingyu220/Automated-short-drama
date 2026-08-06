"""task_ledger.task_id 唯一约束，防止重复成功台账。"""

from alembic import op

revision = "20260807_0007"
down_revision = "20260806_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_task_ledger_task_id",
        "task_ledger",
        ["task_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_task_ledger_task_id", table_name="task_ledger")
