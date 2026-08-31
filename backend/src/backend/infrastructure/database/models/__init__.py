"""ORM 模型集合，确保 Alembic autogenerate 可见."""
from backend.infrastructure.database.models.account import AccountUsageRecord  # noqa: F401
from backend.infrastructure.database.models.drama_import import DramaImportRunRecord  # noqa: F401
from backend.infrastructure.database.models.execution import (  # noqa: F401
    ExecutionArtifactRecord,
    ExecutionEventRecord,
)
from backend.infrastructure.database.models.rule import (  # noqa: F401
    ConfigChangeLogRecord,
    ConfigSnapshotRecord,
    DouyinAccountRecord,
    MaterialRuleRangeRecord,
    PlatformResourceConfigRecord,
    PresetMappingRecord,
    RuleParameterRecord,
    RuleSetRecord,
    RuleVersionRecord,
    TemplatePriceRuleRecord,
)
from backend.infrastructure.database.models.worker import WorkerLeaseRecord  # noqa: F401
from backend.infrastructure.database.models.runtime_environment import (  # noqa: F401
    RuntimeEnvironmentRecord,
)
from backend.infrastructure.database.models.task import (  # noqa: F401
    DramaTaskRecord,
    QueueItemRecord,
    WorkflowRunRecord,
    StepRunRecord,
    TaskLedgerRecord,
)
