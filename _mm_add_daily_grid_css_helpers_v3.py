import shutil
from datetime import datetime

css_path = r"C:\TradeAlerts\static\style.css"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{css_path}.bak_mm_daily_grid_css_helpers_v3_{ts}"
shutil.copy2(css_path, bak)
print("Backup ->", bak)

s = open(css_path, "r", encoding="utf-8").read()

MARK = "/* MM_DAILY_GRID_CSS_HELPERS_V1 */"
block = (
    "\\n" + MARK + "\\n"
    ".mm-analytics-grid > * { min-width: 0; }\\n"
    ".mm-analytics-grid .card { width: 100%; }\\n"
)

if MARK in s:
    print("OK: helpers already present.")
else:
    out = s.replace("\\r\\n", "\\n").rstrip("\\n") + "\\n" + block.lstrip("\\n")
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(out)
    print("PATCHED ->", css_path)
