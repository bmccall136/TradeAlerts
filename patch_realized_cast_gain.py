from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\services\realized_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

src2 = re.sub(r"SUM\(gain\)", "SUM(CAST(gain AS REAL))", src)
if src2 == src:
    raise SystemExit("No SUM(gain) patterns found to replace.")

p.write_text(src2, encoding="utf-8")
print("OK: forced CAST(gain AS REAL) in SUM() calls")
