from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\dashboard.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Replace the *exact* old-shape block inside live_status()
pat = re.compile(
    r"(?ms)"
    r"^[ \t]*try:\n"
    r"^[ \t]*rb\s*=\s*realized_buckets_from_live_db_db\(str\(LIVE_DB\)\)\s*or\s*\{\}\s*\n"
    r"^[ \t]*pnl\s*=\s*\(rb\.get\(\"pnl\"\)\s*or\s*\{\}\)\s*\n"
    r"^[ \t]*day_pnl\s*=\s*float\(pnl\.get\(\"today\",\s*0\.0\)\s*or\s*0\.0\)\s*\n"
    r"^[ \t]*week_pnl\s*=\s*float\(pnl\.get\(\"week\",\s*0\.0\)\s*or\s*0\.0\)\s*\n"
    r"^[ \t]*month_pnl\s*=\s*float\(pnl\.get\(\"month\",\s*0\.0\)\s*or\s*0\.0\)\s*\n"
    r"^[ \t]*except\s+Exception\s+as\s+exc:\n"
    r"^[ \t]*LOG\.warning\(\"realized pnl: live\.db failed \(using zeros\): %s\",\s*exc\)\s*\n"
    r"^[ \t]*day_pnl\s*=\s*week_pnl\s*=\s*month_pnl\s*=\s*0\.0\s*\n"
)

m = pat.search(src)
if not m:
    raise SystemExit("ERROR: could not find the old realized block (pattern mismatch). Paste lines ~1568-1580 if this hits.")

indent = re.match(r"^[ \t]*", m.group(0)).group(0)

replacement = f"""{indent}try:
{indent}    rb = realized_buckets_from_live_db_db(str(LIVE_DB)) or {{}}

{indent}    # Shape A (current): {{'day':{{pnl,pct}}, 'week':..., 'month':...}}
{indent}    if isinstance(rb, dict) and isinstance(rb.get("day"), dict):
{indent}        day_pnl   = float((rb.get("day") or {{}}).get("pnl") or 0.0)
{indent}        week_pnl  = float((rb.get("week") or {{}}).get("pnl") or 0.0)
{indent}        month_pnl = float((rb.get("month") or {{}}).get("pnl") or 0.0)
{indent}    else:
{indent}        # Shape B (older): {{'pnl': {{'today':..,'week':..,'month':..}}}}
{indent}        pnl = (rb.get("pnl") or {{}}) if isinstance(rb, dict) else {{}}
{indent}        day_pnl   = float(pnl.get("today", 0.0) or 0.0)
{indent}        week_pnl  = float(pnl.get("week", 0.0) or 0.0)
{indent}        month_pnl = float(pnl.get("month", 0.0) or 0.0)

{indent}except Exception as exc:
{indent}    LOG.warning("realized pnl: live.db failed (using zeros): %s", exc)
{indent}    day_pnl = week_pnl = month_pnl = 0.0
"""

src2 = src[:m.start()] + replacement + src[m.end():]
p.write_text(src2, encoding="utf-8")
print("OK: patched live_status() realized parsing (supports both shapes)")
