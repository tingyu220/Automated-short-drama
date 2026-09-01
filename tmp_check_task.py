import sys, json
sys.path.insert(0, 'd:/work/short-drama-delivery-workbuddy/backend/src')
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.database.repositories.task_repository import SqlAlchemyTaskRepository

session = SessionLocal()
task_repo = SqlAlchemyTaskRepository(session)
task = task_repo.get('be70347e-a38f-448a-b2a3-56b732ad2d6d')
if task:
    print(f"Status: {task.status}")
    print(f"Stage: {task.current_stage}")
    print(f"Link Status: {task.link_status}")
    if task.link_set:
        print(f"Link Set: {json.dumps(task.link_set, ensure_ascii=False, indent=2)}")
    else:
        print("Link Set: empty")
    if task.promotion_configs:
        print(f"Promotion Configs: {json.dumps(task.promotion_configs, ensure_ascii=False, indent=2)}")
    else:
        print("Promotion Configs: empty")
else:
    print("Task not found")
session.close()
