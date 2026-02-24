import shutil, datetime, pathlib, re

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_fix_candidate_fires_block_indent_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

START = "MM_CANDIDATE_FIRES_DB_OVERRIDE_V2S_START"
END   = "MM_CANDIDATE_FIRES_DB_OVERRIDE_V2S_END"

# Find the candidate_fires handler and its indent
m = re.search(r'(?ms)^@app\.route\(\s*([\'"])/api/analytics/candidate_fires\1[^)]*\)\s*\n(?P<ind>[ \t]*)def[ \t]+[A-Za-z0-9_]+[ \t]*\([^\n]*\)[ \t]*:[ \t]*\n', txt)
if not m:
    raise SystemExit("ERROR: Could not find /api/analytics/candidate_fires route+def block.")

def_ind = m.group("ind")
body_prefix = def_ind + "    "  # 4 spaces under the def
after_def = m.end()

# Find START/END markers AFTER the def
s = txt.find(f"# {START}", after_def)
if s < 0:
    raise SystemExit("ERROR: START marker not found after candidate_fires def.")
e = txt.find(f"# {END}", s)
if e < 0:
    raise SystemExit("ERROR: END marker not found after START marker.")

# Include the entire END line + trailing newline (if present)
end_line_end = txt.find("\n", e)
if end_line_end < 0:
    end_line_end = len(txt)
else:
    end_line_end += 1

block = txt[s:end_line_end]

# Indent every non-empty line in the block by 4 spaces (preserve internal structure)
lines = block.splitlines(True)
new_block = "".join((body_prefix + ln) if ln.strip() else ln for ln in lines)

new_txt = txt[:s] + new_block + txt[end_line_end:]
P.write_text(new_txt, encoding="utf-8")

print(r"PATCHED -> C:\TradeAlerts\dashboard.py")
print("Indented V2S block under candidate_fires def (START..END).")
