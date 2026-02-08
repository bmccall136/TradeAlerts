from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\import_realized_from_etrade_csv.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

src2 = src

# Remove common "net wash sale" adjustments
patterns = [
    # gain += deferred
    (r"(?m)^\s*gain\s*\+=\s*deferred\w*\s*$", "    # NOTE: ignore deferred loss for realized P&L tile\n"),
    # gain = gain + deferred
    (r"(?m)^\s*gain\s*=\s*gain\s*\+\s*deferred\w*\s*$", "    # NOTE: ignore deferred loss for realized P&L tile\n"),
    # gain = float(...) + deferred
    (r"(?m)^\s*gain\s*=\s*(.+?)\+\s*deferred\w*\s*$", r"gain = \1  # NOTE: deferred loss ignored\n"),
    # gain = something; if deferred: gain += deferred
    (r"(?ms)(^\s*if\s+deferred\w*\s*:\s*\n)(\s*gain\s*\+=\s*deferred\w*\s*\n)", r"\1    # NOTE: deferred loss ignored\n"),
]

for pat, repl in patterns:
    src2 = re.sub(pat, repl, src2)

if src2 == src:
    raise SystemExit("ERROR: Patch made no changes. The importer may use a different variable name. Re-run Select-String and paste the Deferred block here.")

p.write_text(src2, encoding="utf-8")
print("OK: patched importer to ignore Deferred Loss when computing gain")
