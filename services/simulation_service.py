# ── services/simulation_service.py ── at very top of file ──

import logging
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

from services.data_fetch import fetch_data_with_timeout, fetch_intraday_vwap
from services.indicators import (
    compute_sma, compute_rsi, compute_macd,
    compute_bollinger_bands, compute_volume_multiplier,
    compute_atr, compute_adx, compute_supertracker,
    daily_range_pct, gap_up_pct
)
from services.etrade_service import fetch_etrade_quote
from services.market_service import get_symbols
from services.settings_schema import SimulationSettings, SIM_DB_PATH
from services.trading_helpers import (
    setup_simulation_db, set_cash, get_cash,
    buy_stock, get_position_qty, compute_qty,
    seconds_until_open, check_exit_orders, get_holdings
)

import csv    # <— make sure csv is imported before use
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.utcnow().date().isoformat()             # e.g. "2025-07-31"
LOGFILE = Path(f"logs/triggers_{today}.csv")
LOGFILE.parent.mkdir(parents=True, exist_ok=True)
 
# on first run each day, write header
CSV_HEADER = [
    "timestamp", "symbol", "price",
    "ADX", "ATR_val", "ATR_pct",
    "SuperTracker_osc", "SuperTracker_sig",
    "signals"
]
if not LOGFILE.exists():
    with open(LOGFILE, "w", newline="") as f:
        csv.writer(f).writerow(CSV_HEADER)


logger = logging.getLogger("sim")
ET = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")

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
        if hasattr(history.columns, 'get_level_values'):
            history.columns = history.columns.get_level_values(0)
        history.columns = [c.lower() for c in history.columns]
        if 'close' not in history.columns or 'volume' not in history.columns:
            logger.error(f"{symbol}: missing expected columns {history.columns}")
            return None, [], False
    except Exception as e:
        logger.exception(f"{symbol}: error fetching history - {e}")
        return None, [], False

    # 2) Fetch live price (fallback to last close)
    try:
        quote = fetch_etrade_quote(symbol)
        price = float(quote.get('last_trade_price', quote.get('lastTradePrice', 0))) if isinstance(quote, dict) else float(quote)
    except Exception:
        price = float(history['close'].iat[-1])

    triggered: list[str] = []

    # ─── HARD-GATES + REQUIRED FILTERS ──────────────────────────
    adx = None
    if 'adx' in settings.required_filters:
        adx = compute_adx(history, settings.adx_len)
        if adx.iat[-1] < settings.adx_threshold:
            logger.debug(f"{symbol}: ADX {adx.iat[-1]:.2f} < required {settings.adx_threshold}")
            return price, triggered, False
        triggered.append(f"ADX ≥ {settings.adx_threshold}")
    elif settings.adx_on:
        adx = compute_adx(history, settings.adx_len)

    macd_line = macd_sig = None
    if 'macd' in settings.required_filters or settings.macd_on:
        macd_line, macd_sig = compute_macd(
            history, settings.macd_fast, settings.macd_slow, settings.macd_signal
        )
    if 'macd' in settings.required_filters:
        if macd_line.iat[-1] <= macd_sig.iat[-1]:
            logger.debug(f"{symbol}: MACD {macd_line.iat[-1]:.2f} ≤ {macd_sig.iat[-1]:.2f} required")
            return price, triggered, False
        triggered.append("MACD 🚀")

    osc = sig = None
    if 'super' in settings.required_filters or settings.super_on:
        osc, sig = compute_supertracker(
            history, settings.super_fast, settings.super_slow, settings.super_signal
        )
    if 'super' in settings.required_filters:
        if not (osc.iat[-1] > sig.iat[-1] and osc.iat[-1] > 0):
            logger.debug(f"{symbol}: SuperTracker {osc.iat[-1]:.2f}/{sig.iat[-1]:.2f} required")
            return price, triggered, False
        triggered.append("SuperTracker ↑")

    vwap = None
    if settings.vwap_on:
        try:
            vwap = fetch_intraday_vwap(symbol)
            logger.debug(f"{symbol}: fetched VWAP={vwap:.2f}")
        except Exception as e:
            msg = str(e)
            # only log truly unexpected errors
            if "Missing high in intraday data" not in msg:
                logger.debug(f"{symbol}: VWAP fetch failed: {e}")
            # fallback to historical VWAP
            try:
                vwap = compute_vwap(history)
                logger.debug(f"{symbol}: fallback VWAP={vwap:.2f}")
            except Exception:
                vwap = None
    if vwap is not None and price < vwap:
        logger.debug(f"{symbol}: price {price:.2f} < VWAP {vwap:.2f}")
        return price, triggered, False

    # ─── OPTIONAL SIGNALS ─────────────────────────────────────────────
    if settings.adx_on and adx is not None and f"ADX ≥ {settings.adx_threshold}" not in triggered:
        triggered.append(f"ADX ≥ {settings.adx_threshold}")

    if settings.macd_on and 'macd' not in settings.required_filters:
        macd_line, macd_sig = compute_macd(
            history, settings.macd_fast, settings.macd_slow, settings.macd_signal
        )
        if macd_line.iat[-1] > macd_sig.iat[-1]:
            triggered.append("MACD 🚀")

    if settings.vwap_on and vwap is not None:
        triggered.append("Price > VWAP")

    if settings.bb_on:
        ub, _, _ = compute_bollinger_bands(history['close'], settings.bb_length, settings.bb_std)
        if price > ub.iat[-1]:
            triggered.append("BB breakout")

    if settings.rsi_on:
        rsi = compute_rsi(history, settings.rsi_len)
        if rsi.iat[-1] > settings.rsi_overbought:
            triggered.append("RSI 📈")

    if settings.vol_on:
        vol_mul = compute_volume_multiplier(history, settings.vol_multiplier)
        if vol_mul.iat[-1] >= settings.vol_multiplier:
            triggered.append("Volume spike")

    if settings.atr_on:
        atr_val = compute_atr(history, settings.atr_len)
        if atr_val >= settings.atr_threshold:
            triggered.append(f"ATR{settings.atr_len} ≥ {settings.atr_threshold}")

    if settings.atr_pct_on:
        atr_val = compute_atr(history, settings.atr_len)
        if (atr_val / price * 100) >= settings.atr_pct:
            triggered.append(f"ATR % ≥ {settings.atr_pct}%")

    if settings.range_on and daily_range_pct(history) >= settings.range_pct:
        triggered.append(f"Range % ≥ {settings.range_pct}")

    if settings.gap_on and gap_up_pct(history) >= settings.gap_pct:
        triggered.append(f"Gap % ≥ {settings.gap_pct}")

    if settings.price_sma_on:
        sma_val = compute_sma(history['close'], settings.price_sma_len)
        if price > sma_val:
            triggered.append(f"Price > SMA{settings.price_sma_len}")

    # ─── FINAL PASS/FAIL ─────────────────────────────
    passed = len(triggered) >= settings.min_signals

    # ─── LOG TO CSV ON PASS ──────────────────────────
    if passed:
        # compute ATR values for logging
        atr_val = compute_atr(history, settings.atr_len) if (settings.atr_on or settings.atr_pct_on) else None
        atr_pct = (atr_val / price * 100) if atr_val else None
        # SuperTracker values (if enabled)
        osc_last = osc.iat[-1] if ("osc" in locals() and osc is not None) else None
        sig_last = sig.iat[-1] if ("sig" in locals() and sig is not None) else None

        with open(LOGFILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.utcnow().isoformat(),
                symbol,
                f"{price:.2f}",
                f"{adx.iat[-1]:.2f}" if adx is not None else "",
                f"{atr_val:.2f}"     if atr_val    is not None else "",
                f"{atr_pct:.2f}"     if atr_pct    is not None else "",
                f"{osc_last:.2f}"    if osc_last   is not None else "",
                f"{sig_last:.2f}"    if sig_last   is not None else "",
                ";".join(triggered),
            ])
    # ─── ALWAYS RETURN at the end ──────────────────────────
    return price, triggered, passed

from datetime import datetime
from zoneinfo import ZoneInfo

ET   = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")
now_dt = datetime.utcnow()

def _is_market_open():
    # grab “now” in New York
    now_et = datetime.now(ET)
    today  = now_et.date()

    # what NYSE thinks today’s hours are
    sched = nyse.schedule(start_date=today, end_date=today)
    if sched.empty:
        logger.debug(f"[MARKET] No session today ({today})")
        return False

    # these come back as pandas.Timestamp (tz=America/New_York)
    open_dt  = sched.iloc[0].market_open.to_pydatetime()
    close_dt = sched.iloc[0].market_close.to_pydatetime()

    # debug output—verify all three in your logs
    logger.debug(
        f"[MARKET] now_et   = {now_et!r}\n"
        f"          open_dt  = {open_dt!r}\n"
        f"          close_dt = {close_dt!r}"
    )

    return open_dt <= now_et <= close_dt
from datetime import datetime
import time
import logging
from services.trading_helpers import (
    get_cash, get_position_qty, compute_qty,
    buy_stock, seconds_until_open, check_exit_orders, get_holdings
)
from services.market_service import get_symbols
from services.simulation_service import analyze_symbol, _is_market_open

from datetime import datetime
import time
import logging
from services.trading_helpers import (
    get_cash,
    get_position_qty,
    compute_qty,
    buy_stock,
    seconds_until_open,
    check_exit_orders,
    get_holdings
)
from services.market_service import get_symbols
from services.simulation_service import analyze_symbol, _is_market_open

logger = logging.getLogger("sim")

def run_simulation_loop(settings: SimulationSettings):
    # ── seed logic ──
    try:
        current = get_cash()
    except:
        current = 0.0

    if settings.nuke_db or current == 0.0:
        setup_simulation_db()
        set_cash(settings.starting_cash)
        logger.info(f"[SIM] seed cash: ${get_cash():.2f}")
    else:
        logger.info(f"[SIM] continuing with cash = ${get_cash():.2f}")

    # grab our symbol universe once
    symbols = get_symbols(simulation=True)

    # ── main scanning loop ──
    while True:
        logger.info("🔁 Starting scan loop iteration")

        # a) wait if market closed
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        # b) reset candidate list each pass
        candidates: list[tuple[str, float, list[str]]] = []
        # c) scan symbols & collect the ones that pass
        for sym in symbols:
            # skip if already in a position (single‐entry logic)
            if settings.single_entry_only and get_position_qty(sym) > 0:
                continue

            price, triggered, passed = analyze_symbol(sym, settings)
            if not passed:
                continue

            logger.info(f"[SIM] ALERT {sym}: {len(triggered)}/{settings.min_signals} → {triggered}")
            candidates.append((sym, price, triggered))

        # 4) sort and attempt buy
        if candidates:
            candidates.sort(key=lambda x: len(x[2]), reverse=True)
            purchased = False

            for sym, price, triggered in candidates:
                qty = compute_qty(settings, price)
                cost = qty * price
                cash = get_cash()

                if qty < 1 or cost > cash:
                    logger.info(f"[SIM] Candidate {sym} skipped (qty={qty}, cost=${cost:.2f}, cash=${cash:.2f})")
                    continue

                # buy top affordable
                logger.info(f"[SIM] TOP PICK {sym}: {len(triggered)} signals → {triggered}")
                buy_stock(sym, qty, price, datetime.utcnow())
                logger.info(f"✅ BUY {sym} x{qty} @ ${price:.2f} (cash → ${get_cash():.2f})")
                purchased = True
                break

            if not purchased:
                logger.info("[SIM] No affordable candidates this round")
        else:
            logger.info("[SIM] no candidates this round")

        # 5) handle exits
        check_exit_orders(settings)

        # 6) log holdings
        holdings = get_holdings()
        if holdings:
            logger.info("[SIM] Current holdings:")
            for s, q, avg, lp in holdings:
                logger.info(f"    • {s}: {q} shares @ ${avg:.2f} (last price: ${lp:.2f})")
        else:
            logger.info("[SIM] No holdings")

        # 7) sleep
        logger.info(f"[SIM] Sleeping {settings.poll_interval:.1f}s before next scan")
        time.sleep(settings.poll_interval)
def stop_simulation():
    raise NotImplementedError("Foreground loop; use CTRL‑C to stop")
