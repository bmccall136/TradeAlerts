import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_trv_chart_trigger_lines_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old1 = """    ts      = _parse_dt(request.args.get("ts"))
    buy_ts  = _parse_dt(request.args.get("buy_ts"))
    sell_ts = _parse_dt(request.args.get("sell_ts"))"""

new1 = """    ts      = _parse_dt(request.args.get("ts"))
    buy_ts  = _parse_dt(request.args.get("buy_ts"))
    sell_ts = _parse_dt(request.args.get("sell_ts"))

    def _parse_marks(raw):
        out = []
        for part in (raw or "").split("|"):
            d = _parse_dt(part)
            if d is not None:
                out.append(d)
        return out

    buy_marks = _parse_marks(request.args.get("buy_marks"))
    sell_marks = _parse_marks(request.args.get("sell_marks"))"""

if old1 not in txt:
    raise SystemExit("Block 1 not found")
txt = txt.replace(old1, new1, 1)

old2 = """        # Optional "ts" marker (yellow-ish label); does NOT break anything if absent
        if ts:
            t = _to_index_tz(ts)
            if t:
                ax.axvline(t, linewidth=2, alpha=0.8)
                ax.text(t, close.max(), " ALERT", va="top", ha="left", fontsize=10)"""

new2 = """        # Extra trigger marker lines
        for _bm in buy_marks:
            try:
                _t = _to_index_tz(_bm)
                if _t:
                    ax.axvline(_t, linewidth=1.3, alpha=0.55, linestyle="--")
            except Exception:
                pass

        for _sm in sell_marks:
            try:
                _t = _to_index_tz(_sm)
                if _t:
                    ax.axvline(_t, linewidth=1.3, alpha=0.55, linestyle="--")
            except Exception:
                pass

        # Optional "ts" marker; suppress it if it matches buy_ts
        if ts:
            _same_as_buy = False
            try:
                _same_as_buy = (buy_ts is not None and ts == buy_ts)
            except Exception:
                _same_as_buy = False
            if not _same_as_buy:
                t = _to_index_tz(ts)
                if t:
                    ax.axvline(t, linewidth=2, alpha=0.8)
                    ax.text(t, close.max(), " ALERT", va="top", ha="left", fontsize=10)"""

if old2 not in txt:
    raise SystemExit("Block 2 not found")
txt = txt.replace(old2, new2, 1)

P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_CHART_TRIGGER_LINES_V1")
