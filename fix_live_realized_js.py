from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\templates\live.html")
if not p.exists():
    # fallback if live.html is not under templates in your repo
    p = Path(r"C:\TradeAlerts\live.html")
    if not p.exists():
        raise SystemExit("ERROR: live.html not found at C:\\TradeAlerts\\templates\\live.html or C:\\TradeAlerts\\live.html")

src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(p.suffix + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# 1) Remove the BROKEN block that references day/week/month before they exist
# This block sits between the unrealized pnl setColor(...) and the REALIZED P&L comment.
broken_pat = re.compile(
    r'(?s)'
    r'(setColor\(document\.querySelector\(\'#kpi-pnl-day-pct\'\),\s*dPct\);\s*)'
    r'(?:\s*const\s+dR\s*=.*?set\(\s*\'#kpi-r-month-pct\'\s*,\s*pct\(mRPct\)\s*\);\s*)'
    r'(\s*//\s*---\s*REALIZED\s*P&L.*?\n)',
)

src2, n = broken_pat.subn(r"\1\2", src, count=1)
if n != 1:
    print("WARN: did not find the broken pre-realized block (pattern mismatch). Continuing…")
    src2 = src

# 2) Remove the duplicate setColor block that repeats right after the correct realized section
dup_colors_pat = re.compile(
    r'(?s)'
    r'(setColor\(document\.querySelector\(\'#kpi-r-month-pct\'\),\s*mRPct\);\s*)'
    r'\s*// Optional: one-line debug.*?'
    r'(?:\s*setColor\(document\.querySelector\(\'#kpi-r-day\'\),\s*dR\);\s*'
    r'setColor\(document\.querySelector\(\'#kpi-r-day-pct\'\),\s*dRPct\);\s*'
    r'setColor\(document\.querySelector\(\'#kpi-r-week\'\),\s*wR\);\s*'
    r'setColor\(document\.querySelector\(\'#kpi-r-week-pct\'\),\s*wRPct\);\s*'
    r'setColor\(document\.querySelector\(\'#kpi-r-month\'\),\s*mR\);\s*'
    r'setColor\(document\.querySelector\(\'#kpi-r-month-pct\'\),\s*mRPct\);\s*)'
)

src3, n2 = dup_colors_pat.subn(r"\1", src2, count=1)
if n2 != 1:
    print("WARN: did not find duplicate setColor block (pattern mismatch). Continuing…")
    src3 = src2

p.write_text(src3, encoding="utf-8")
print("OK: live.html realized P&L JS fixed (removed broken early refs + duplicate colors)")
