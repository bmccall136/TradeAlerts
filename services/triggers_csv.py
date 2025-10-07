# C:\TradeAlerts\services\triggers_csv.py
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

# Fixed, “all columns” header (add more any time; file will include them)
FIELDS = [
    "ts_et",
    "symbol",
    "price",
    "signals",  # core
    "adx",
    "macd",
    "macd_signal",
    "macd_hist",
    "rsi",  # momentum
    "sma20",
    "sma50",
    "sma200",  # trend
    "bb_upper",
    "bb_lower",
    "atr",  # bands/volatility
    "volume",
    "avg_volume",
    "gap_pct",
    "day_chg_pct",  # tape/changes
    "rank",
    "score",
    "scanner",
    "notes",  # ranking/meta
]

LOG_DIR = Path(r"C:\TradeAlerts\logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _now_et_str() -> str:
    # ET without external deps
    # Naive but fine: EST/EDT shift isn’t critical to a minute-level log
    # If you prefer real ET: use zoneinfo("America/New_York")
    off = -4 if _is_dst_approx() else -5
    return (datetime.utcnow() + timedelta(hours=off)).strftime("%Y-%m-%d %H:%M:%S")


def _is_dst_approx():
    # Very loose: Mar–Oct as DST
    m = datetime.utcnow().month
    return 3 <= m <= 10


def _ensure_header(fp: Path):
    if not fp.exists() or fp.stat().st_size == 0:
        with fp.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(FIELDS)


def _write_row(fp: Path, row: dict):
    _ensure_header(fp)
    out = {k: "" for k in FIELDS}
    out.update(row)  # unknown keys are ignored; known keys fill columns
    with fp.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([out.get(k, "") for k in FIELDS])


def emit_trigger(
    *,
    symbol: str,
    price: float | int | str | None,
    signals: list[str] | str = "",
    indicators: dict | None = None,
    rank: int | None = None,
    score: float | None = None,
    scanner: str = "live",
    notes: str = "",
):
    """Append a fully-populated trigger row to daily file and latest pointer."""
    indicators = indicators or {}
    sig_str = (
        "; ".join(signals) if isinstance(signals, (list, tuple)) else str(signals or "")
    )

    row = {
        "ts_et": _now_et_str(),
        "symbol": str(symbol or "").upper(),
        "price": price if price is not None else "",
        "signals": sig_str,
        # pull safely from indicators map (use .get)
        "adx": indicators.get("adx"),
        "macd": indicators.get("macd"),
        "macd_signal": indicators.get("macd_signal"),
        "macd_hist": indicators.get("macd_hist"),
        "rsi": indicators.get("rsi"),
        "sma20": indicators.get("sma20"),
        "sma50": indicators.get("sma50"),
        "sma200": indicators.get("sma200"),
        "bb_upper": indicators.get("bb_upper"),
        "bb_lower": indicators.get("bb_lower"),
        "atr": indicators.get("atr"),
        "volume": indicators.get("volume"),
        "avg_volume": indicators.get("avg_volume"),
        "gap_pct": indicators.get("gap_pct"),
        "day_chg_pct": indicators.get("day_chg_pct"),
        "rank": rank,
        "score": score,
        "scanner": scanner,
        "notes": notes,
    }

    day = datetime.utcnow().strftime("%Y-%m-%d")
    daily = LOG_DIR / f"triggers_{day}.csv"
    latest = LOG_DIR / "triggers.csv"

    _write_row(daily, row)
    _write_row(latest, row)
