import re, shutil
from datetime import datetime

path = r"C:\TradeAlerts\templates\analytics.html"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{path}.bak_mm_move_daily_grid_open_v1_{ts}"
shutil.copy2(path, bak)
print("Backup ->", bak)

s = open(path, "r", encoding="utf-8").read()

OPEN = "<!-- MM_DAILY_GRID_WRAP_OPEN_V1 -->"
CLOSE = "<!-- MM_DAILY_GRID_WRAP_CLOSE_V1 -->"
GRID = '<div class="mm-analytics-grid">'

if OPEN not in s or CLOSE not in s:
    raise SystemExit("ERROR: grid markers not found (OPEN/CLOSE).")

# 1) Remove the current OPEN + immediate grid div (wherever it is)
# Allow whitespace/newlines between marker and grid tag.
pat_remove = re.compile(r'(?s)\s*' + re.escape(OPEN) + r'\s*' + re.escape(GRID) + r'\s*')
m = pat_remove.search(s)
if not m:
    raise SystemExit("ERROR: Could not find OPEN+grid div block to remove.")

s_removed = s[:m.start()] + "\n" + s[m.end():]
print("Removed existing OPEN+grid div block.")

# 2) Find insertion point: first <div class="card ..."> AFTER the toolbar/date controls
# We'll pick the first occurrence of '<div class="card' after the toolbar block.
# (This is stable across your pages.)
m_card = re.search(r'(?i)<div\s+class="card\b', s_removed)
if not m_card:
    # fallback: first table as content anchor
    m_card = re.search(r'(?i)<table\b', s_removed)
if not m_card:
    raise SystemExit("ERROR: Could not find a card/table anchor to place the grid before.")

ins = m_card.start()

insert_block = "\n" + OPEN + "\n" + GRID + "\n"
s2 = s_removed[:ins] + insert_block + s_removed[ins:]
print("Inserted OPEN+grid div before first content card/table.")

# 3) Sanity: ensure we have exactly one grid div open
grid_count = len(re.findall(re.escape(GRID), s2))
print("grid_div_count=", grid_count)

# 4) Ensure CLOSE is preceded by a closing </div> for the grid; if not, add it
# We expect: </div>\n<!-- CLOSE -->
m_close = re.search(re.escape(CLOSE), s2)
if not m_close:
    raise SystemExit("ERROR: CLOSE marker vanished.")
pre = s2[max(0, m_close.start()-200):m_close.start()]
if "</div>" not in pre:
    s2 = s2[:m_close.start()] + "\n</div>\n" + s2[m_close.start():]
    print("Inserted missing </div> before CLOSE marker.")
else:
    print("CLOSE marker already has a </div> before it.")

open(path, "w", encoding="utf-8").write(s2)
print("PATCHED ->", path)

# Quick verify snippet around OPEN
idx = s2.find(OPEN)
print("OPEN_near=", idx)
print("Snippet_after_OPEN:")
print(s2[idx:idx+250].replace("\\n","\\\\n")[:250])
