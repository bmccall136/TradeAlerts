import pathlib, shutil, datetime, re

targets = [
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html"),
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review.html"),
]

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
patched = 0

needle = """    src = src.replace(/([&?])buy_ts=[^&]*/g, "");
    src = src.replace(/([&?])sell_ts=[^&]*/g, "");
    src = src.replace(/([&?])buy_marks=[^&]*/g, "");
    src = src.replace(/([&?])sell_marks=[^&]*/g, "");
    src = src.replace(/[?&]rtfix=1/g, "");"""

insert = """    src = src.replace(/([&?])ts=[^&]*/g, "");
    src = src.replace(/([&?])buy_ts=[^&]*/g, "");
    src = src.replace(/([&?])sell_ts=[^&]*/g, "");
    src = src.replace(/([&?])buy_marks=[^&]*/g, "");
    src = src.replace(/([&?])sell_marks=[^&]*/g, "");
    src = src.replace(/[?&]rtfix=1/g, "");
    src = src.replace(/[?&]+$/g, "");
    src = src.replace(/&&+/g, "&");
    src = src.replace(/\?&/g, "?");"""

for p in targets:
    if not p.exists():
        continue
    txt = p.read_text(encoding="utf-8", errors="replace")
    bak = p.with_name(p.name + f".bak_runtime_dedupe_query_v1_{ts}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")

    if needle not in txt:
        print(f"UNCHANGED -> {p}")
        continue

    txt = txt.replace(needle, insert, 1)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"PATCHED -> {p}")
    patched += 1

print(f"PATCH_COUNT={patched}")
