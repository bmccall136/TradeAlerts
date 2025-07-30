# services/simulation_service.py

import csv
import time
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from services.data_fetch import fetch_data_with_timeout, fetch_intraday_vwap

import pandas as pd
import pandas_market_calendars as mcal
from services.market_service     import get_symbols
from services.data_fetch    import fetch_data_with_timeout
from services.etrade_service     import fetch_etrade_quote
from services.settings_schema   import SimulationSettings
from services.trading_helpers import (
    buy_stock, get_position_qty, setup_simulation_db,
    set_cash, get_cash, insert_or_update_holding,
    compute_qty, seconds_until_open, check_exit_orders,
    get_avg_cost, get_holdings, check_if_position_open
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
    # 0) Determine how many days of history we need
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

        # Flatten & lowercase columns
        if isinstance(history.columns, pd.MultiIndex):
            history.columns = history.columns.get_level_values(0)
        history.columns = [c.lower() for c in history.columns]

        if 'close' not in history.columns or 'volume' not in history.columns:
            logger.error(f"{symbol}: missing expected columns {history.columns.tolist()}")
            return None, [], False

    except Exception as e:
        logger.exception(f"{symbol}: error fetching/parsing history - {e}")
        return None, [], False

    # 2) Calculate intraday VWAP
    try:
        vwap = fetch_intraday_vwap(symbol)
    except Exception as e:
        logger.error(f"{symbol}: failed to fetch VWAP ({e}); skipping VWAP filter")
        vwap = None

     # 3) Fetch live price (fallback to history close)
    try:
        quote = fetch_etrade_quote(symbol)
        if isinstance(quote, dict):
            price = float(quote.get("last_trade_price", quote.get("lastTradePrice", 0)))
        else:
            price = float(quote)
    except Exception:
        price = float(history["close"].iat[-1])

    # ─── initialize our signal list (must come before any .append) ──
    triggered = []

    # now that price is guaranteed to exist and triggered is a list:
    logger.debug(f"{symbol}: final price = {price}")

    logger.debug(f"{symbol}: final price = {price}")

    # ─── initialize the list of signals ───────────────────────────
    triggered = []

    # 4) VWAP filter
    if settings.vwap_on and vwap is not None:
        if price < vwap:
            # below VWAP → immediate fail
            logger.debug(f"{symbol}: price {price:.2f} < VWAP {vwap:.2f}; skipping")
            return price, triggered, False
        triggered.append("Price > VWAP")
    # 5) Bollinger Bands
    if settings.bb_on:
        ub, _, _ = compute_bollinger_bands(history["close"], settings.bb_length, settings.bb_std)
        if price > ub.iat[-1]:
            triggered.append("BB breakout")

    # 6) MACD
    if settings.macd_on:
        macd_line, signal = compute_macd(
            history, settings.macd_fast, settings.macd_slow, settings.macd_signal
        )
        if macd_line.iat[-1] > signal.iat[-1]:
            triggered.append("MACD 🚀")

    # 7) RSI
    if settings.rsi_on:
        rsi = compute_rsi(history, settings.rsi_len)
        if rsi.iat[-1] > settings.rsi_overbought:
            triggered.append("RSI 📈")

    # 8) Volume spike
    if settings.vol_on:
        vol_mul = compute_volume_multiplier(history, settings.vol_multiplier)
        if vol_mul.iat[-1] >= settings.vol_multiplier:
            triggered.append("Volume spike")

    # 9) ATR absolute & percentage
    if settings.atr_on or settings.atr_pct_on:
        atr = compute_atr(history, settings.atr_len)
        if settings.atr_on and atr >= settings.atr_threshold:
            triggered.append(f"ATR{settings.atr_len} ≥ {settings.atr_threshold}")
        if settings.atr_pct_on and (atr / price * 100) >= settings.atr_pct:
            triggered.append(f"ATR % ≥ {settings.atr_pct}%")

    # 10) Range, Gap, SMA, etc.
    if settings.range_on and daily_range_pct(history) >= settings.range_pct:
        triggered.append(f"Range % ≥ {settings.range_pct}")
    if settings.gap_on and gap_up_pct(history) >= settings.gap_pct:
        triggered.append(f"Gap % ≥ {settings.gap_pct}")
    if settings.price_sma_on:
        sma = compute_sma(history["close"], settings.sma_length)
        if price > sma:
            triggered.append(f"Price > SMA{settings.sma_length}")

    # 11) Final pass/fail
    # after you compute VWAP, BB, SMA, etc. — format ub/sma safely
    try:
        ub_val  = ub.iat[-1]  if hasattr(ub, "iat")  else float(ub)
    except Exception:
        ub_val = None
    try:
        sma_val = sma.iat[-1] if hasattr(sma, "iat") else float(sma)
    except Exception:
        sma_val = None
    logger.debug(
        f"{symbol}: price={price:.2f}, VWAP={vwap}, "
        f"UB={ub_val}, SMA{settings.sma_length}={sma_val}, triggered={triggered}"
    )
    passed = len(triggered) >= settings.min_signals
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
    logger.info(f"[SIM] seed cash: ${get_cash():.2f}")
    symbols = get_symbols(simulation=True)

    while True:
        # 1) pause if market closed
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        logger.info("🔁 Starting scan loop iteration")

        # 2) reset candidate list
        candidates: list[tuple[str, float, list[str]]] = []

        # 3) scan symbols & collect passed ones
        for sym in symbols:
            # skip if in position and single-entry-only
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
