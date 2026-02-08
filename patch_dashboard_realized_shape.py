from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\dashboard.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Replace the block that currently does:
#   rb = realized_buckets_from_live_db_db(...)
#   pnl = rb.get("pnl") ...
# with a shape-tolerant version.

pat = re.compile(
    r"(?s)"
    r"# ---------- 7\) REALIZED P&L.*?\n"
    r"realized_obj\s*=\s*\{.*?\}\n",
)

replacement = r'''# ---------- 7) REALIZED P&L (live.db realized_trades) ----------
# NOTE: services.realized_service.realized_buckets_from_live_db() returns:
#   {day:{pnl,pct}, week:{pnl,pct}, last_week:{...}, month:{pnl,pct}, all:{pnl,pct}}
# Older code expected a wrapper like {"pnl": {"today":..,"week":..,"month":..}}.
# We normalize BOTH shapes here.

try:
    rb = realized_buckets_from_live_db_db(str(LIVE_DB)) or {}

    # Shape A (preferred / current): {"day": {"pnl":..}, "week":..., "month":...}
    if isinstance(rb, dict) and "day" in rb and isinstance(rb.get("day"), dict):
        day_pnl   = float((rb.get("day") or {}).get("pnl") or 0.0)
        week_pnl  = float((rb.get("week") or {}).get("pnl") or 0.0)
        month_pnl = float((rb.get("month") or {}).get("pnl") or 0.0)

    # Shape B (older): {"pnl": {"today":..,"week":..,"month":..}}
    else:
        pnl = (rb.get("pnl") or {}) if isinstance(rb, dict) else {}
        day_pnl   = float(pnl.get("today", 0.0) or 0.0)
        week_pnl  = float(pnl.get("week", 0.0) or 0.0)
        month_pnl = float(pnl.get("month", 0.0) or 0.0)

except Exception as exc:
    LOG.warning("realized pnl: live.db failed (using zeros): %s", exc)
    day_pnl = week_pnl = month_pnl = 0.0

# Percent calc: you currently compute denom earlier before 'about' is populated,
# so pct will be 0.0 anyway. Keep it simple/stable here.
realized_obj = {
    "day":   {"pnl": round(day_pnl, 2),   "pct": 0.0},
    "week":  {"pnl": round(week_pnl, 2),  "pct": 0.0},
    "month": {"pnl": round(month_pnl, 2), "pct": 0.0},
}
'''

src2, n = pat.subn(replacement, src, count=1)
if n != 1:
    raise SystemExit(f"ERROR: expected to replace 1 realized block, replaced {n}")

p.write_text(src2, encoding="utf-8")
print("OK: patched /live/status realized block to accept both shapes")
