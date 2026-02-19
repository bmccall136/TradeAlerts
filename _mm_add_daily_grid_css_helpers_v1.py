import os, shutil
from datetime import datetime

css_path = r"C:\TradeAlerts\static\style.css"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{css_path}.bak_mm_daily_grid_css_helpers_v1_{ts}"
shutil.copy2(css_path, bak)
print("Backup ->", bak)

s = open(css_path, "r", encoding="utf-8").read()

MARK = "/* MM_DAILY_GRID_CSS_HELPERS_V1 */"
block = f"""
{MARK}
.mm-analytics-grid > * {{ min-width: 0; }}
.mm-analytics-grid .card {{ width: 100%; }}
"""

if MARK in s:
    print("OK: helpers already present.")
else:
    open(css_path, "w", encoding="utf-8", newline="\\n").write(s.rstrip() + "\\n\\n" + block.lstrip("\\n"))
    print("PATCHED ->", css_path)
