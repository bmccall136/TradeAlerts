from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\import_realized_from_etrade_csv.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Replace the specific net_gain logic with plain gain
pat = re.compile(
    r"(?ms)"
    r"^\s*#\s*IMPORTANT:\s*wash-sale.*?\n"
    r"^\s*#\s*For a .*?\n"
    r"^\s*net_gain\s*=\s*gain\s*\+\s*deferred\s*\n"
)

m = pat.search(src)
if not m:
    raise SystemExit("ERROR: Could not find the wash-sale net_gain block to replace.")

replacement = (
    "                # NOTE: For dashboard realized P&L tiles, we use broker 'Gain $' ONLY.\n"
    "                # Deferred Loss $ is a wash-sale adjustment and is tracked separately.\n"
    "                net_gain = gain\n"
)

src2 = src[:m.start()] + replacement + src[m.end():]

# Also ensure the INSERT uses net_gain (it will now equal gain)
if "net_gain" not in src2:
    raise SystemExit("ERROR: net_gain disappeared unexpectedly after patch.")

p.write_text(src2, encoding="utf-8")
print("OK: importer now ignores Deferred Loss in realized_trades.gain (net_gain = gain)")
