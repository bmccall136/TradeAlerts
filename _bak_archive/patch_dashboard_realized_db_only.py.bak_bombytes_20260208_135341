from pathlib import Path
from datetime import datetime

dash = Path(r"C:\TradeAlerts\dashboard.py")
src = dash.read_text(encoding="utf-8", errors="ignore")

bak = dash.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

lines = src.splitlines()

# 1) Ensure we have an alias import that cannot collide with any local function name
import_line = "from services.realized_service import realized_buckets_from_live_db as realized_buckets_from_live_db_db"

if import_line not in src:
    # insert after the last "from services" import if possible; otherwise after initial imports
    insert_at = None
    for i, line in enumerate(lines):
        if line.startswith("from services"):
            insert_at = i + 1
    if insert_at is None:
        # after first block of imports
        for i, line in enumerate(lines):
            if line.strip() == "" and i > 0:
                insert_at = i + 1
                break
    if insert_at is None:
        insert_at = 0
    lines.insert(insert_at, import_line)
    print("Inserted import:", import_line)
else:
    print("Import already present")

# 2) Replace *call sites* of realized_buckets_from_live_db( ... ) with realized_buckets_from_live_db_db(
#    but do NOT touch a function definition line.
changed = 0
for i, line in enumerate(lines):
    s = line.lstrip()
    if s.startswith("def realized_buckets_from_live_db"):
        continue
    if "realized_buckets_from_live_db(" in line:
        lines[i] = line.replace("realized_buckets_from_live_db(", "realized_buckets_from_live_db_db(")
        changed += 1

print("Rewrote call sites:", changed)

dash.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("OK patched dashboard to use DB-only realized buckets alias")
