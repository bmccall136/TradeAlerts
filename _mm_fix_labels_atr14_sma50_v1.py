import re, shutil, datetime, pathlib

ROOT = pathlib.Path(r"C:\TradeAlerts\templates")
if not ROOT.exists():
    raise SystemExit(f"ERROR: templates dir not found: {ROOT}")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# Targets: settings pages (buy/sell) - patch any template that contains window.__MM_CFG__
targets = []
for p in sorted(ROOT.glob("*.html")):
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if "window.__MM_CFG__" in t:
        targets.append(p)

if not targets:
    raise SystemExit("ERROR: no templates containing window.__MM_CFG__ found in templates/*.html")

def patch(txt: str):
    changed = 0

    # PRICE SMA already renamed -> SMA50 in your file; we leave it alone.

    # RANGE should display as ATR14 (RMA) in UI
    txt2, n1 = re.subn(r'(\{"key":\s*"range",\s*"label":\s*")Range(")', r'\1ATR14 (RMA)\2', txt)
    txt, changed = txt2, changed + n1

    txt2, n2 = re.subn(r'(\{"k":\s*"range_pct",\s*"label":\s*")Range %(")', r'\1ATR14 Threshold\2', txt)
    txt, changed = txt2, changed + n2

    txt2, n3 = re.subn(r'(\{"key":\s*"range",\s*"label":\s*")RANGE(")', r'\1ATR14\2', txt)
    txt, changed = txt2, changed + n3

    # ATR card (the enhancer one) should be labeled clearly
    txt2, n4 = re.subn(r'(\{"key":\s*"atr",\s*"label":\s*")ATR(")', r'\1ATR (Enhancer)\2', txt)
    txt, changed = txt2, changed + n4

    return txt, changed

touched = []
for p in targets:
    txt = p.read_text(encoding="utf-8", errors="replace")
    new_txt, n = patch(txt)
    if n > 0:
        bak = p.with_suffix(f".html.bak_fix_labels_atr14_sma50_v1_{ts}")
        shutil.copy2(p, bak)
        p.write_text(new_txt, encoding="utf-8")
        touched.append((str(p), str(bak), n))

print("PATCH_DONE")
for f, b, n in touched:
    print(f"- {f}")
    print(f"  backup: {b}")
    print(f"  edits:  {n}")

if not touched:
    print("NOTE: No changes were needed (already correct).")
