import sqlite3
conn = sqlite3.connect("data/database/app.db")
r = conn.execute("SELECT state, claimed_by, lease_until FROM queue_item WHERE task_id=(SELECT id FROM drama_task WHERE drama_name LIKE '%微光%')").fetchone()
print(f"state={r[0]}, claimed_by={r[1]}, lease={r[2]}")
conn.close()
