import re, shutil
from datetime import datetime

path = r"C:\TradeAlerts\templates\analytics.html"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{path}.bak_mm_daily_grid_dedupe_v1_{ts}"
shutil.copy2(path, bak)
print("Backup ->", bak)

s = open(path, "r", encoding="utf-8").read()

# Replace two consecutive grid div opens with one
pat = r'(<div\s+class="mm-analytics-grid">\s*)(<div\s+class="mm-analytics-grid">\s*)'
s2, n = re.subn(pat, r'\1', s, count=1, flags=re.I)

if n == 0:
    print("OK: no duplicate consecutive grid div found; no change.")
else:
    open(path, "w", encoding="utf-8").write(s2)
    print("PATCHED ->", path, "(removed duplicate mm-analytics-grid div; hits=%d)" % n)

# verify count near marker
MARK_OPEN = "MM_DAILY_GRID_WRAP_OPEN_V1"
idx = s2.find(MARK_OPEN)
print("marker_found=", (idx != -1))
