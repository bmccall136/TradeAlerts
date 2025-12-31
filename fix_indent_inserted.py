import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Fix the one bad line that got de-indented to column 0.
# We ONLY want the 'inserted += 1' that appears right before 'except Exception:' in this sync loop.
pat = re.compile(r'\ninserted\s*\+=\s*1\s*\n(\s*except\s+Exception\s*:\s*\n)', re.MULTILINE)

src2, n = pat.subn(r'\n            inserted += 1\n\1', src)
if n != 1:
    raise SystemExit(f"ERROR: expected to indent 1 'inserted += 1' before except, indented {n}")

p.write_text(src2, encoding="utf-8")
print("OK indented inserted += 1")
