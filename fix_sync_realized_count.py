from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

m = re.search(r'(?ms)^def\s+sync_realized_trades_from_etrade\s*\(.*?\)\s*:\s*\n(.*?)(?=^\S|\Z)', src)
if not m:
    raise SystemExit("ERROR: could not find def sync_realized_trades_from_etrade(...) block")

block = m.group(0)

# We will replace ANY of these patterns inside the function:
# trades = recent_executions_as_trades(...)
# trades, _realized_sum = ...
# with a single correct call using count (because signature is (count=50))
pat_any = re.compile(r'(?m)^\s*trades\s*=.*$|^\s*trades\s*,\s*_realized_sum\s*=.*$', re.M)

# Make sure we only replace the FIRST relevant assignment inside the function
lines = block.splitlines()
replaced = 0
out = []
for line in lines:
    if replaced == 0 and ("recent_executions_as_trades" in line or "trades," in line or line.lstrip().startswith("trades =")):
        # Insert the correct two lines and skip the old assignment line
        out.append("    trades = recent_executions_as_trades(count=500)")
        out.append("    _realized_sum = None")
        replaced = 1
        continue
    out.append(line)

if replaced != 1:
    raise SystemExit("ERROR: did not find a trades assignment to replace inside sync_realized_trades_from_etrade")

block2 = "\n".join(out) + "\n"

src2 = src.replace(block, block2)
if src2 == src:
    raise SystemExit("ERROR: patch made no changes (unexpected)")

p.write_text(src2, encoding="utf-8")
print("OK: sync_realized_trades_from_etrade now calls recent_executions_as_trades(count=500)")
