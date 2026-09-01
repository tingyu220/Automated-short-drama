import sqlite3
conn = sqlite3.connect("data/database/app.db")
conn.execute(
    "UPDATE drama_task SET status='READY', link_status='NOT_STARTED', "
    "current_stage='WAITING_AVAILABLE_TIME', link_set_json='{}', "
    "promotion_configs_json='{}' "
    "WHERE drama_name LIKE '%微光%'"
)
conn.execute(
    "UPDATE queue_item SET state='QUEUED', claimed_by=NULL, lease_until=NULL "
    "WHERE task_id=(SELECT id FROM drama_task WHERE drama_name LIKE '%微光%')"
)
conn.commit()
print("Reset done")
conn.close()
