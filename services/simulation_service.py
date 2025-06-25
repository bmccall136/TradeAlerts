import time
import logging
from datetime import datetime
from pathlib import Path

from services.etrade_service import fetch_etrade_quote
from services.market_service import fetch_data_with_timeout
from services.trading_helpers import (
    set_cash,
    buy_stock,
    sell_stock,
    get_cash,
    nuke_simulation_db
)
import logging

logger = logging.getLogger('sim')

# ── control flag & stop fn ─────────────────────────────────────
_sim_stop = False

def stop_simulation():
    """Signal the running simulation loop to exit on next iteration."""
    global _sim_stop
    _sim_stop = True

# ── helpers ─────────────────────────────────────────────────────

def load_symbols():
    """Load the list of symbols from your SP500 file."""
    p = Path(__file__).parent.parent / "sp500_symbols.txt"
    return [s.strip() for s in p.read_text().splitlines() if s.strip()]

def calculate_qty(settings, data):
    """
    Turn max_per_trade into whole‐share qty based on latest price.
    Expects `data['price']` to be the live price.
    """
    try:
        price   = float(data.get("price") if isinstance(data, dict) else getattr(data, "price", 0))
        max_amt = float(settings.max_per_trade)
        if price <= 0:
            return 0
        qty = int(max_amt // price)
        return max(qty, 1)
    except Exception as e:
        logging.error(f"[sim] calculate_qty error: {e}")
        return 1

def evaluate_exit(pos, settings):
    """
    Return True if any exit condition fires:
     - trailing‐stop
     - sell_after_days
    """
    price = pos.get("price", 0)
    # ─ trailing stop ─
    if getattr(settings, 'use_trailing_stop', False):
        peak = pos.get("peak_price", price)
        if price <= peak * (1 - settings.trailing_stop_pct):
            return True

    # ─ time‐based exit ─
    entry = pos.get("entry_time")
    if getattr(settings, 'sell_after_days', None) and entry:
        if (datetime.utcnow() - entry).days >= settings.sell_after_days:
            return True

    return False

# ── main simulation loop ───────────────────────────────────────

def run_simulation_loop(settings):
    logger.info(f"[sim] starting run with settings={settings}")
    nuke_simulation_db()
    set_cash(settings.starting_cash)
    logger.info(f"[sim] seed cash: {get_cash():.2f}")

    positions = {}
    symbols   = load_symbols()
    while not _sim_stop:

        for sym in symbols:
            # 1) live price
            try:
                price_live = float(fetch_etrade_quote(sym))
            except Exception as e:
                logger.warning(f"[sim] {sym}: price fetch failed ({e})")
                continue

            # 2) pull 1d/1m bars once (for all indicators)
            df = None
            if settings.sma_on or settings.rsi_on or settings.bb_on:
                df = fetch_data_with_timeout(sym, period='1d', interval='1m')
                if df is None or df.empty:
                    logger.warning(f"[sim] {sym}: no market data for indicators")
                    continue

            decisions = []
            reasons   = []

            # 3a) SMA cross-above
            if settings.sma_on:
                sma = df['Close'].rolling(settings.sma_length).mean().iloc[-1]
                ok  = price_live > sma
                decisions.append(ok)
                reasons.append(f"SMA({settings.sma_length}) pass? {ok}")
            
             # 3b) RSI oversold-cross
            if settings.rsi_on:
                delta      = df['Close'].diff()
                up         = delta.clip(lower=0)
                down       = -delta.clip(upper=0)
                roll_up    = up.ewm(span=settings.rsi_len).mean()
                roll_down  = down.ewm(span=settings.rsi_len).mean()
                rs         = roll_up / roll_down
                rsi_series = 100 - (100 / (1 + rs))
                latest_rsi = float(rsi_series.iloc[-1])   # scalar
                ok         = latest_rsi < settings.rsi_oversold
                decisions.append(ok)
                reasons.append(f"RSI({settings.rsi_len})={latest_rsi:.1f} pass? {ok}")


            # 3c) Bollinger Band breakout
            if settings.bb_on:
                mb    = df['Close'].rolling(settings.bb_length).mean().iloc[-1]
                std   = df['Close'].rolling(settings.bb_length).std().iloc[-1]
                upper = mb + settings.bb_std * std
                ok    = price_live > upper
                decisions.append(ok)
                reasons.append(f"BB upper={upper:.2f} pass? {ok}")

            # 3d) VWAP (you already have this)
            if settings.vwap_on:
                vol = df['Volume']
                tp  = (df['High'] + df['Low'] + df['Close']) / 3
                vwap_ser = (tp * vol).cumsum() / vol.cumsum()
                latest_vwap = vwap_ser.iloc[-1]
                ok = (price_live - latest_vwap) > settings.vwap_threshold
                # right before “if not all(decisions): …”
                logger.debug(f"[sim] {sym}  decisions={decisions}  reasons={reasons}")
                decisions.append(ok)
                vwap_scalar = float(latest_vwap.iloc[0]) if isinstance(latest_vwap, pd.Series) else float(latest_vwap)
                reasons.append(f"VWAP={vwap_scalar:.2f} pass? {ok}")

            # 3e) single-entry guard
            if settings.single_entry_only and sym in positions:
                logger.debug(f"[sim] {sym} already in positions")
                continue

            # DEBUG: dump decisions & reasons
            logger.debug(f"[sim] {sym}: decisions={decisions}  reasons={reasons}")

            # if no filters at all, skip
            if not decisions:
                logger.debug(f"[sim] {sym}: no filters enabled, skipping buy")
                continue

            # 4) only buy if *all* pass
            decisions = [
                (d.iloc[0] if hasattr(d, 'iloc') else d)
                for d in decisions
            ]
            if not all(decisions):
                continue


            # … then do your buy …

            # 5) calculate qty & BUY
            qty = calculate_qty(settings, {"price": price_live})
            if qty <= 0:
                logger.debug(f"[sim] {sym}: qty=0, skipping")
                continue
            try:
                buy_stock(sym, qty, price_live)
                logger.info(f"BUY  {sym} x{qty} @ {price_live:.2f}")
                positions[sym] = {
                    "entry_time": datetime.utcnow(),
                    "qty":        qty,
                    "peak_price": price_live,
                    "price":      price_live
                }
            except ValueError as e:
                logger.warning(f"[sim] skip BUY {sym}: {e}")

        # ── EXIT pass ──
        for sym, pos in list(positions.items()):
            # fetch live…
            price_live = float(fetch_etrade_quote(sym))
            pos["price"] = price_live
            # update peak
            if price_live > pos["peak_price"]:
                pos["peak_price"] = price_live

            # log for trailing-stop
            if evaluate_exit(pos, settings):
                try:
                    sell_stock(sym, pos["qty"], price_live)
                    logger.info(f"SELL {sym} x{pos['qty']} @ {price_live:.2f}")
                except ValueError as e:
                    logger.warning(f"[sim] skip SELL {sym}: {e}")
                positions.pop(sym)

        time.sleep(getattr(settings, 'poll_interval', 60))