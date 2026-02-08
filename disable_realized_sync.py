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
    raise SystemExit("ERROR: could not find sync_realized_trades_from_etrade")

old_block = m.group(0)

new_block = r'''def sync_realized_trades_from_etrade(
    db_path: str,
    start_date: _dt.date | None = None,
) -> Dict[str, object]:
    """
    Disabled.

    Your E*TRADE executions feed currently returns pl=0.0 for SELL rows,
    so it cannot be used to compute realized P&L. We instead write realized
    P&L into live.db at SELL fill time (method #1).
    """
    today = _dt.date.today()
    return {"ok": False, "disabled": True, "reason": "executions pl is 0.0; use SELL fill-time DB writes", "end": today.isoformat()}
'''

src2 = src.replace(old_block, new_block)
if src2 == src:
    raise SystemExit("ERROR: replacement made no changes (unexpected)")

p.write_text(src2, encoding="utf-8")
print("OK: sync_realized_trades_from_etrade disabled (method #1 is authoritative)")
