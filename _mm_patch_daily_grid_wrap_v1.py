import re, shutil
from datetime import datetime

path = r"C:\TradeAlerts\templates\analytics.html"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{path}.bak_mm_daily_grid_wrap_v1_{ts}"
shutil.copy2(path, bak)
print("Backup ->", bak)

s = open(path, "r", encoding="utf-8").read()

MARK_OPEN = "<!-- MM_DAILY_GRID_WRAP_OPEN_V1 -->"
MARK_CLOSE = "<!-- MM_DAILY_GRID_WRAP_CLOSE_V1 -->"

if MARK_OPEN in s and MARK_CLOSE in s:
    print("OK: grid wrap markers already present; no change.")
    raise SystemExit(0)

pat = r'(<div\s+class="d-flex\s+align-items-center\s+justify-content-between\s+mb-2"[^>]*>.*?</div>)'
m = re.search(pat, s, flags=re.I|re.S)
if not m:
    print("ERROR: Could not find header row block (d-flex align-items-center justify-content-between mb-2).")
    raise SystemExit(2)

hdr_end = m.end()
OPEN_HTML = "\n\n" + MARK_OPEN + "\n" + '<div class="mm-analytics-grid">' + "\n"
s = s[:hdr_end] + OPEN_HTML + s[hdr_end:]

m2 = re.search(r'\n\s*<script\b', s, flags=re.I)
if not m2:
    print("ERROR: Could not find a <script> tag to anchor closing grid.")
    raise SystemExit(3)

ins = m2.start()
CLOSE_HTML = "\n</div>\n" + MARK_CLOSE + "\n"
s = s[:ins] + CLOSE_HTML + s[ins:]

open(path, "w", encoding="utf-8", newline="\n").write(s)
print("PATCHED ->", path, "(added mm-analytics-grid wrap)")

s2 = open(path, "r", encoding="utf-8").read()
print("verify_open=", (MARK_OPEN in s2))
print("verify_close=", (MARK_CLOSE in s2))
