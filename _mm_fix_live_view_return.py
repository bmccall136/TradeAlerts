import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_fix_live_view_return_{ts}")
shutil.copy2(P, bak)
txt = P.read_text(encoding="utf-8", errors="replace")

# Grab the live_view function block
m = re.search(r'(?ms)^@app\.route\(\s*[\'"]/live[\'"]\s*\)\s*\ndef\s+live_view\s*\(\s*\)\s*:\s*\n(.*?)(?=^\s*def\s|\Z)', txt)
if not m:
    raise SystemExit("ERROR: Could not find @app.route('/live') def live_view() block")

block = m.group(0)

# Ensure a correct return exists at top-level indent inside live_view
RET = '    return render_template("live.html", account=account, holdings=holdings)\n'

# Remove any mis-indented render_template return lines inside the block (too deep or too shallow)
block2 = re.sub(r'(?m)^\s*return\s+render_template\(\s*[\'"]live\.html[\'"].*?\)\s*$', '', block)

# Ensure we end with exactly one proper return
# Insert return just before the end of the function block (before next def / EOF)
# i.e., append to the end of the live_view block
if 'return render_template("live.html"' not in block2:
    # Make sure block ends with a newline
    if not block2.endswith("\n"):
        block2 += "\n"
    block2 += "\n" + RET

# Replace in full text
txt2 = txt[:m.start()] + block2 + txt[m.end():]
P.write_text(txt2, encoding="utf-8", errors="replace")

print("Backup ->", bak)
print("PATCHED ->", P)
