import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_trv_chart_force_trade_date_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """        # Normalize index to US/Eastern if possible
        try:
            et = pytz.timezone("America/New_York")
            if df.index.tz is None:
                # yfinance often gives naive index; treat as UTC then convert
                df.index = pd.to_datetime(df.index).tz_localize("UTC").tz_convert(et)
            else:
                df.index = df.index.tz_convert(et)
        except Exception:
            # fallback: keep as-is
            pass

        # Focus window: around ts if provided (?60 minutes), else full day
        if ts:
            # interpret ts as ET naive -> localize ET if df index is tz-aware
            try:
                et = pytz.timezone("America/New_York")
                ts_et = et.localize(ts) if df.index.tz is not None and ts.tzinfo is None else ts
                lo = ts_et - pd.Timedelta(minutes=60)
                hi = ts_et + pd.Timedelta(minutes=60)
                dfw = df.loc[(df.index >= lo) & (df.index <= hi)].copy()
                if dfw.empty:
                    dfw = df.copy()
            except Exception:
                dfw = df.copy()
        else:
            dfw = df.copy()"""

new = """        # Normalize index to US/Eastern if possible
        try:
            et = pytz.timezone("America/New_York")
            if df.index.tz is None:
                # yfinance often gives naive index; treat as UTC then convert
                df.index = pd.to_datetime(df.index).tz_localize("UTC").tz_convert(et)
            else:
                df.index = df.index.tz_convert(et)
        except Exception:
            # fallback: keep as-is
            pass

        # Force data to the trade date when ts is provided
        if ts:
            try:
                et = pytz.timezone("America/New_York")
                ts_et = et.localize(ts) if getattr(df.index, "tz", None) is not None and ts.tzinfo is None else ts
                trade_day = ts_et.date()
                dmask = pd.to_datetime(df.index).date == trade_day
                dfd = df.loc[dmask].copy()
                if not dfd.empty:
                    df = dfd
            except Exception:
                pass

        # Focus window: around ts if provided (?60 minutes), else full day
        if ts:
            # interpret ts as ET naive -> localize ET if df index is tz-aware
            try:
                et = pytz.timezone("America/New_York")
                ts_et = et.localize(ts) if df.index.tz is not None and ts.tzinfo is None else ts
                lo = ts_et - pd.Timedelta(minutes=60)
                hi = ts_et + pd.Timedelta(minutes=60)
                dfw = df.loc[(df.index >= lo) & (df.index <= hi)].copy()
                if dfw.empty:
                    dfw = df.copy()
            except Exception:
                dfw = df.copy()
        else:
            dfw = df.copy()"""

if old not in txt:
    raise SystemExit("Target block not found.")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_CHART_FORCE_TRADE_DATE_V1")
