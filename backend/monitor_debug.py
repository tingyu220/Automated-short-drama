import sys, time, os
sys.path.insert(0, 'd:/work/short-drama-delivery-workbuddy/backend/src')

task_id = 'be70347e-a38f-448a-b2a3-56b732ad2d6d'
log_dir = 'd:/work/short-drama-delivery-workbuddy/logs'

# Find the latest worker log
log_files = [f for f in os.listdir(log_dir) if f.startswith('worker-restart-') and f.endswith('.log')]
log_files.sort(reverse=True)
log_path = os.path.join(log_dir, log_files[0]) if log_files else None
print(f"Monitoring log: {log_path}")

# Track log size to detect new content
last_size = 0
if log_path and os.path.exists(log_path):
    last_size = os.path.getsize(log_path)

for i in range(60):
    time.sleep(5)
    # Check task state
    from backend.infrastructure.database.session import SessionLocal
    from backend.infrastructure.database.repositories.task_repository import SqlAlchemyTaskRepository
    session = SessionLocal()
    task = SqlAlchemyTaskRepository(session).get(task_id)
    link_keys = list(task.link_set.keys()) if task.link_set else []
    print(f"[{i*5}s] status={task.status} link_status={task.link_status} links={link_keys}")
    session.close()

    # Check for new log content
    if log_path and os.path.exists(log_path):
        curr_size = os.path.getsize(log_path)
        if curr_size > last_size:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(last_size)
                new_content = f.read()
            for line in new_content.splitlines():
                if 'DEBUG' in line or '旧庭' in line or '9.9' in line or '9,9' in line:
                    print(f"  LOG: {line}")
            last_size = curr_size

    if task.status in ("LINK_READY", "MANUAL_REVIEW", "COMPLETED", "FAILED"):
        if task.link_set:
            print(f"\nFinal link_set keys: {list(task.link_set.keys())}")
        break
