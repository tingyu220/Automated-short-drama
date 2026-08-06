"""ORM 模型集合，确保 Alembic autogenerate 可见."""
from backend.infrastructure.database.models.execution import (  # noqa: F401
    ExecutionArtifactRecord,
    ExecutionEventRecord,
)
from backend.infrastructure.database.models.worker import WorkerLeaseRecord  # noqa: F401
from backend.infrastructure.database.models.task import (  # noqa: F401
    DramaTaskRecord,
    QueueItemRecord,
    WorkflowRunRecord,
    StepRunRecord,
    TaskLedgerRecord,
)
