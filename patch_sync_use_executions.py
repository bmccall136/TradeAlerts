import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

has_exec = re.search(r'(?m)^def\s+recent_executions_as_trades\s*\(', src) is not None
has_today = re.search(r'(?m)^def\s+get_today_trades_and_realized\s*\(', src) is not None

m = re.search(r'(?ms)^def\s+sync_realized_trades_from_etrade\s*\(.*?\)\s*:\s*\n(.*?)(?=^\S|\Z)', src)
if not m:
    raise SystemExit("ERROR: could not find def sync_realized_trades_from_etrade(...) block")

block = m.group(0)

# Replace the one line that assigns trades via get_* helper
# We don't care what it currently calls; we replace the assignment safely.
pat_line = re.compile(r'(?m)^\s*trades\s*,\s*_realized_sum\s*=\s*.*$', re.M)

if not pat_line.search(block):
    raise SystemExit("ERROR: could not find 'trades, _realized_sum = ...' line inside sync_realized_trades_from_etrade")

if has_exec:
    repl = "    trades = recent_executions_as_trades(days=days)\n    _realized_sum = None"
elif has_today:
    # Fallback: no days kwarg; just call it as-is
    repl = "    trades, _realized_sum = get_today_trades_and_realized()"
else:
    raise SystemExit("ERROR: neither recent_executions_as_trades nor get_today_trades_and_realized exists")

block2 = pat_line.sub(repl, block, count=1)

src2 = src.replace(block, block2)
if src2 == src:
    raise SystemExit("ERROR: patch made no changes (unexpected)")

p.write_text(src2, encoding="utf-8")
print("OK: sync_realized_trades_from_etrade now uses executions (or safe fallback)")
