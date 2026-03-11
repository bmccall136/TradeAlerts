import yfinance as yf
import pandas as pd
from datetime import datetime

PRICE_MIN = 5
PRICE_MAX = 150
RELVOL_MIN = 1.2
TOP_N = 200

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    try:
        if isinstance(df.columns, pd.MultiIndex):
            cols = []
            for c in df.columns:
                parts = [str(x) for x in c if str(x) != "" and str(x).lower() != "nan"]
                cols.append("_".join(parts))
            df.columns = cols
    except Exception:
        pass
    return df

def _pick_col(df: pd.DataFrame, candidates):
    cols = list(df.columns)
    low = {str(c).lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in low:
            return low[cand.lower()]
    for c in cols:
        sc = str(c).lower()
        for cand in candidates:
            if cand.lower() in sc:
                return c
    return None

def build_relvol_universe(symbols):
    rows = []
    now = datetime.now()

    stats = {
        "total": 0,
        "download_empty": 0,
        "too_short": 0,
        "no_today": 0,
        "no_prev": 0,
        "bad_price": 0,
        "below_relvol": 0,
        "exceptions": 0,
        "accepted": 0,
    }

    for i, sym in enumerate(symbols, 1):
        stats["total"] += 1

        if i % 25 == 0:
            print(f"[relvol_intraday] processed {i}/{len(symbols)}")

        try:
            sym = str(sym).strip().upper()
            if not sym:
                continue

            df = yf.download(
                sym,
                period="5d",
                interval="1m",
                progress=False,
                auto_adjust=False,
                threads=False
            )

            if df is None or len(df) == 0:
                stats["download_empty"] += 1
                continue

            df = _flatten_columns(df)

            if len(df) < 50:
                stats["too_short"] += 1
                continue

            df = df.reset_index()

            dt_col = _pick_col(df, ["Datetime", "Date"])
            vol_col = _pick_col(df, ["Volume"])
            close_col = _pick_col(df, ["Close"])

            if not dt_col or not vol_col or not close_col:
                stats["exceptions"] += 1
                continue

            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
            df[vol_col] = pd.to_numeric(df[vol_col], errors="coerce")
            df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
            df = df.dropna(subset=[dt_col, vol_col, close_col])

            if len(df) < 50:
                stats["too_short"] += 1
                continue

            df["date"] = df[dt_col].dt.date
            df["time"] = df[dt_col].dt.time

            today = df["date"].max()
            today_df = df[df["date"] == today].copy()
            prev_df = df[df["date"] < today].copy()

            if len(today_df) == 0:
                stats["no_today"] += 1
                continue

            cutoff = today_df[dt_col].max().time()
            prev_df = prev_df[prev_df["time"] <= cutoff]

            if len(prev_df) == 0:
                stats["no_prev"] += 1
                continue

            vol_today = float(today_df[vol_col].sum())
            avg_vol = float(prev_df.groupby("date")[vol_col].sum().mean() or 0.0)
            relvol = (vol_today / avg_vol) if avg_vol > 0 else 0.0

            price = float(today_df[close_col].iloc[-1])

            if price < PRICE_MIN or price > PRICE_MAX:
                stats["bad_price"] += 1
                continue

            if relvol >= RELVOL_MIN:
                rows.append((sym, relvol))
                stats["accepted"] += 1
            else:
                stats["below_relvol"] += 1

        except Exception:
            stats["exceptions"] += 1
            continue

    rows.sort(key=lambda x: x[1], reverse=True)
    out = [sym for sym, _ in rows[:TOP_N]]

    print("[relvol_intraday] summary:", stats)
    print(f"[relvol_intraday] final_count={len(out)} head={out[:25]}")
    return out
