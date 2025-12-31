from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\import_realized_from_etrade_csv.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Replace: net_gain = gain + deferred  -> net_gain = gain
src2, n = re.subn(
    r"(?m)^\s*net_gain\s*=\s*gain\s*\+\s*deferred\s*$",
    "                net_gain = gain  # NOTE: ignore Deferred Loss (wash-sale) for realized tile\n",
    src
)

if n != 1:
    raise SystemExit(f"ERROR: expected to replace 1 'net_gain = gain + deferred' line, replaced {n}")

p.write_text(src2, encoding="utf-8")
print("OK: importer now ignores Deferred Loss (tile should match 'Total Gain Realized')")
