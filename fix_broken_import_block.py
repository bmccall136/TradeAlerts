from pathlib import Path
from datetime import datetime

dash = Path(r"C:\TradeAlerts\dashboard.py")
src = dash.read_text(encoding="utf-8", errors="ignore")

bak = dash.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

bad_line = "from services.realized_service import realized_buckets_from_live_db as realized_buckets_from_live_db_db"

lines = src.splitlines()

# Find the exact broken pattern:
# from services.etrade_service import (
# <bad_line>
#     REALIZED_START_DATE,
# )
fixed = 0
out = []
i = 0
while i < len(lines):
    if (lines[i].strip() == "from services.etrade_service import (" and
        i + 3 < len(lines) and
        lines[i+1].strip() == bad_line and
        "REALIZED_START_DATE" in lines[i+2] and
        lines[i+3].strip() == ")"):

        # Keep the etrade_service import block valid (drop the bad line)
        out.append(lines[i])        # from services.etrade_service import (
        out.append(lines[i+2])      #     REALIZED_START_DATE,
        out.append(lines[i+3])      # )
        out.append("")              # blank line
        out.append(bad_line)        # add alias import as its own statement
        fixed += 1
        i += 4
        continue

    out.append(lines[i])
    i += 1

if fixed != 1:
    raise SystemExit(f"ERROR: expected to fix exactly 1 broken import block, fixed {fixed}")

dash.write_text("\n".join(out) + "\n", encoding="utf-8")
print("OK fixed broken import block and moved realized_service import out of parentheses")
