import pathlib, datetime, shutil

P = pathlib.Path(r"C:\TradeAlerts\templates\layout.html")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".html.bak_fix_doctype_prefix_v1_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

raw = P.read_bytes()

# decode using utf-8-sig to strip BOM if present
txt = raw.decode("utf-8-sig", errors="replace")

needle = "<!DOCTYPE html"
k = txt.lower().find(needle.lower())
if k < 0:
    raise SystemExit("ERROR: <!DOCTYPE html not found in layout.html")

if k > 0:
    removed = txt[:k]
    print(f"Removing {k} chars before DOCTYPE (this was causing Quirks Mode).")
    txt = txt[k:]
else:
    print("DOCTYPE already at start (no prefix to remove).")

# write back WITHOUT BOM
P.write_text(txt, encoding="utf-8", errors="replace")
print("PATCHED ->", P)

# quick sanity: print first line
first = txt.splitlines()[0] if txt.splitlines() else ""
print("First line now:", first)
