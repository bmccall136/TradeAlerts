from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# If API_BASE already exists, don't touch anything.
if re.search(r'(?m)^\s*API_BASE\s*=', src):
    print("OK: API_BASE already defined (no change).")
    raise SystemExit(0)

# Try to find an existing base constant we can alias to (common names)
alias_targets = [
    "BASE_URL", "API_ROOT", "ETRADE_BASE", "ETRADE_API_BASE", "ROOT_URL"
]

alias = None
for name in alias_targets:
    if re.search(rf'(?m)^\s*{re.escape(name)}\s*=\s*[\'"]', src):
        alias = name
        break

if alias:
    inject = f'\n# --- Added by patch: missing constant used by list_trade_transactions()\nAPI_BASE = {alias}\n'
else:
    # Safe default for production (you run production only)
    inject = (
        '\n# --- Added by patch: missing constant used by list_trade_transactions()\n'
        'API_BASE = "https://api.etrade.com/v1"\n'
    )

# Insert after the last import line near the top of file
lines = src.splitlines()
insert_at = 0
for i, line in enumerate(lines[:400]):  # only scan early header
    if line.startswith("import ") or line.startswith("from "):
        insert_at = i + 1

lines.insert(insert_at, inject.rstrip("\n"))
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("OK: inserted API_BASE at line", insert_at + 1)
