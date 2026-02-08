import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Replace the 2-value tuple with the correct 5-value tuple
pattern = re.compile(
    r'("INSERT INTO realized_trades \(symbol, action, qty, close_date, gain\) VALUES \(\?, \?, \?, \?, \?\)",\s*)\(\s*pl\s*,\s*dt_et\.isoformat\(\)\s*\)',
    re.IGNORECASE
)

replacement = r'\1(sym, action, qty, dt_et.isoformat(), pl)'

src2, n = pattern.subn(replacement, src)
if n != 1:
    raise SystemExit(f"ERROR: expected to replace 1 tuple, replaced {n}")

# Ensure sym/qty are defined just before the INSERT (surgical add if missing)
# We'll inject just above the cur.execute( ... INSERT ... ) line if not already present nearby.
lines = src2.splitlines()
out = []
insert_line_idx = None

for i, line in enumerate(lines):
    if "INSERT INTO realized_trades (symbol, action, qty, close_date, gain)" in line:
        insert_line_idx = i
        break

if insert_line_idx is None:
    raise SystemExit("ERROR: could not locate INSERT line after patch")

# Look back a few lines to see if sym/qty already exist
window = "\n".join(lines[max(0, insert_line_idx-10):insert_line_idx]).lower()
need_inject = ("sym =" not in window) or ("qty =" not in window)

for i, line in enumerate(lines):
    if i == insert_line_idx and need_inject:
        out.append("            sym = str(t.get(\"symbol\", \"\") or \"\").strip().upper()")
        out.append("            if not sym:")
        out.append("                continue")
        out.append("            qty = float(t.get(\"qty\", 0.0) or 0.0)")
        out.append("            if qty <= 0:")
        out.append("                continue")
    out.append(line)

src3 = "\n".join(out)
p.write_text(src3, encoding="utf-8")
print("OK patched tuple + ensured sym/qty")
