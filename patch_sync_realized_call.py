import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Decide which helper exists
has_recent = re.search(r'(?m)^def\s+get_recent_trades_and_realized\s*\(', src) is not None
has_today  = re.search(r'(?m)^def\s+get_today_trades_and_realized\s*\(', src) is not None

if has_recent:
    print("OK: get_recent_trades_and_realized already exists. No change needed.")
    raise SystemExit(0)

if not has_today:
    raise SystemExit("ERROR: neither get_recent_trades_and_realized nor get_today_trades_and_realized exists in etrade_service.py")

# Patch only inside sync_realized_trades_from_etrade: replace the missing call name
m = re.search(r'(?ms)^def\s+sync_realized_trades_from_etrade\s*\(.*?\)\s*:\s*\n(.*?)(?=^\S|\Z)', src)
if not m:
    raise SystemExit("ERROR: could not find def sync_realized_trades_from_etrade(...) block")

block = m.group(0)

if "get_recent_trades_and_realized" not in block:
    raise SystemExit("ERROR: sync_realized_trades_from_etrade block did not reference get_recent_trades_and_realized (unexpected)")

block2 = block.replace("get_recent_trades_and_realized", "get_today_trades_and_realized")

src2 = src.replace(block, block2)
if src2 == src:
    raise SystemExit("ERROR: patch made no changes (unexpected)")

p.write_text(src2, encoding="utf-8")
print("OK: sync_realized_trades_from_etrade now calls get_today_trades_and_realized()")
