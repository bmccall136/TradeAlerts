from pathlib import Path
from datetime import datetime

dash = Path(r"C:\TradeAlerts\dashboard.py")
src = dash.read_text(encoding="utf-8", errors="ignore")

bak = dash.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

import_line = "from services.realized_service import realized_buckets_from_live_db as realized_buckets_from_live_db_db"

lines = src.splitlines()

# 1) Remove ALL occurrences (so we don't leave the bad one inside parentheses)
new_lines = []
removed = 0
for line in lines:
    if line.strip() == import_line:
        removed += 1
        continue
    new_lines.append(line)

if removed == 0:
    print("WARN: import line not found to remove (continuing)")
else:
    print("Removed occurrences:", removed)

# 2) Find insertion point: after last top-level import
# top-level means starts at column 0 with 'import ' or 'from '
insert_at = None
for i, line in enumerate(new_lines):
    if line.startswith("import ") or line.startswith("from "):
        insert_at = i + 1

if insert_at is None:
    insert_at = 0

# Avoid inserting inside a module docstring if file starts with """..."""
# If the very top is a docstring, insertion point should be after it.
if insert_at == 0 and len(new_lines) >= 1 and new_lines[0].lstrip().startswith(('"""',"'''")):
    q = new_lines[0].lstrip()[:3]
    end = None
    for i in range(1, len(new_lines)):
        if q in new_lines[i]:
            end = i
            break
    if end is not None:
        insert_at = end + 1

# 3) Insert import line if not already present somewhere else
if any(l.strip() == import_line for l in new_lines):
    print("Import already present after cleanup; not inserting")
else:
    new_lines.insert(insert_at, import_line)
    print("Inserted import at line", insert_at + 1)

dash.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("OK fixed import placement")
