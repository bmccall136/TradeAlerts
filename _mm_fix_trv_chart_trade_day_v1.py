import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_trv_chart_trade_day_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """        # Pull 1d 1m bars (Yahoo intraday is allowed)
        df = yf.download(symbol, period="1d", interval="1m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            raise RuntimeError("No intraday bars returned")"""

new = """        # Pull intraday bars for the trade day when ts is provided; otherwise latest 1d.
        if ts:
            try:
                _start_day = ts.strftime("%Y-%m-%d")
                _end_day = (ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                df = yf.download(symbol, start=_start_day, end=_end_day, interval="1m", progress=False, auto_adjust=True)
            except Exception:
                df = yf.download(symbol, period="2d", interval="1m", progress=False, auto_adjust=True)
        else:
            df = yf.download(symbol, period="1d", interval="1m", progress=False, auto_adjust=True)

        if df is None or df.empty:
            raise RuntimeError("No intraday bars returned")"""

if old not in txt:
    raise SystemExit("Target download block not found.")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_CHART_TRADE_DAY_V1")
