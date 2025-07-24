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
from services.trading_helpers import (
    buy_stock, get_position_qty, setup_simulation_db,
    set_cash, get_cash, insert_or_update_holding,
    compute_qty, seconds_until_open, check_exit_orders,
    get_avg_cost, get_holdings
)
from services.indicators        import (
    compute_sma, compute_rsi, compute_macd,
    compute_bollinger_bands, compute_volume_multiplier,
    compute_vwap, compute_atr,
    daily_range_pct, gap_up_pct
)
from .settings_schema import SIM_DB_PATH, SimulationSettings

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
def run_simulation_loop(settings: SimulationSettings):
    logger.info(f"[SIM] seed cash: ${get_cash():.2f}")

    symbols = get_symbols(simulation=True)

    while True:
        # 1) pause if closed
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        logger.info("🔁 Starting scan loop iteration")

        # 2) iterate universe
        for sym in symbols:
            # a) indicator pass/fail
            hist_price, triggered, passed = analyze_symbol(sym, settings)
            if not (passed and len(triggered) >= settings.min_signals):
                continue
            logger.info(f"[SIM] ALERT {sym}: {len(triggered)}/{settings.min_signals} → {triggered}")

            # b) fetch live quote & timestamp
            now_dt = datetime.utcnow()
            live_px = fetch_etrade_quote(sym)
            logger.debug(f"[MARKET] {sym}: E*TRADE price = {live_px}")
            if not live_px or live_px <= 0:
                continue

            # — keep holdings’ last_price up‑to‑date only for positions we already own —
            from services.trading_helpers import insert_or_update_holding, get_position_qty, get_avg_cost
            if get_position_qty(sym) > 0:
                insert_or_update_holding(
                    symbol=sym,
                    qty=0,                      # no change in share count
                    avg_cost=get_avg_cost(sym), # leave avg cost untouched
                    last_price=live_px          # overwrite only the price
                )

            # c) compute size & cost
            qty  = compute_qty(settings, live_px)
            cost = qty * live_px
            if qty < 1 or cost > get_cash():
                logger.info(f"[SIM] insufficient cash for {sym}: need ${cost:.2f}, have ${get_cash():.2f}")
                continue

            # d) execute buy
            try:
                buy_stock(sym, qty, live_px, now_dt)
                set_cash(get_cash() - cost)
                logger.info(f"✅ BUY {sym} x{qty} @ ${live_px:.2f} (cash → ${get_cash():.2f})")
            except Exception as e:
                logger.error(f"❌ Failed to BUY {sym}: {e}")

            # e) handle exits immediately after
            check_exit_orders(settings)

            # f) log holdings
            holdings = get_holdings()
            if holdings:
                logger.info("[SIM] Current holdings:")
                for s, q, avg_cost, last_price in holdings:
                    logger.info(f"    • {s}: {q} shares @ ${avg_cost:.2f} (last price: ${last_price:.2f})")
            else:
                logger.info("[SIM] No holdings")

def stop_simulation():
    raise NotImplementedError("Foreground loop; use CTRL‑C to stop")
