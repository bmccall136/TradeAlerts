# services/simulation_service.py

import csv
import time
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

from services.market_service    import fetch_data_with_timeout, get_symbols
from services.etrade_service     import fetch_etrade_quote
from services.settings_schema   import SimulationSettings
from services.trading_helpers   import (
    buy_stock, get_position_qty, setup_simulation_db,
    set_cash, get_cash, insert_or_update_holding,
    compute_qty, seconds_until_open, check_exit_orders,
    get_avg_cost
)
from services.indicators        import (
    compute_sma, compute_rsi, compute_macd,
    compute_bollinger_bands, compute_volume_multiplier,
    compute_vwap, compute_atr,
    daily_range_pct, gap_up_pct
)

logger = logging.getLogger("sim")
ET   = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")

LOGFILE = Path("logs/triggers.csv")
LOGFILE.parent.mkdir(parents=True, exist_ok=True)


def analyze_symbol(symbol: str, settings: SimulationSettings):
    lookback = max(
        settings.atr_len,
        settings.bb_length,
        settings.macd_slow + settings.macd_signal,
        settings.rsi_len,
    )

    # 1) Fetch history (for indicators)…
    try:
        history = fetch_data_with_timeout(symbol, f"{lookback}d")
        if history is None or history.empty:
            logger.warning(f"No data for {symbol}; skipping")
            return None, [], False

        # 1) Flatten to drop symbol level if MultiIndex
        if isinstance(history.columns, pd.MultiIndex):
            history.columns = history.columns.get_level_values(0)

        # 2) Lowercase all column names
        history.columns = [c.lower() for c in history.columns]

        # 3) Require 'close' and 'volume'
        if 'close' not in history.columns or 'volume' not in history.columns:
            logger.error(f"{symbol}: missing expected columns; got {history.columns.tolist()}")
            return None, [], False

    except Exception as e:
        logger.exception(f"{symbol}: error fetching/parsing history - {e}")
        return None, [], False
     
    # 2) Always pull live price from E*TRADE (fallback to history close)
    try:
        logger.debug(f"{symbol}: calling fetch_etrade_quote()")
        quote = fetch_etrade_quote(symbol)
        logger.debug(f"{symbol}: fetch_etrade_quote returned → {quote!r}")

        if isinstance(quote, dict):
            price = float(quote.get("last_trade_price", quote.get("lastTradePrice", 0)))
        else:
            price = float(quote)
    except Exception as e:
        logger.error(f"{symbol}: failed to fetch E*TRADE quote ({e}), using history close")
        price = float(history["close"].iat[-1])

    logger.debug(f"{symbol}: final price = {price}")

    # 4) Run your indicator tests
    triggered = []

    if settings.bb_on:
        ub, _, _ = compute_bollinger_bands(history["close"], settings.bb_length, settings.bb_std)
        if price > ub.iat[-1]:
            triggered.append("BB breakout")

    if settings.macd_on:
        macd_line, signal = compute_macd(
            history, settings.macd_fast, settings.macd_slow, settings.macd_signal
        )
        if macd_line.iat[-1] > signal.iat[-1]:
            triggered.append("MACD 🚀")

    if settings.rsi_on:
        rsi = compute_rsi(history, settings.rsi_len)
        if rsi.iat[-1] > settings.rsi_overbought:
            triggered.append("RSI 📈")

    if settings.vol_on:
        vol_mul = compute_volume_multiplier(history, settings.vol_multiplier)
        # pick the most recent volume multiplier
        current_vol = vol_mul.iloc[-1]
        if current_vol >= settings.vol_multiplier:
            triggered.append('volume Spike')

    if settings.atr_on:
        atr = compute_atr(history, settings.atr_len)
        if atr >= settings.atr_threshold:
            triggered.append(f"ATR{settings.atr_len} ≥ {settings.atr_threshold}")

    if settings.atr_pct_on:
        atr = compute_atr(history, settings.atr_len)
        if (atr / price * 100) >= settings.atr_pct:
            triggered.append(f"ATR % ≥ {settings.atr_pct}%")

    if settings.range_on:
        rng = daily_range_pct(history)
        if rng >= settings.range_pct:
            triggered.append(f"Range % ≥ {settings.range_pct}")

    if settings.gap_on:
        gap = gap_up_pct(history)
        if gap >= settings.gap_pct:
            triggered.append(f"Gap % ≥ {settings.gap_pct}")

    if settings.price_sma_on:
        sma = compute_sma(history["close"], settings.sma_length)
        if price > sma:
            triggered.append(f"Price > SMA{settings.sma_length}")

    # 5) Ensure all enabled toggles fired
    # pass if we hit at least min_signals triggers
    passed_all = len(triggered) >= settings.min_signals
    return price, triggered, passed_all

def _is_market_open():
    today = datetime.now(ET).date()
    sched = nyse.schedule(start_date=today, end_date=today)
    if sched.empty:
        return False
    open_t  = sched.iloc[0].market_open.time()
    close_t = sched.iloc[0].market_close.time()
    now_t   = datetime.now(ET).time()
    return open_t <= now_t <= close_t


def run_simulation_loop(settings: SimulationSettings):
    # Only rebuild & reseed if the user explicitly requested it
    if settings.nuke_db:
        setup_simulation_db()
        set_cash(settings.starting_cash)
        logger.info(f"[SIM] seed cash: ${get_cash():.2f}")

    # …now pick up from whatever state was in the DB…
    symbols = get_symbols(simulation=True)
    TRIGGER_LABELS = [
        f"Price > SMA{settings.sma_length}",
        "RSI 📈", "MACD 🚀", "BB breakout",
        f"Vol ×{settings.vol_multiplier}", "VWAP+ 💰",
        f"ATR{settings.atr_len} ≥ {settings.atr_threshold}",
        f"ATR % ≥ {settings.atr_pct}%",
        f"Range % ≥ {settings.range_pct}",
        f"Gap % ≥ {settings.gap_pct}",
    ]
    total_enabled = sum(getattr(settings, k) for k in [
        "price_sma_on","rsi_on","macd_on","bb_on",
        "vol_on","vwap_on","atr_on","atr_pct_on",
        "range_on","gap_on",
    ])

    if not LOGFILE.exists():
        with open(LOGFILE, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(["timestamp","symbol"] + TRIGGER_LABELS + ["buy"])

    trade_log = []

    while True:
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        logger.info("Starting scan loop iteration")

        for sym in symbols:
            price, triggered, passed = analyze_symbol(sym, settings)
            # now buy if we met the minimum‐signals threshold
            buy_flag = int(passed and len(triggered) >= settings.min_signals)
            flags    = [int(lbl in triggered) for lbl in TRIGGER_LABELS]

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LOGFILE, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([ts, sym] + flags + [buy_flag])

            if get_position_qty(sym) > 0:
                insert_or_update_holding(
                    sym, qty=0,
                    avg_cost=get_avg_cost(sym),
                    last_price=price
                )

            logger.info(f"[SIM] ALERT {sym} ({len(triggered)}/{total_enabled}) -> {triggered}")
            logger.info(f"[SIM] ALERT {sym} ({buy_flag}/1) required")

            if not buy_flag:
                continue
            if settings.single_entry_only and get_position_qty(sym) > 0:
                logger.info(f"⛔ Already holding {sym}; skipping")
                continue

            now_dt = datetime.utcnow()
            # … your wash‑sale & settlement checks here …

            qty  = compute_qty(settings, price)
            cost = qty * price
            if qty < 1 or cost > get_cash():
                logger.info(f"[SKIP] {sym} cost ${cost:.2f} vs cash ${get_cash():.2f}")
                continue

            try:
                buy_stock(sym, qty, price, now_dt)
                trade_log.append({"symbol": sym, "action": "BUY", "time": now_dt})
                logger.info(f"✅ BUY {sym} x{qty} @ ${price:.2f}")
            except Exception as e:
                logger.error(f"❌ BUY failed for {sym}: {e}")

            check_exit_orders(settings)

        if settings.poll_interval > 0:
            logger.info(f"⏸ Scan complete — sleeping {settings.poll_interval:.1f}s")
            time.sleep(settings.poll_interval)


def stop_simulation():
    raise NotImplementedError("Foreground loop; use CTRL‑C to stop")
