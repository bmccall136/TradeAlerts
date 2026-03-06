import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_trv_chart_blackout_nonmarket_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """        ax.plot(close.index, close.values, linewidth=2)

        # Shade held period if buy_ts and sell_ts exist (best effort)
        def _to_index_tz(dt):"""

new = """        ax.plot(close.index, close.values, linewidth=2)

        # Black out non-market / no-candle gaps (overnight, premarket holes, etc.)
        try:
            import pandas as _pd
            _idx = close.index
            if len(_idx) >= 2:
                for _i in range(1, len(_idx)):
                    try:
                        _prev = _idx[_i - 1]
                        _cur = _idx[_i]
                        _mins = (_cur - _prev).total_seconds() / 60.0
                        if _mins > 20:
                            ax.axvspan(_prev, _cur, color="black", alpha=0.35, zorder=0)
                    except Exception:
                        pass
        except Exception:
            pass

        # Shade held period if buy_ts and sell_ts exist (best effort)
        def _to_index_tz(dt):"""

if old not in txt:
    raise SystemExit("Target plot block not found.")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_CHART_BLACKOUT_NONMARKET_V1")
