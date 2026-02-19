import re, shutil
from datetime import datetime

path = r"C:\TradeAlerts\templates\analytics.html"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{path}.bak_mm_daily_grid_markers_v2_{ts}"
shutil.copy2(path, bak)
print("Backup ->", bak)

s = open(path, "r", encoding="utf-8").read()

MARK_OPEN  = "<!-- MM_DAILY_GRID_WRAP_OPEN_V1 -->"
MARK_CLOSE = "<!-- MM_DAILY_GRID_WRAP_CLOSE_V1 -->"

open_pos = s.find(MARK_OPEN)
if open_pos == -1:
    raise SystemExit("ERROR: OPEN marker not found.")

# Remove ANY CLOSE marker that appears before OPEN (and its preceding </div> line if present)
while True:
    cpos = s.find(MARK_CLOSE)
    if cpos == -1:
        break
    if cpos > s.find(MARK_OPEN):
        break

    start = s.rfind("\n", 0, cpos)
    if start == -1: start = 0

    prev_start = s.rfind("\n", 0, max(0, start-1))
    prev_line = s[prev_start:start].strip() if prev_start != -1 else ""
    if prev_line == "</div>":
        start = prev_start

    end = s.find("\n", cpos)
    if end == -1:
        end = cpos + len(MARK_CLOSE)
    else:
        end = end + 1

    s = s[:start] + s[end:]

# Ensure OPEN is followed by the grid div
s = re.sub(
    re.escape(MARK_OPEN) + r"\s*(?:<div\s+class=""mm-analytics-grid"">\s*)?",
    MARK_OPEN + "\n<div class=\"mm-analytics-grid\">\n",
    s,
    count=1,
    flags=re.I
)

# Insert CLOSE before analytics.js include if present; else before the last <script>
m = re.search(r'\n\s*<script[^>]+analytics\.js[^>]*>\s*</script>\s*', s, flags=re.I)
if m:
    ins = m.start()
else:
    scripts = list(re.finditer(r'\n\s*<script\b', s, flags=re.I))
    if not scripts:
        raise SystemExit("ERROR: No <script> tags found for close anchor.")
    ins = scripts[-1].start()

after_open = s.find(MARK_OPEN)
after_close = s.find(MARK_CLOSE, after_open+1)
if after_close == -1:
    s = s[:ins] + "\n</div>\n" + MARK_CLOSE + "\n" + s[ins:]
    print("Inserted CLOSE marker at bottom anchor.")
else:
    print("CLOSE marker already exists after OPEN; leaving it.")

open(path, "w", encoding="utf-8").write(s)
print("PATCHED ->", path)

s3 = open(path, "r", encoding="utf-8").read()
op = s3.find(MARK_OPEN)
cp = s3.find(MARK_CLOSE, op+1)
print("verify_open_pos=", op)
print("verify_close_pos=", cp)
print("verify_order_ok=", (op != -1 and cp != -1 and cp > op))
