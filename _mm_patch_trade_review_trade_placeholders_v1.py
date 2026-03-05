import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_trade.html")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".html.bak_trv_trade_placeholders_v1_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_TRADE_PLACEHOLDERS_V1"
if MARK in txt:
    print("Already patched."); raise SystemExit(0)

def ins(after_pat, ins_html):
    nonlocal_txt = None
    return re.sub(after_pat, lambda m: m.group(0) + "\n" + ins_html, txt, count=1, flags=re.I|re.S)

# Insert buy placeholder
buy_ins = f"<!-- {MARK} -->\n<div id=\"mm-trv-buy-box\"></div>\n<!-- /{MARK} -->"
txt2 = re.sub(r'(?is)(<h3[^>]*>\s*Buy\s+Triggers\b.*?>)', r'\1' + "\n" + buy_ins, txt, count=1)

# Insert sell placeholder
sell_ins = f"<!-- {MARK} -->\n<div id=\"mm-trv-sell-box\"></div>\n<!-- /{MARK} -->"
txt3 = re.sub(r'(?is)(<h3[^>]*>\s*Sell\s+Triggers\b.*?>)', r'\1' + "\n" + sell_ins, txt2, count=1)

P.write_text(txt3, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
