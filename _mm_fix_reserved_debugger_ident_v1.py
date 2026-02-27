import re, shutil, datetime
from pathlib import Path

ROOT = Path(r"C:\TradeAlerts")
targets = []
for ext in (".js", ".html"):
    targets += list(ROOT.rglob(f"*{ext}"))

# Only illegal identifier uses (NOT the debugger; statement)
PATTERNS = [
    (re.compile(r'(?m)^(\s*)(let|const|var)\s+debugger(\s*=)', re.I), r'\1\2 dbg\3'),
    (re.compile(r'(?m)^(\s*)function\s+debugger(\s*\()', re.I), r'\1function dbg\2'),
    (re.compile(r'(?m)^(\s*)class\s+debugger(\s*[{])', re.I), r'\1class dbg\2'),
]

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
changed = 0

for p in targets:
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue

    new = txt
    for rx, rep in PATTERNS:
        new = rx.sub(rep, new)

    if new != txt:
        bak = p.with_suffix(p.suffix + f".bak_fix_debugger_ident_v1_{ts}")
        shutil.copy2(p, bak)
        p.write_text(new, encoding="utf-8")
        print(f"PATCHED -> {p} (backup {bak})")
        changed += 1

print(f"DONE. files_changed={changed}")