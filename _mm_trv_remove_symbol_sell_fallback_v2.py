import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_remove_symbol_sell_fallback_v2_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

orig = txt

patterns = [
    re.compile(r'''
        \s*if\s*\(\s*!_match\s*&&\s*_symbol\s*\)\s*\{
        [\s\S]*?
        \}
    ''', re.X),
    re.compile(r'''
        \s*if\s*\(\s*!_match\s*&&\s*_sells\.length\s*\)\s*\{
        [\s\S]*?
        \}
    ''', re.X),
]

for pat in patterns:
    txt = pat.sub(
        '\n          // MM_TRV_REMOVE_SYMBOL_SELL_FALLBACK_V2: removed unsafe fallback\n',
        txt,
        count=1
    )

if txt == orig:
    raise SystemExit("No symbol/first-sell fallback blocks were found")

P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_REMOVE_SYMBOL_SELL_FALLBACK_V2")
