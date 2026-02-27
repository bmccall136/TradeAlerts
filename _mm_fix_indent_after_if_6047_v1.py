import datetime, shutil, re
from pathlib import Path

p = Path(r"C:\TradeAlerts\dashboard.py")
if not p.exists():
    raise SystemExit(f"Missing: {p}")

txt = p.read_text(encoding="utf-8", errors="replace")
lines = txt.splitlines(True)  # keep line endings

need_line = 6050
if len(lines) < need_line:
    raise SystemExit(f"dashboard.py only has {len(lines)} lines; expected at least {need_line}. Not patching.")

idx = 6047 - 1  # line 6047 -> 0-based index
line_if = lines[idx]

m = re.match(r'^(\s*)if\b.*:\s*$', line_if)
if not m:
    raise SystemExit(f"Line 6047 does not look like an if-statement. Got: {line_if.strip()!r}")

indent = m.group(1)
k = idx + 1
# skip blank/comment lines
while k < len(lines) and (lines[k].strip() == "" or lines[k].lstrip().startswith("#")):
    k += 1

# If next meaningful line is NOT indented as an if-body, insert a pass.
body_indent = indent + "    "
if k < len(lines) and not lines[k].startswith(body_indent):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_suffix(p.suffix + f".bak_fix_indent_after_if_6047_v1_{ts}")
    shutil.copy2(p, bak)
    lines.insert(idx + 1, body_indent + "pass\n")
    p.write_text("".join(lines), encoding="utf-8")
    print(f"Backup -> {bak}")
    print("PATCHED: inserted 'pass' under line 6047 to fix IndentationError.")
    print("Context:")
    for i in range(idx-2, idx+6):
        if 0 <= i < len(lines):
            print(f"{i+1:>6}: {lines[i].rstrip()}")
else:
    print("No change needed: line after 6047 is already indented (or file ends).")