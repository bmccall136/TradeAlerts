from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\live_loop.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

src2 = src.replace("# ... rest of your logic\n", "")
src2 = src2.replace("# ... candidate logic continues ...\n", "")

if src2 == src:
    print("WARN: nothing changed (lines not found).")
else:
    p.write_text(src2, encoding="utf-8")
    print("OK: removed placeholder comments")

