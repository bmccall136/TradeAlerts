# services/simulation_service.py

import csv, time, logging
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
from services.market_service import get_symbols
from services.etrade_service    import fetch_etrade_quote
from services.trading_helpers  import (
    buy_stock, sell_stock, get_position_qty,
    setup_simulation_db, set_cash, get_cash,
    insert_trade, insert_or_update_holding,
    compute_qty, seconds_until_open,
    check_exit_orders,
)
from services.settings_schema   import SimulationSettings
from services.indicators import (
    compute_sma, compute_rsi, compute_macd, compute_bollinger_bands,
    compute_volume_multiplier, compute_vwap, compute_atr,
    daily_range_pct, gap_up_pct
)

logger = logging.getLogger("sim")
ET   = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")

LOGFILE = Path("logs/triggers.csv")
LOGFILE.parent.mkdir(parents=True, exist_ok=True)

# services/simulation_service.py

from services.market_service import fetch_data_with_timeout  # or however you grab your bar data
from services.market_service    import get_symbols
# assume INDICATOR_COLUMNS and indicator_keys are defined here as per last message

def analyze_symbol(symbol, settings):
    """
    For a single symbol:
      1) fetch history
      2) compute each of your 11 boolean tests
      3) return (triggered_filters, passed_all_required)
    """
    # 1) figure out how many bars you need
    lookback = max(
        settings.atr_len,
        settings.bb_length,
        settings.macd_slow + settings.macd_signal,
        settings.rsi_len,
    )

    # 2) fetch the last `lookback` days of OHLCV
    history = fetch_data_with_timeout(symbol, f"{lookback}d")

    # 3) current price = last close
    price = float(history['Close'].iloc[-1])
    triggered = []

    # — BB breakout?
    if settings.bb_on:
        ub, mb, lb = compute_bollinger_bands(
            history['Close'], settings.bb_length, settings.bb_std
        )
        ub_, lb_ = float(ub.iat[-1]), float(lb.iat[-1])
        if price > ub_:
            triggered.append('BB breakout')

    # — MACD crossover?
    if settings.macd_on:
        macd_line, signal = compute_macd(
            history['Close'],
            settings.macd_fast,
            settings.macd_slow,
            settings.macd_signal
        )
        if float(macd_line.iat[-1]) > float(signal.iat[-1]):
            triggered.append('MACD 🚀')

    # — RSI overbought?
    if settings.rsi_on:
        rsi = compute_rsi(history['Close'], settings.rsi_len)
        if float(rsi.iat[-1]) > settings.rsi_overbought:
            triggered.append('RSI 📈')

    # — VWAP?
    if settings.vwap_on:
        vwap = compute_vwap(history)
        vwap_ = float(vwap.iat[-1]) if hasattr(vwap, 'iat') else float(vwap)
        if price >= vwap_:
            triggered.append('VWAP+ 💰')

    # — ATR absolute?
    if settings.atr_on:
        atr = compute_atr(history, settings.atr_len)
        if float(atr.iat[-1]) >= settings.atr_threshold:
            triggered.append(f'ATR{settings.atr_len} ≥ {settings.atr_threshold}')

    # — ATR %?
    if settings.atr_pct_on:
        atr = compute_atr(history, settings.atr_len)
        pct = float(atr.iat[-1]) / price * 100
        if pct >= settings.atr_pct:
            triggered.append(f'ATR % ≥ {settings.atr_pct}%')

    # — Range %?
    if settings.range_on:
        rng = daily_range_pct(history)
        if float(rng.iat[-1]) >= settings.range_pct:
            triggered.append(f'Range % ≥ {settings.range_pct}%')

    # — Gap %?
    if settings.gap_on:
        gap = gap_up_pct(history)
        if float(gap.iat[-1]) >= settings.gap_pct:
            triggered.append(f'Gap % ≥ {settings.gap_pct}%')

    # — Vol multiplier?
    if settings.vol_on:
        vm = compute_volume_multiplier(history, settings.vol_multiplier)
        if float(vm.iat[-1]) >= settings.vol_multiplier:
            triggered.append(f'Vol ×{settings.vol_multiplier}')

    # — Price > SMA?
    if settings.price_sma_on:
        sma = compute_sma(history['Close'], settings.sma_length)
        if price > float(sma.iat[-1]):
            triggered.append(f'Price > SMA{settings.sma_length}')

    # — (You can add news_on or other tests here) —

    # 5) check required toggles all fired
    required_flags = [
        'sma_on', 'rsi_on', 'macd_on', 'bb_on',
        'vol_on', 'vwap_on', 'atr_on', 'atr_pct_on',
        'range_on', 'gap_on', 'price_sma_on'
    ]
    flag_to_label = {
        'sma_on':        f'Price > SMA{settings.sma_length}',
        'rsi_on':        'RSI 📈',
        'macd_on':       'MACD 🚀',
        'bb_on':         'BB breakout',
        'vol_on':        f'Vol ×{settings.vol_multiplier}',
        'vwap_on':       'VWAP+ 💰',
        'atr_on':        f'ATR{settings.atr_len} ≥ {settings.atr_threshold}',
        'atr_pct_on':    f'ATR % ≥ {settings.atr_pct}%',
        'range_on':      f'Range % ≥ {settings.range_pct}%',
        'gap_on':        f'Gap % ≥ {settings.gap_pct}%',
        'price_sma_on':  f'Price > SMA{settings.sma_length}',
    }

    passed_all_required = True
    for flag in required_flags:
        if getattr(settings, flag):
            label = flag_to_label[flag]
            if label not in triggered:
                passed_all_required = False
                break

    return triggered, passed_all_required



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
    setup_simulation_db()
    if settings.nuke_db:
        setup_simulation_db()

    set_cash(settings.starting_cash)
    logger.info(f"[SIM] seed cash: ${get_cash():.2f}")

    symbols = get_symbols()  # make sure you have get_symbols imported
    # the 11 boolean columns your scan routine computes per symbol
    INDICATOR_COLUMNS = [
        "sma",        # simple moving average
        "rsi",        # relative strength index
        "macd",       # MACD crossover
        "bb",         # Bollinger Bands breakout
        "vol",        # volume spike
        "vwap",       # VWAP+
        "price_sma",  # price > SMA
        "atr",        # absolute ATR filter
        "atr_pct",    # ATR % filter
        "range",      # daily range % filter
        "gap"         # pre-market gap % filter
    ]

    # the 11 corresponding flags on your SimulationSettings dataclass
    indicator_keys = [
        "sma_on",
        "rsi_on",
        "macd_on",
        "bb_on",
        "vol_on",
        "vwap_on",
        "price_sma_on",
        "atr_on",
        "atr_pct_on",
        "range_on",
        "gap_on",
    ]

    total_enabled = sum(1 for k in indicator_keys if getattr(settings, k))
    threshold         = total_enabled

    if not LOGFILE.exists():
        with open(LOGFILE, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(["timestamp", "symbol"] + INDICATOR_COLUMNS + ["buy"])

    trade_log = []

    while True:
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        logger.info("🔁 Starting scan loop iteration")
        for sym in symbols:
            try:
                result = analyze_symbol(sym, settings)
            except ValueError as e:
                logger.error(f"[SIM] Error analyzing {sym}: {e}")
                continue
            if not result or "price" not in result:
                continue

            price    = result["price"]
            triggers = result.get("triggers", [])
            passed   = len(triggers)
            buy_flag = int(passed == total_enabled)

            flags = [int(col in triggers) for col in INDICATOR_COLUMNS]
            ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LOGFILE, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([ts, sym] + flags + [buy_flag])

            # always update last_price if we already hold it
            if get_position_qty(sym) > 0:
                insert_or_update_holding(sym, 0, get_avg_cost(sym), price)

            logger.info(f"[SIM] ALERT {sym} ({passed}/{total_enabled}) triggered : {triggers}")
            logger.info(f"[SIM] ALERT {sym} ({buy_flag}/1) required")

            if buy_flag == 0:
                continue
            if settings.single_entry_only and get_position_qty(sym) > 0:
                logger.info(f"⛔ Already holding {sym} — skipping re-entry")
                continue

            now_dt = datetime.utcnow()
            if wash_sale_prohibited(sym, now_dt, trade_log):
                logger.info(f"⛔ Skipping {sym} due to wash-sale rule")
                continue
            if funds_not_settled(sym, now_dt, trade_log):
                logger.info(f"⛔ Skipping {sym}: funds not yet settled")
                continue

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
                logger.error(f"❌ Failed to BUY {sym}: {e}")

            check_exit_orders(settings)

        if settings.poll_interval > 0:
            logger.info(f"⏸ Scan complete — sleeping {settings.poll_interval:.1f}s…")
            time.sleep(settings.poll_interval)

def stop_simulation():
    raise NotImplementedError("Your run loop is foreground; use CTRL-C.")
