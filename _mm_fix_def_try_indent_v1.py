import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_fix_def_try_indent_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

# Fix: "def ...:\ntry:" at same indent -> indent the try by 4 spaces
pat = re.compile(r"(?m)^(?P<ind>[ \t]*)def(?P<rest>[^\n]*):\s*\n(?P=ind)try:\s*$")
new_txt, n = pat.subn(r"\g<ind>def\g<rest>:\n\g<ind>    try:", txt)

# Also handle accidental tabs (still indent 1 level deeper, using 4 spaces)
pat2 = re.compile(r"(?m)^(?P<ind>[ \t]*)def(?P<rest>[^\n]*):\s*\n(?P=ind)\t*try:\s*$")
new_txt, n2 = pat2.subn(r"\g<ind>def\g<rest>:\n\g<ind>    try:", new_txt)

total = n + n2
P.write_text(new_txt, encoding="utf-8")
print(r"PATCHED -> C:\TradeAlerts\dashboard.py")
print("Fixed def/try indentation sites ->", total)

if total == 0:
    print("NOTE: No 'def...\\ntry:' same-indent sites found. If crash persists, we’ll patch the specific handler block by markers next.")
