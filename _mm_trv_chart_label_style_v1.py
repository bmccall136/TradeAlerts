import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_trv_chart_label_style_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """        if buy_t:
            ax.axvline(buy_t, linewidth=2)
            ax.text(buy_t, close.min(), _fmt_lbl(buy_t, "BUY"), va="bottom", ha="left", fontsize=10)

        if sell_t:
            ax.axvline(sell_t, linewidth=2)
            ax.text(sell_t, close.min(), _fmt_lbl(sell_t, "SELL"), va="bottom", ha="left", fontsize=10)"""

new = """        if buy_t:
            ax.axvline(buy_t, linewidth=2)
            ax.text(
                buy_t, close.min(), _fmt_lbl(buy_t, "BUY"),
                va="bottom", ha="left", fontsize=10, color="#7CFFB2",
                bbox=dict(boxstyle="round,pad=0.20", facecolor="#0b0b0b", edgecolor="none", alpha=0.85)
            )

        if sell_t:
            ax.axvline(sell_t, linewidth=2)
            ax.text(
                sell_t, close.min(), _fmt_lbl(sell_t, "SELL"),
                va="bottom", ha="left", fontsize=10, color="#FF9A9A",
                bbox=dict(boxstyle="round,pad=0.20", facecolor="#0b0b0b", edgecolor="none", alpha=0.85)
            )"""

if old not in txt:
    raise SystemExit("Target BUY/SELL label block not found.")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_CHART_LABEL_STYLE_V1")
