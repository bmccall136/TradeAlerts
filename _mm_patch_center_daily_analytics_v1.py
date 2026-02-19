import os, re, glob, shutil
from datetime import datetime

ROOT = r"C:\TradeAlerts"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

def backup(path, tag):
    b = f"{path}.bak_{tag}_{ts}"
    shutil.copy2(path, b)
    print(f"Backup -> {b}")
    return b

def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write(path, s):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)

# 1) Append analytics-only CSS
css_path = os.path.join(ROOT, "static", "style.css")
if not os.path.exists(css_path):
    css_path = os.path.join(ROOT, "style.css")

if not os.path.exists(css_path):
    raise SystemExit("ERROR: style.css not found at C:\\TradeAlerts\\static\\style.css or C:\\TradeAlerts\\style.css")

css = read(css_path)

MARK = "/* MM_ANALYTICS_CENTER_WRAP_V1 */"
CSS_BLOCK = f"""
{MARK}
/* === Analytics Centered Layout === */
.mm-analytics-wrap {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px 24px 40px 24px;
}}

.mm-analytics-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
}}

@media (max-width: 1100px) {{
  .mm-analytics-grid {{
    grid-template-columns: 1fr;
  }}
}}
"""

if MARK in css:
    print(f"OK: CSS marker already present in {css_path}")
else:
    backup(css_path, "mm_analytics_center_css_v1")
    write(css_path, css.rstrip() + "\n\n" + CSS_BLOCK.lstrip("\n"))
    print(f"PATCHED -> {css_path} (added analytics centered CSS)")

# 2) Patch Daily Analytics template wrapper
tmpl_dir = os.path.join(ROOT, "templates")
if not os.path.isdir(tmpl_dir):
    raise SystemExit("ERROR: templates folder not found at C:\\TradeAlerts\\templates")

candidates = []
for p in glob.glob(os.path.join(tmpl_dir, "*.html")):
    try:
        t = read(p)
    except Exception:
        continue
    if ("Daily Analytics" in t) and ("container-fluid py-3" in t or "container-fluid" in t):
        candidates.append(p)

if not candidates:
    for p in glob.glob(os.path.join(tmpl_dir, "*.html")):
        try:
            t = read(p)
        except Exception:
            continue
        if "Daily Analytics" in t:
            candidates.append(p)

if not candidates:
    raise SystemExit("ERROR: Could not find a template containing 'Daily Analytics' under C:\\TradeAlerts\\templates")

target = candidates[0]
t = read(target)
changed = 0

# Replace outer container
if 'class="mm-analytics-wrap"' not in t:
    t2, n = re.subn(r'<div\s+class="container-fluid\s+py-3"\s*>', '<div class="mm-analytics-wrap">', t, count=1, flags=re.I)
    if n == 0:
        t2, n = re.subn(r'<div\s+class="container-fluid[^"]*"\s*>', '<div class="mm-analytics-wrap">', t, count=1, flags=re.I)
    if n > 0:
        t = t2
        changed += 1

# Best-effort: wrap BUYS+SELLS block in grid (only if we can do it safely)
if "mm-analytics-grid" not in t and ("BUYS" in t and "SELLS" in t):
    buys_idx = t.find("BUYS")
    sells_idx = t.find("SELLS")
    if buys_idx != -1 and sells_idx != -1 and buys_idx < sells_idx:
        start_div = t.rfind("<div", 0, buys_idx)
        if start_div != -1:
            tail = t[sells_idx:]
            m = re.search(r"</table>", tail, flags=re.I)
            if m:
                end_pos = sells_idx + m.end()
                m2 = re.search(r"</div>", t[end_pos:], flags=re.I)
                end_pos2 = end_pos + (m2.end() if m2 else 0)
                t = t[:start_div] + '<div class="mm-analytics-grid">\n' + t[start_div:end_pos2] + "\n</div>\n" + t[end_pos2:]
                changed += 1

if changed > 0:
    backup(target, "mm_daily_center_wrap_v1")
    write(target, t)
    print(f"PATCHED -> {target} (changed_hits={changed})")
else:
    print(f"OK: No template changes applied -> {target}")

print("DONE. Ctrl+F5 the Daily Analytics page.")
