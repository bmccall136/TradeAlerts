import pathlib, shutil, datetime, re

targets = [
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html"),
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review.html"),
]

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
patched = 0

patterns = [
    re.compile(r'<!-- MM_TRV_RUNTIME_MARKS_FORCE_V2 -->[\s\S]*?<!-- /?MM_TRV_RUNTIME_MARKS_FORCE_V2 -->\s*', re.I),
    re.compile(r'<!-- MM_TRV_RUNTIME_MARKS_FORCE_V2 -->[\s\S]*?</script>\s*', re.I),
    re.compile(r'<!-- MM_TRV_RUNTIME_CHART_PARAMS_V1 -->[\s\S]*?</script>\s*', re.I),
]

for p in targets:
    if not p.exists():
        continue

    txt = p.read_text(encoding="utf-8", errors="replace")
    bak = p.with_name(p.name + f".bak_remove_conflicting_runtime_v1_{ts}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")

    orig = txt
    for pat in patterns:
        txt = pat.sub("", txt)

    if txt != orig:
        p.write_text(txt, encoding="utf-8", newline="\n")
        print(f"PATCHED -> {p}")
        patched += 1
    else:
        print(f"UNCHANGED -> {p}")

print(f"PATCH_COUNT={patched}")
