import sqlite3, json
conn = sqlite3.connect("data/database/app.db")
conn.row_factory = sqlite3.Row
r = conn.execute("SELECT link_set_json, promotion_configs_json FROM drama_task WHERE drama_name LIKE '%微光%'").fetchone()
d = dict(r)
print("=== link_set ===")
print(json.dumps(json.loads(d["link_set_json"]), ensure_ascii=False, indent=2))
print("\n=== promotion_configs ===")
print(json.dumps(json.loads(d["promotion_configs_json"]), ensure_ascii=False, indent=2))
conn.close()
