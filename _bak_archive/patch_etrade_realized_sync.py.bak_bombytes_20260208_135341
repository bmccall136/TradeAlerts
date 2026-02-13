import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")
bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# --- Patch 1: replace the broken INSERT (gain, close_date) with full-schema compatible INSERT
old_insert = r'"INSERT INTO realized_trades \(gain, close_date\) VALUES \(\?, \?\)",'
new_insert = r'"INSERT INTO realized_trades (symbol, action, qty, close_date, gain) VALUES (?, ?, ?, ?, ?)",'

src2, n1 = re.subn(old_insert, new_insert, src, flags=re.IGNORECASE)
if n1 != 1:
    raise SystemExit(f"ERROR: expected to replace 1 insert line, replaced {n1}")

# --- Patch 2: ensure CREATE TABLE block matches your live.db schema (only if it's still the "minimal" one)
# We'll replace ONLY if we detect a minimal create table definition that doesn't include required cols like symbol/action/qty.
create_pat = re.compile(
    r'(CREATE TABLE IF NOT EXISTS realized_trades\s*\(\s*)(.*?)(\)\s*;)',
    re.IGNORECASE | re.DOTALL
)

m = create_pat.search(src2)
if not m:
    print("WARN: CREATE TABLE block not found; leaving as-is.")
    src3 = src2
else:
    body = m.group(2)
    # Only replace if it's minimal / incompatible
    if ("symbol" not in body.lower()) or ("action" not in body.lower()) or ("qty" not in body.lower()):
        full_body = """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            qty REAL NOT NULL,
            open_date TEXT,
            close_date TEXT NOT NULL,
            price_share REAL,
            proceeds REAL,
            cost_share REAL,
            total_cost REAL,
            gain REAL,
            term TEXT,
            price_paid REAL,
            price_sold REAL
        """.strip("\n")

        src3 = src2[:m.start(2)] + full_body + src2[m.end(2):]
        print("Patched CREATE TABLE realized_trades -> full schema")
    else:
        src3 = src2
        print("CREATE TABLE already looks full; leaving as-is.")

p.write_text(src3, encoding="utf-8")
print("OK patched", p)
