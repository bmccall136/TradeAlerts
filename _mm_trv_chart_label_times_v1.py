import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_trv_chart_label_times_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """        # BUY/SELL vertical markers
        if buy_t:
            ax.axvline(buy_t, linewidth=2)
            ax.text(buy_t, close.min(), " BUY", va="bottom", ha="left", fontsize=10)
        if sell_t:
            ax.axvline(sell_t, linewidth=2)
            ax.text(sell_t, close.min(), " SELL", va="bottom", ha="left", fontsize=10)"""

new = """        # BUY/SELL vertical markers + timestamps
        def _fmt_lbl(dt_obj, tag):
            try:
                return f" {tag} {dt_obj.strftime('%H:%M:%S')}"
            except Exception:
                return f" {tag}"

        if buy_t:
            ax.axvline(buy_t, linewidth=2)
            ax.text(buy_t, close.min(), _fmt_lbl(buy_t, "BUY"), va="bottom", ha="left", fontsize=10)

        if sell_t:
            ax.axvline(sell_t, linewidth=2)
            ax.text(sell_t, close.min(), _fmt_lbl(sell_t, "SELL"), va="bottom", ha="left", fontsize=10)"""

if old not in txt:
    raise SystemExit("Target BUY/SELL marker block not found.")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_CHART_LABEL_TIMES_V1")
