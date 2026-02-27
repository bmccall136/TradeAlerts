import re, shutil, datetime, pathlib, sys

FILES = [
  pathlib.Path(r"C:\TradeAlerts\templates\settings_sell.html"),
  pathlib.Path(r"C:\TradeAlerts\templates\settings_buy.html"),
]

MARK_RE = re.compile(r"(?s)<!--\s*(MM_REGIME_EXIT_OVERLAY_UI_[A-Z0-9_]+_START)\s*-->.*?<!--\s*(MM_REGIME_EXIT_OVERLAY_UI_[A-Z0-9_]+_END)\s*-->")

def patch_one(p: pathlib.Path):
    if not p.exists():
        print(f"SKIP (missing): {p}")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_suffix(p.suffix + f".bak_fix_overlay_loc_v1_{ts}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")

    txt = p.read_text(encoding="utf-8", errors="replace")

    m = MARK_RE.search(txt)
    if not m:
        print(f"NO_MARKERS -> {p} (nothing changed)")
        return

    block = m.group(0)

    # Remove ALL copies (avoid duplicates)
    txt2 = MARK_RE.sub("", txt).rstrip() + "\n"

    endblock = "{% endblock %}"
    j = txt2.rfind(endblock)
    if j < 0:
        raise SystemExit(f"ERROR: could not find '{{% endblock %}}' in {p}")

    # Insert block immediately before endblock
    txt3 = txt2[:j].rstrip() + "\n\n" + block.strip() + "\n\n" + txt2[j:]

    p.write_text(txt3, encoding="utf-8")
    print(f"PATCHED -> {p}")

for f in FILES:
    patch_one(f)

print("DONE. Hard refresh the Settings pages (Ctrl+F5).")