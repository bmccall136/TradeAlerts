# services/universe_relvol.py

import yfinance as yf

PRICE_MIN = 5
PRICE_MAX = 150
RELVOL_MIN = 1.8
TOP_N = 200


def build_relvol_universe(symbols):
    rows = []

    for i, sym in enumerate(symbols, 1):
        if i % 25 == 0:
            print(f"[relvol] processed {i}/{len(symbols)}")

        try:
            df = yf.download(
                sym,
                period="6d",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False
            )

            if df is None or len(df) < 5:
                continue

            avg_vol = df["Volume"][:-1].mean()
            today_vol = df["Volume"].iloc[-1]
            relvol = today_vol / avg_vol if avg_vol else 0
            price = df["Close"].iloc[-1]

            if price < PRICE_MIN or price > PRICE_MAX:
                continue

            if relvol >= RELVOL_MIN:
                rows.append((sym, relvol))

        except Exception:
            continue

    rows.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in rows[:TOP_N]]