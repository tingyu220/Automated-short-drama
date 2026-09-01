import sys, time
sys.path.insert(0, 'd:/work/short-drama-delivery-workbuddy/backend/src')
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.database.repositories.task_repository import SqlAlchemyTaskRepository
from backend.infrastructure.database.repositories.queue_repository import SqlAlchemyQueueRepository

task_id = 'be70347e-a38f-448a-b2a3-56b732ad2d6d'
for i in range(36):
    time.sleep(5)
    session = SessionLocal()
    task = SqlAlchemyTaskRepository(session).get(task_id)
    items = SqlAlchemyQueueRepository(session).list_by_task(task_id)
    item = items[0] if items else None
    link_keys = list(task.link_set.keys()) if task.link_set else []
    q_state = item.state if item else "?"
    q_failure = item.failure_code if item else None
    print(f"[{i*5}s] status={task.status} link_status={task.link_status} stage={task.current_stage} links={link_keys} queue={q_state} failure={q_failure}")
    session.close()
    if task.status in ("LINK_READY", "MANUAL_REVIEW", "COMPLETED", "DRY_RUN", "FAILED"):
        if task.link_set:
            print(f"link_set keys: {list(task.link_set.keys())}")
            for k, v in task.link_set.items():
                v_preview = v[:80] + "..." if len(v) > 80 else v
                print(f"  {k}: {v_preview}")
        break
