import pathlib, datetime, shutil

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review.html")  # <-- change after you find actual name
assert P.exists(), P
ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak=P.with_suffix(f".html.bak_stamp_{ts}")
shutil.copy2(P,bak)
print("Backup ->", bak)

txt=P.read_text(encoding="utf-8", errors="replace")
STAMP="MM_TRV_HTTP_STAMP_"+ts
if STAMP in txt:
    print("Already stamped"); raise SystemExit(0)

txt2 = txt + "\n<!-- %s -->\n" % STAMP
P.write_text(txt2, encoding="utf-8", errors="replace")
print("STAMPED ->", P)
print("STAMP:", STAMP)
