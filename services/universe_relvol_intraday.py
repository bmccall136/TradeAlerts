import yfinance as yf
import pandas as pd
from datetime import datetime

PRICE_MIN = 5
PRICE_MAX = 150
RELVOL_MIN = 1.8
TOP_N = 200


def build_relvol_universe(symbols):

    rows = []
    now = datetime.now()

    for i, sym in enumerate(symbols, 1):

        if i % 25 == 0:
            print(f"[relvol_intraday] processed {i}/{len(symbols)}")

        try:

            df = yf.download(
                sym,
                period="5d",
                interval="1m",
                progress=False,
                auto_adjust=False,
                threads=False
            )

            if df is None or len(df) < 50:
                continue

            df = df.reset_index()

            df["date"] = df["Datetime"].dt.date
            df["time"] = df["Datetime"].dt.time

            today = df["date"].max()

            today_df = df[df["date"] == today]
            prev_df = df[df["date"] < today]

            if len(today_df) == 0:
                continue

            # volume so far today
            vol_today = today_df["Volume"].sum()

            # previous days volume up to same time
            cutoff = today_df["Datetime"].max().time()

            prev_df = prev_df[prev_df["time"] <= cutoff]

            if len(prev_df) == 0:
                continue

            avg_vol = prev_df.groupby("date")["Volume"].sum().mean()

            relvol = vol_today / avg_vol if avg_vol else 0

            price = today_df["Close"].iloc[-1]

            if price < PRICE_MIN or price > PRICE_MAX:
                continue

            if relvol >= RELVOL_MIN:
                rows.append((sym, relvol))

        except Exception:
            continue

    rows.sort(key=lambda x: x[1], reverse=True)

    return [sym for sym, _ in rows[:TOP_N]]