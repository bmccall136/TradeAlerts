# ── services/simulation_service.py ── at very top of file ──

import csv  # <— make sure csv is imported before use
import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from services.data_fetch import fetch_data_with_timeout, fetch_intraday_vwap
from services.etrade_service import fetch_etrade_quote
from services.indicators import (
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_supertracker,
    compute_volume_multiplier,
    daily_range_pct,
    gap_up_pct,
)
from services.market_service import get_symbols
from services.settings_schema import SimulationSettings
from services.trading_helpers import buy_stock as enter_trade
from services.trading_helpers import (
    check_exit_orders,
    compute_qty,
    get_cash,
    get_holdings,
    get_position_qty,
    get_trades,
    seconds_until_open,
    set_cash,
    setup_simulation_db,
)

# --- CSV logging setup (Excel-friendly) ---
today = datetime.utcnow().date().isoformat()
LOGFILE = Path(f"logs/triggers_{today}.csv")
LOGFILE.parent.mkdir(parents=True, exist_ok=True)

# Canonical trigger keys -> column names
TRIGGERS = {
    "ADX_REQ": "ADX_req",
    "MACD_UP": "MACD_up",
    "SUPER_UP": "Super_up",
    "VWAP_PLUS": "VWAP_plus",
    "BB_BREAKOUT": "BB_breakout",
    "RSI_OVERBOUGHT": "RSI_overbought",
    "VOL_SPIKE": "Vol_spike",
    "ATR_ABS": "ATR_ge",
    "ATR_PCT": "ATRpct_ge",
    "RANGE_PCT": "Range_ge",
    "GAP_PCT": "Gap_ge",
    "PRICE_GT_SMA": "Price_gt_SMA",
}

CSV_HEADER = [
    "timestamp",
    "symbol",
    "price",
    "ADX",
    "ATR_val",
    "ATR_pct",
    "SuperTracker_osc",
    "SuperTracker_sig",
    *TRIGGERS.values(),  # one-hot columns
    "signals",  # ASCII, semicolon-separated
]

# Create file with BOM so Excel reads UTF-8 correctly
if not LOGFILE.exists():
    with open(LOGFILE, "w", newline="", encoding="utf-8-sig") as f:
        import csv

        csv.writer(f).writerow(CSV_HEADER)


logger = logging.getLogger("sim")
ET = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")
import json
from pathlib import Path


def _canonize_triggers(triggered: list[str]) -> set[str]:
    """
    Map the human/emoji strings in `triggered` to canonical keys used in TRIGGERS.
    Keeps this tolerant to minor wording differences.
    """
    keys = set()
    for t in triggered:
        t = (t or "").lower()
        if "adx" in t:
            keys.add("ADX_REQ")
        if "macd" in t:
            keys.add("MACD_UP")
        if "super" in t:
            keys.add("SUPER_UP")
        if "vwap" in t:
            keys.add("VWAP_PLUS")
        if "bb breakout" in t or "bb" in t:
            keys.add("BB_BREAKOUT")
        if "rsi" in t:
            keys.add("RSI_OVERBOUGHT")
        if "volume" in t:
            keys.add("VOL_SPIKE")
        if "atr %" in t or "atr % ≥" in t:
            keys.add("ATR_PCT")
        # plain ATR (absolute) — try to avoid double-counting with ATR%
        if "atr" in t and "atr %" not in t:
            keys.add("ATR_ABS")
        if "range %" in t:
            keys.add("RANGE_PCT")
        if "gap %" in t:
            keys.add("GAP_PCT")
        if "price > sma" in t:
            keys.add("PRICE_GT_SMA")
        if "price > vwap" in t:
            keys.add("VWAP_PLUS")
    return keys


# services/simulation_service.py
from dataclasses import asdict  # optional helper below
from pathlib import Path

# This is the ONLY place we touch the JSON file on disk.
_SIM_CONFIG_FILE = Path(__file__).parent.parent / "simulation_config.json"


def load_simulation_settings() -> SimulationSettings:
    """
    Load simulation_config.json and return a SimulationSettings object.
    Missing file or bad JSON → return defaults.
    """
    try:
        with open(_SIM_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f) or {}
    except FileNotFoundError:
        data = {}
    except Exception:
        # malformed JSON, etc.
        data = {}
    return SimulationSettings(**data)


# (optional) Handy helper if a dict is more convenient in templates
def settings_as_dict() -> dict:
    return asdict(load_simulation_settings())


def analyze_symbol(symbol: str, settings: SimulationSettings):
    # 0) Determine lookback
    lookback = max(
        settings.atr_len,
        settings.bb_length,
        settings.macd_slow + settings.macd_signal,
        settings.rsi_len,
    )

    # 1) Fetch history
    try:
        history = fetch_data_with_timeout(symbol, f"{lookback}d")
        if history is None or history.empty:
            logger.warning(f"No data for {symbol}; skipping")
            return None, [], False
        if hasattr(history.columns, "get_level_values"):
            history.columns = history.columns.get_level_values(0)
        history.columns = [c.lower() for c in history.columns]
        if "close" not in history.columns or "volume" not in history.columns:
            logger.error(f"{symbol}: missing expected columns {history.columns}")
            return None, [], False
    except Exception as e:
        logger.exception(f"{symbol}: error fetching history - {e}")
        return None, [], False

    # 2) Fetch live price (fallback to last close)
    try:
        quote = fetch_etrade_quote(symbol)
        price = (
            float(quote.get("last_trade_price", quote.get("lastTradePrice", 0)))
            if isinstance(quote, dict)
            else float(quote)
        )
    except Exception:
        price = float(history["close"].iat[-1])

    triggered: list[str] = []

    # ─── HARD-GATES + REQUIRED FILTERS ──────────────────────────
    triggered = list(triggered)  # ensure it's a mutable list

    # --- ADX ---
    adx_v = None
    if ("adx" in settings.required_filters) or settings.adx_on:
        adx_series = compute_adx(history, settings.adx_len)
        adx_v = float(adx_series.iat[-1])
        if adx_v >= settings.adx_threshold:
            # use threshold label to match your downstream string checks
            if f"ADX ≥ {settings.adx_threshold}" not in triggered:
                triggered.append(f"ADX ≥ {settings.adx_threshold}")

    # --- MACD ---
    macd_line_v = macd_sig_v = None
    if ("macd" in settings.required_filters) or settings.macd_on:
        macd_line, macd_sig = compute_macd(
            history, settings.macd_fast, settings.macd_slow, settings.macd_signal
        )
        macd_line_v = float(macd_line.iat[-1])
        macd_sig_v = float(macd_sig.iat[-1])
        if macd_line_v > macd_sig_v:
            # keep your original label for compatibility
            if "MACD 🚀" not in triggered:
                triggered.append("MACD 🚀")

    # --- SuperTracker (if you use it) ---
    osc_v = sig_v = None
    if ("super" in settings.required_filters) or getattr(settings, "super_on", False):
        osc, sig = compute_supertracker(
            history, settings.super_fast, settings.super_slow, settings.super_signal
        )
        osc_v = float(osc.iat[-1])
        sig_v = float(sig.iat[-1])
        if (osc_v > sig_v) and (osc_v > 0):
            if "SuperTracker ↑" not in triggered:
                triggered.append("SuperTracker ↑")

    # --- VWAP (soft signal) ---
    vwap = None
    if getattr(settings, "vwap_on", False):
        try:
            vwap = fetch_intraday_vwap(symbol)
            logger.debug(f"{symbol}: fetched VWAP={vwap:.2f}")
        except Exception as e:
            msg = str(e)
            if "Missing high in intraday data" not in msg:
                logger.debug(f"{symbol}: VWAP fetch failed: {e}")
            try:
                vwap_series = compute_vwap(history)
                vwap = (
                    float(vwap_series)
                    if not hasattr(vwap_series, "iat")
                    else float(vwap_series.iat[-1])
                )
                logger.debug(f"{symbol}: fallback VWAP={vwap:.2f}")
            except Exception:
                vwap = None
        if (vwap is not None) and (price is not None) and (price >= vwap):
            if "Price>VWAP" not in triggered:
                triggered.append("Price>VWAP")

    # --- Bollinger breakout ---
    if getattr(settings, "bb_on", False):
        ub, _, _ = compute_bollinger_bands(
            history["close"], settings.bb_length, settings.bb_std
        )
        if price is not None and price > float(ub.iat[-1]):
            if "BB breakout" not in triggered:
                triggered.append("BB breakout")

    # --- RSI overbought (your original intent) ---
    if getattr(settings, "rsi_on", False):
        rsi = compute_rsi(history, settings.rsi_len)
        if float(rsi.iat[-1]) > settings.rsi_overbought:
            if "RSI 📈" not in triggered:
                triggered.append("RSI 📈")

    # --- Volume spike ---
    if getattr(settings, "vol_on", False):
        vol_mul_series = compute_volume_multiplier(history, settings.vol_multiplier)
        if float(vol_mul_series.iat[-1]) >= settings.vol_multiplier:
            if "Volume spike" not in triggered:
                triggered.append("Volume spike")

    # --- ATR absolute ---
    if getattr(settings, "atr_on", False):
        atr_series = compute_atr(history, settings.atr_len)
        atr_v = (
            float(atr_series.iat[-1])
            if hasattr(atr_series, "iat")
            else float(atr_series)
        )
        if atr_v >= settings.atr_threshold:
            lab = f"ATR{settings.atr_len} ≥ {settings.atr_threshold}"
            if lab not in triggered:
                triggered.append(lab)

    # --- ATR percent ---
    if getattr(settings, "atr_pct_on", False):
        atr_series = compute_atr(history, settings.atr_len)
        atr_v = (
            float(atr_series.iat[-1])
            if hasattr(atr_series, "iat")
            else float(atr_series)
        )
        if price and (atr_v / price * 100.0) >= settings.atr_pct:
            lab = f"ATR % ≥ {settings.atr_pct}%"
            if lab not in triggered:
                triggered.append(lab)

    # --- Range / Gap ---
    if (
        getattr(settings, "range_on", False)
        and daily_range_pct(history) >= settings.range_pct
    ):
        lab = f"Range % ≥ {settings.range_pct}"
        if lab not in triggered:
            triggered.append(lab)
    if getattr(settings, "gap_on", False) and gap_up_pct(history) >= settings.gap_pct:
        lab = f"Gap % ≥ {settings.gap_pct}"
        if lab not in triggered:
            triggered.append(lab)

    # --- Price > SMA(N) generic ---
    if getattr(settings, "price_sma_on", False):
        smaN = compute_sma(history["close"], settings.price_sma_len)
        smaN_v = float(smaN.iat[-1]) if hasattr(smaN, "iat") else float(smaN)
        if price is not None and price > smaN_v:
            lab = f"Price > SMA{settings.price_sma_len}"
            if lab not in triggered:
                triggered.append(lab)

    # --- Price > SMA20 (explicit, for require_sma20 and your tags) ---
    sma20_v = None
    if getattr(settings, "require_sma20", True) or getattr(settings, "sma_on", False):
        sma20 = compute_sma(history["close"], 20)
        sma20_v = float(sma20.iat[-1]) if hasattr(sma20, "iat") else float(sma20)
        if price is not None and price > sma20_v:
            if "Price>SMA20" not in triggered:
                triggered.append("Price>SMA20")

    # ─── FINAL PASS/FAIL ─────────────────────────────
    req = set(getattr(settings, "required_filters", []))  # e.g., {'adx','macd','super'}
    need_adx = "adx" in req
    need_macd = "macd" in req
    need_super = "super" in req

    meets_reqs = (
        (not need_adx or (adx_v is not None and adx_v >= settings.adx_threshold))
        and (
            not need_macd
            or (
                macd_line_v is not None
                and macd_sig_v is not None
                and macd_line_v > macd_sig_v
            )
        )
        and (
            not need_super
            or (osc_v is not None and sig_v is not None and osc_v > sig_v and osc_v > 0)
        )
    )

    sma20_ok = not getattr(settings, "require_sma20", True) or (
        sma20_v is not None and price is not None and price > sma20_v
    )
    min_signals = int(getattr(settings, "min_signals", 2))

    passed = (len(triggered) >= min_signals) and meets_reqs and sma20_ok
    return price, triggered, passed

    # ─── LOG TO CSV ON PASS ──────────────────────────
    if passed:
        # numeric fields (safe if toggles are off)
        atr_val = (
            compute_atr(history, settings.atr_len)
            if (settings.atr_on or settings.atr_pct_on)
            else None
        )
        atr_pct = (atr_val / price * 100) if atr_val else None
        osc_last = osc.iat[-1] if (locals().get("osc") is not None) else None
        sig_last = sig.iat[-1] if (locals().get("sig") is not None) else None

        # one-hot vector from current `triggered` strings
        trig_keys = _canonize_triggers(triggered)
        one_hot = [1 if k in trig_keys else 0 for k in TRIGGERS.keys()]

        # ASCII signals (avoid emojis/≥)
        ascii_labels = []
        if "ADX_REQ" in trig_keys:
            ascii_labels.append("ADX>=thresh")
        if "MACD_UP" in trig_keys:
            ascii_labels.append("MACD_cross_up")
        if "SUPER_UP" in trig_keys:
            ascii_labels.append("Super_up")
        if "VWAP_PLUS" in trig_keys:
            ascii_labels.append("Price>VWAP")
        if "BB_BREAKOUT" in trig_keys:
            ascii_labels.append("BB_breakout")
        if "RSI_OVERBOUGHT" in trig_keys:
            ascii_labels.append("RSI_overbought")
        if "VOL_SPIKE" in trig_keys:
            ascii_labels.append("Vol_spike")
        if "ATR_ABS" in trig_keys:
            ascii_labels.append("ATR>=abs")
        if "ATR_PCT" in trig_keys:
            ascii_labels.append("ATR>=pct")
        if "RANGE_PCT" in trig_keys:
            ascii_labels.append("Range>=pct")
        if "GAP_PCT" in trig_keys:
            ascii_labels.append("Gap>=pct")
        if "PRICE_GT_SMA" in trig_keys:
            ascii_labels.append(f"Price>SMA{getattr(settings, 'price_sma_len', 20)}")

        row = [
            datetime.utcnow().isoformat(),
            symbol,
            f"{price:.2f}",
            f"{adx.iat[-1]:.2f}" if locals().get("adx") is not None else "",
            f"{atr_val:.2f}" if atr_val is not None else "",
            f"{atr_pct:.2f}" if atr_pct is not None else "",
            f"{osc_last:.2f}" if osc_last is not None else "",
            f"{sig_last:.2f}" if sig_last is not None else "",
            *one_hot,
            ";".join(ascii_labels),
        ]

        # Always append with BOM to keep Excel happy
        with open(LOGFILE, "a", newline="", encoding="utf-8-sig") as f:
            import csv

            csv.writer(f).writerow(row)


from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")
now_dt = datetime.utcnow()


def _is_market_open():
    # grab “now” in New York
    now_et = datetime.now(ET)
    today = now_et.date()

    # what NYSE thinks today’s hours are
    sched = nyse.schedule(start_date=today, end_date=today)
    if sched.empty:
        logger.debug(f"[MARKET] No session today ({today})")
        return False

    # these come back as pandas.Timestamp (tz=America/New_York)
    open_dt = sched.iloc[0].market_open.to_pydatetime()
    close_dt = sched.iloc[0].market_close.to_pydatetime()

    # debug output—verify all three in your logs
    logger.debug(
        f"[MARKET] now_et   = {now_et!r}\n"
        f"          open_dt  = {open_dt!r}\n"
        f"          close_dt = {close_dt!r}"
    )

    return open_dt <= now_et <= close_dt


import logging
from datetime import UTC, datetime

from services.simulation_service import _is_market_open, analyze_symbol

logger = logging.getLogger("sim")
from types import SimpleNamespace

# Load settings early with a safe fallback
try:
    from services.simulation_service import load_simulation_settings

    settings = load_simulation_settings()
except Exception as e:
    print(f"[SIM] settings load failed: {e}")
    settings = SimpleNamespace(starting_cash=1000.0)


def run_simulation_loop(settings: SimulationSettings):
    from datetime import datetime

    setup_simulation_db()
    try:
        current = get_cash()
    except Exception:
        current = 0.0

    if settings.nuke_db or current == 0.0:
        setup_simulation_db()
        set_cash(settings.starting_cash)
        logger.info(f"[SIM] seed cash: ${get_cash():.2f}")
    else:
        logger.info(f"[SIM] continuing with cash = ${get_cash():.2f}")

    symbols = get_symbols(simulation=True)

    while True:
        # ─── Market hours check ──────────────────────────────
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        logger.info("🔁 Starting scan loop iteration")

        # reset per pass
        candidates: list[tuple[str, float, list[str]]] = []

        # gates once per pass (BEFORE the loop)
        strict_signals = getattr(settings, "strict_buy_signals", 4)
        require_sma20 = getattr(settings, "require_sma20", True)
        req = set(getattr(settings, "required_filters", []))  # e.g., {'adx','macd'}

        stats = {
            "analyzed": 0,
            "price_ok": 0,
            "tokenized": 0,
            "met_sig": 0,
            "met_sma": 0,
            "met_req": 0,
            "candidates": 0,
        }

        for sym in symbols:
            stats["analyzed"] += 1

            if (
                getattr(settings, "single_entry_only", False)
                and get_position_qty(sym) > 0
            ):
                continue

            try:
                res = analyze_symbol(sym, settings)
            except Exception as e:
                logger.exception(f"{sym}: analyze_symbol crashed — {e}")
                continue

            if not res or not isinstance(res, (tuple, list)) or len(res) != 3:
                logger.debug(f"{sym}: analyze_symbol returned {res!r}; skipping")
                continue

            price, triggered, _ = res
            if price is None:
                logger.debug(f"{sym}: price is None; skipping")
                continue
            stats["price_ok"] += 1

            tokens = [(t or "").replace(" ", "").lower() for t in (triggered or [])]
            stats["tokenized"] += 1
            sig_count = len(tokens)

            has_sma20 = any("price>sma20" in t or "price>sma(20)" in t for t in tokens)
            has_adx = any(t.startswith("adx") or "adx>=" in t for t in tokens)
            has_macd = any("macd" in t for t in tokens)
            meets_reqs = ("adx" not in req or has_adx) and (
                "macd" not in req or has_macd
            )

            if sig_count >= strict_signals:
                stats["met_sig"] += 1
            if not require_sma20 or has_sma20:
                stats["met_sma"] += 1
            if meets_reqs:
                stats["met_req"] += 1

            if (
                (sig_count >= strict_signals)
                and (not require_sma20 or has_sma20)
                and meets_reqs
            ):
                logger.info(
                    f"[SIM] ALERT {sym}: {sig_count}/{strict_signals} → {triggered}"
                )
                candidates.append((sym, float(price), list(triggered)))
                stats["candidates"] += 1
            else:
                logger.info(
                    f"[SIM] Skip {sym}: sc={sig_count} need>={strict_signals} "
                    f"sma20_req={require_sma20} has_sma20={has_sma20} "
                    f"need_adx={'adx' in req} has_adx={has_adx} "
                    f"need_macd={'macd' in req} has_macd={has_macd} "
                    f"trigs={triggered}"
                )

        # one-line summary for this pass
        logger.info(
            f"[SIM] pass stats: analyzed={stats['analyzed']} price_ok={stats['price_ok']} "
            f"tokenized={stats['tokenized']} met_sig={stats['met_sig']} "
            f"met_sma={stats['met_sma']} met_req={stats['met_req']} candidates={stats['candidates']}"
        )

        # ---------- RISK-AWARE BUY SECTION ----------
        if candidates:
            # 1) Promote your tuple list into a scoring dict
            #    candidates: list[ (sym, price, triggered) ]
            candidates_meta = {}
            for sym, price, triggered in candidates:
                tokens = [(t or "").replace(" ", "").lower() for t in (triggered or [])]
                meta = {
                    "price": float(price),
                    "signals_matched": len(tokens),
                    # optional nudges if you want to enrich later:
                    # "vol_spike": 0.0, "macd_hist": 0.0, "vwap_diff": 0.0,
                }
                candidates_meta[sym] = meta

            # 2) Scoring: heavy weight on signals_matched; slight nudge for higher price
            def _score_candidate(sym, meta):
                return meta.get("signals_matched", 0) * 10 + (
                    meta.get("price", 0.0) * 0.01
                )

            ranked = sorted(
                [
                    (sym, _score_candidate(sym, meta), meta)
                    for sym, meta in candidates_meta.items()
                ],
                key=lambda x: x[1],
                reverse=True,
            )

            # 3) Pull current cash/holdings/trade history once
            cash_now = get_cash()
            holdingsL = {
                s: {"qty": q, "avg_cost": ac, "last_price": lp}
                for s, q, ac, lp in get_holdings()
            }
            trade_log = get_trades(10000)  # plenty to reconstruct last buys

            # pyramiding rules (tweak to taste)
            pyramid_rules = {
                "max_adds": 2,  # after initial entry
                "min_add_interval_s": 300,  # 5 min between adds
                "min_add_distance_pct": 1.0,  # add only if >= +1% from last fill
                "max_position_qty": 999999,  # hard cap
                "t_plus_settlement_days": 2,  # soft T+2 using first buy time
            }

            # helpers from local data (don’t hit DB repeatedly)
            from datetime import datetime, timedelta

            def _get_buy_events(sym):
                ev = []
                for t in trade_log or []:
                    if (t.get("symbol") == sym) and (
                        str(t.get("action", "")).upper() == "BUY"
                    ):
                        # 'trade_time' is ISO; make it aware
                        ts = t.get("trade_time")
                        try:
                            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=UTC)
                        except Exception:
                            dt = datetime.now(UTC)
                        ev.append(
                            {
                                "time": dt,
                                "price": float(t.get("price") or 0.0),
                                "qty": int(float(t.get("qty") or 0)),
                            }
                        )
                # oldest first
                return sorted(ev, key=lambda e: e["time"])

            def _pyramid_ok(sym, price, qty, rules):
                pos = holdingsL.get(
                    sym, {"qty": 0, "avg_cost": None, "last_price": None}
                )
                buys = _get_buy_events(sym)
                reasons = []

                # cash
                if (cash_now - price * qty) < 1.00:
                    reasons.append("cash")

                # no prior buys → first entry always OK (skip add-specific checks)
                if not buys:
                    # still respect position qty cap
                    if qty > rules["max_position_qty"]:
                        reasons.append("max_qty")
                    return (len(reasons) == 0), reasons

                # derive add stats from buy history
                adds = max(len(buys) - 1, 0)
                last_fill_px = buys[-1]["price"]
                first_buy_dt = buys[0]["time"]
                last_add_dt = buys[-1]["time"]

                # max adds
                if adds >= rules["max_adds"]:
                    reasons.append("max_adds")

                # cooldown
                since = (datetime.now(UTC) - last_add_dt).total_seconds()
                if since < rules["min_add_interval_s"]:
                    reasons.append("cooldown")

                # min distance from last fill
                min_px = last_fill_px * (1 + rules["min_add_distance_pct"] / 100.0)
                if price < min_px:
                    reasons.append("distance")

                # soft T+2 from first entry if you want to simulate cash-settlement behavior
                if rules.get("t_plus_settlement_days", 0) > 0:
                    earliest_next = first_buy_dt + timedelta(
                        days=rules["t_plus_settlement_days"]
                    )
                    if (
                        datetime.now(UTC) < earliest_next
                        and pos.get("qty", 0) > 0
                    ):
                        reasons.append("t+2")

                # position cap
                if (pos.get("qty", 0) + qty) > rules["max_position_qty"]:
                    reasons.append("max_qty")

                return (len(reasons) == 0), reasons

            # 4) Walk the ranked list; buy the first one that passes gates
            purchased = False
            for sym, score, meta in ranked:
                price = float(meta["price"])
                # sanity: require your strict signals again
                trigs = next((t for (s, p, t) in candidates if s == sym), [])
                sig_count = len(trigs)
                if sig_count < strict_signals:
                    logger.info(
                        f"[SIM] Skip {sym}: only {sig_count}/{strict_signals} signals after rank"
                    )
                    continue

                qty = compute_qty(settings, price)
                if qty < 1:
                    logger.info(f"[SIM] Skip {sym}: qty calc < 1 at price={price:.2f}")
                    continue

                ok, why = _pyramid_ok(sym, price, qty, pyramid_rules)
                if not ok:
                    logger.info(f"[SIM] Blocked {sym} by pyramiding: {','.join(why)}")
                    continue

                try:
                    ok_trd = enter_trade(sym, qty, price)
                    if ok_trd is False:
                        logger.warning(f"[SIM] ❌ enter_trade returned False for {sym}")
                        continue
                    logger.info(
                        f"[SIM] ✅ BUY {sym} x{qty} @ {price:.2f} (score={score:.2f}, sigs={sig_count})"
                    )
                    purchased = True
                    break
                except Exception as e:
                    logger.exception(f"[SIM] BUY failed for {sym}: {e}")

            if not purchased:
                logger.info(
                    "[SIM] ranked selection found no purchasable candidates (all gated)"
                )
        else:
            logger.info("[SIM] no candidates this round")

        # ---- rest of your loop unchanged ----
        logger.debug("[CHECK-EXITS] Entered check_exit_orders()")
        check_exit_orders(settings)
        holdings = get_holdings()
        logger.debug(f"[CHECK-EXITS] Holdings: {holdings}")
        if holdings:
            logger.info("[SIM] Current holdings:")
            for s, q, avg, lp in holdings:
                logger.info(
                    f"    • {s}: {q} shares @ ${avg:.2f} (last price: ${lp:.2f})"
                )
        else:
            logger.info("[SIM] No holdings")
        logger.info(f"[SIM] Sleeping {settings.poll_interval:.1f}s before next scan")
        time.sleep(settings.poll_interval)


def stop_simulation():
    raise NotImplementedError("Foreground loop; use CTRL‑C to stop")
