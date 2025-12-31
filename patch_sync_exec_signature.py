import re
import inspect
from pathlib import Path
from datetime import datetime

# Load module to introspect signature
from services import etrade_service as et

sig = str(inspect.signature(et.recent_executions_as_trades))
print("recent_executions_as_trades signature =", sig)

# Decide how to call it
# We prefer to pass our 'days' variable if the function supports something compatible.
call = None
if "days" in sig:
    call = "recent_executions_as_trades(days=days)"
elif "lookback_days" in sig:
    call = "recent_executions_as_trades(lookback_days=days)"
elif "ndays" in sig:
    call = "recent_executions_as_trades(ndays=days)"
elif "n_days" in sig:
    call = "recent_executions_as_trades(n_days=days)"
elif "window" in sig:
    call = "recent_executions_as_trades(window=days)"
elif "count" in sig:
    # some implementations use count instead of days; keep it conservative:
    call = "recent_executions_as_trades(count=200)"
else:
    # no supported parameter names -> call with no args
    call = "recent_executions_as_trades()"

print("Will patch sync_realized_trades_from_etrade to call:", call)

p = Path(r\"C:\TradeAlerts\services\etrade_service.py\")
src = p.read_text(encoding=\"utf-8\", errors=\"ignore\")

bak = p.with_suffix(\".py.bak_\" + datetime.now().strftime(\"%Y%m%d_%H%M%S\"))
bak.write_text(src, encoding=\"utf-8\")
print(\"Backup ->\", bak)

m = re.search(r'(?ms)^def\\s+sync_realized_trades_from_etrade\\s*\\(.*?\\)\\s*:\\s*\\n(.*?)(?=^\\S|\\Z)', src)
if not m:
    raise SystemExit(\"ERROR: could not find def sync_realized_trades_from_etrade(...) block\")

block = m.group(0)

# Replace any existing line that assigns trades via recent_executions_as_trades(...)
pat = re.compile(r'(?m)^\\s*trades\\s*=\\s*recent_executions_as_trades\\(.*\\)\\s*$', re.M)

if not pat.search(block):
    # fallback: replace the older 2-tuple assignment line if present
    pat2 = re.compile(r'(?m)^\\s*trades\\s*,\\s*_realized_sum\\s*=\\s*.*$', re.M)
    if not pat2.search(block):
        raise SystemExit(\"ERROR: could not find a trades assignment line inside sync_realized_trades_from_etrade\")
    block2 = pat2.sub(f\"    trades = {call}\\n    _realized_sum = None\", block, count=1)
else:
    block2 = pat.sub(f\"    trades = {call}\", block, count=1)

src2 = src.replace(block, block2)
if src2 == src:
    raise SystemExit(\"ERROR: patch made no changes (unexpected)\")

p.write_text(src2, encoding=\"utf-8\")
print(\"OK: patched sync_realized_trades_from_etrade to match executions signature\")
