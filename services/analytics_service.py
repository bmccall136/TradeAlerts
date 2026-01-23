# services/analytics_service.py
from __future__ import annotations

import csv
import glob
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Dict, Any
from zoneinfo import ZoneInfo
from collections import Counter

ETZ = ZoneInfo("America/New_York")


def _safe_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _norm_trigger_family(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[\s\-\_\(\)\[\]\{\}\:\;,\>\<]+", "", s)
    if "macd" in s:
        return "macd"
    if "vwap" in s:
        return "vwap"
    if "adx" in s:
        return "adx"
    if "rsi" in s:
        return "rsi"
    if "bb" in s or "boll" in s:
        return "bb"
    if "vol" in s or "volume" in s:
        return "vol"
    if "sma" in s:
        return "sma"
    if "atr" in s:
        return "atr"
    return s or "(blank)"


def _split_signals(raw: str) -> List[str]:
    """
    Supports:
      - "MACD 🚀, VWAP"
      - "adx+macd+sma+vol+vwap" (combo form)
      - "['MACD','VWAP']"
    """
    if not raw:
        return []
    s = str(raw)
    s = s.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
    if "+" in s and "," not in s:
        parts = [p.strip() for p in s.split("+") if p.strip()]
    else:
        parts = [p.strip() for p in s.split(",") if p.strip()]
    return parts


def _hold_bucket(mins: float | None) -> str:
    if mins is None:
        return "(na)"
    if mins >= 24 * 60:
        return "1d+"
    if mins >= 60:
        return "60-1440"
    if mins >= 15:
        return "15-60"
    if mins >= 5:
        return "5-15"
    return "0-5"


def _pl_bucket(pct: float | None) -> str:
    if pct is None:
        return "(na)"
    # pct is a percent value, e.g. -0.25 means -0.25%
    if pct <= -3.0:
        return "≤ -3%"
    if pct <= -1.0:
        return "-3% to -1%"
    if pct < 0.0:
        return "-1% to 0%"
    if pct < 0.5:
        return "0% to 0.5%"
    if pct < 1.5:
        return "0.5% to 1.5%"
    if pct < 3.0:
        return "1.5% to 3%"
    return "≥ 3%"


@dataclass
class DailyAnalytics:
    et_date: str
    buy_file: str
    sell_file: str
    buy_rows: int
    sell_rows: int

    sell_actions: List[Tuple[str, int]]
    sell_reasons: List[Tuple[str, int]]

    buy_trigger_families: List[Tuple[str, int]]
    buy_trigger_combos: List[Tuple[str, int]]

    top_buy_symbols: List[Tuple[str, int]]
    top_sell_symbols: List[Tuple[str, int]]

    sell_hold_buckets: List[Tuple[str, int]]
    sell_pl_buckets: List[Tuple[str, int]]


def _newest_matching(paths: List[str]) -> str | None:
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return None
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths[0]


def find_today_logs(log_dir: str) -> Tuple[str | None, str | None, str]:
    """
    Returns (triggers_csv, sell_triggers_csv, et_date_str)
    Prefer today's dated file if present; otherwise fallback to newest.
    """
    now_et = datetime.now(ETZ)
    day = now_et.strftime("%Y-%m-%d")

    triggers_today = os.path.join(log_dir, f"triggers_{day}.csv")
    sell_today = os.path.join(log_dir, f"sell_triggers_{day}.csv")

    if os.path.exists(triggers_today) and os.path.exists(sell_today):
        return triggers_today, sell_today, day

    triggers_any = _newest_matching(
        glob.glob(os.path.join(log_dir, "triggers_*.csv")) + [os.path.join(log_dir, "triggers.csv")]
    )
    sell_any = _newest_matching(
        glob.glob(os.path.join(log_dir, "sell_triggers_*.csv")) + [os.path.join(log_dir, "sell_triggers.csv")]
    )

    guess = day
    for p in (sell_any, triggers_any):
        if p:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(p))
            if m:
                guess = m.group(1)
                break

    return triggers_any, sell_any, guess


def compute_daily_analytics(
    log_dir: str = r"C:\TradeAlerts\logs",
    max_rows: int = 0,
) -> DailyAnalytics:
    buy_path, sell_path, et_day = find_today_logs(log_dir)

    # BUY
    buy_rows = 0
    by_buy_symbol = Counter()
    by_buy_family = Counter()
    by_buy_combo = Counter()

    if buy_path and os.path.exists(buy_path):
        with open(buy_path, newline="", encoding="utf-8", errors="ignore") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []
            symk = next((k for k in cols if k.lower() in ("symbol", "sym", "ticker")), None)
            sigk = next((k for k in cols if "signals_pretty" in k.lower() or "signals" in k.lower()), None)

            for row in r:
                buy_rows += 1
                if max_rows and buy_rows >= max_rows:
                    break

                sym = ((row.get(symk) if symk else "") or "").strip().upper()
                if sym:
                    by_buy_symbol[sym] += 1

                raw = (row.get(sigk) if sigk else "") or ""
                parts = _split_signals(raw)

                fams = sorted({_norm_trigger_family(p) for p in parts if p.strip()})
                for fam in fams:
                    by_buy_family[fam] += 1
                if fams:
                    by_buy_combo["+".join(fams)] += 1

    # SELL
    sell_rows = 0
    by_sell_symbol = Counter()
    by_sell_action = Counter()
    by_sell_reason = Counter()
    by_hold_bucket = Counter()
    by_pl_bucket = Counter()

    if sell_path and os.path.exists(sell_path):
        with open(sell_path, newline="", encoding="utf-8", errors="ignore") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []

            symk = next((k for k in cols if k.lower() in ("symbol", "sym", "ticker")), None)
            actk = next((k for k in cols if k.lower() in ("action", "order_action", "orderaction")), None)
            reik = next((k for k in cols if k.lower() in ("reason", "event", "why")), None)
            holdk = next((k for k in cols if "hold" in k.lower()), None)
            plk = next((k for k in cols if "pl" in k.lower() and "pct" in k.lower()), None)

            for row in r:
                sell_rows += 1
                if max_rows and sell_rows >= max_rows:
                    break

                sym = ((row.get(symk) if symk else "") or "").strip().upper()
                if sym:
                    by_sell_symbol[sym] += 1

                act = ((row.get(actk) if actk else "") or "").strip().upper() or "UNKNOWN"
                by_sell_action[act] += 1

                reason = ((row.get(reik) if reik else "") or "").strip() or "(blank)"
                by_sell_reason[reason] += 1

                hold_min = _safe_float(row.get(holdk)) if holdk else None
                by_hold_bucket[_hold_bucket(hold_min)] += 1

                pl_pct = _safe_float(row.get(plk)) if plk else None
                by_pl_bucket[_pl_bucket(pl_pct)] += 1

    return DailyAnalytics(
        et_date=et_day,
        buy_file=buy_path or "",
        sell_file=sell_path or "",
        buy_rows=buy_rows,
        sell_rows=sell_rows,
        sell_actions=by_sell_action.most_common(12),
        sell_reasons=by_sell_reason.most_common(12),
        buy_trigger_families=by_buy_family.most_common(12),
        buy_trigger_combos=by_buy_combo.most_common(12),
        top_buy_symbols=by_buy_symbol.most_common(20),
        top_sell_symbols=by_sell_symbol.most_common(20),
        sell_hold_buckets=by_hold_bucket.most_common(12),
        sell_pl_buckets=by_pl_bucket.most_common(12),
    )


# =========================
# Charts feed (JSON)
# =========================

def _parse_iso_to_et(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        s = str(ts).strip()
        if s.endswith("Z"):
            s = s[:-1]
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # assume ET if naive
            dt = dt.replace(tzinfo=ETZ)
        return dt.astimezone(ETZ)
    except Exception:
        return None


def _bucket_5min(dt: datetime) -> str:
    m = (dt.minute // 5) * 5
    return dt.replace(minute=m, second=0, microsecond=0).strftime("%H:%M")


def compute_analytics_charts(
    log_dir: str = r"C:\TradeAlerts\logs",
) -> Dict[str, Any]:
    """
    Lightweight aggregates for Chart.js.
    - sell_over_time: counts per 5-min bucket
    - sell_exit_reasons: counts for exits only (filters loop/hold/watch)
    - buy_trigger_mix: trigger family counts
    """
    buy_path, sell_path, et_day = find_today_logs(log_dir)

    # SELL charts
    sell_over_time = Counter()
    sell_exit_reasons = Counter()

    if sell_path and os.path.exists(sell_path):
        with open(sell_path, newline="", encoding="utf-8", errors="ignore") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []

            timek = next((k for k in cols if k.lower() in ("time", "timestamp", "ts", "time_et")), None)
            reik = next((k for k in cols if k.lower() in ("reason", "event", "why")), None)

            for row in r:
                reason = ((row.get(reik) if reik else "") or "").strip().lower()

                # exits only for time series
                if reason and reason not in ("loop", "hold", "watch", "tick"):
                    dt = _parse_iso_to_et((row.get(timek) if timek else "") or "")
                    if dt:
                        sell_over_time[_bucket_5min(dt)] += 1

                reason = ((row.get(reik) if reik else "") or "").strip().lower()
                # exits only: ignore continuous watcher reasons
                if reason and reason not in ("loop", "hold", "watch", "tick"):
                    sell_exit_reasons[reason.upper()] += 1

    # BUY trigger mix chart
    buy_trigger_mix = Counter()

    if buy_path and os.path.exists(buy_path):
        with open(buy_path, newline="", encoding="utf-8", errors="ignore") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []
            sigk = next((k for k in cols if "signals_pretty" in k.lower() or "signals" in k.lower()), None)

            for row in r:
                raw = (row.get(sigk) if sigk else "") or ""
                parts = _split_signals(raw)
                for p in parts:
                    fam = _norm_trigger_family(p)
                    if fam and fam != "(blank)":
                        buy_trigger_mix[fam] += 1

    # Make ordered dicts for stable charts
    sell_over_time_sorted = {k: sell_over_time[k] for k in sorted(sell_over_time.keys())}
    sell_exit_reasons_sorted = dict(sell_exit_reasons.most_common(12))
    buy_trigger_mix_sorted = dict(buy_trigger_mix.most_common(12))

    return {
        "ok": True,
        "et_date": et_day,
        "sell_over_time": sell_over_time_sorted,
        "sell_exit_reasons": sell_exit_reasons_sorted,
        "buy_trigger_mix": buy_trigger_mix_sorted,
    }
