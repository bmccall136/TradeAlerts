from __future__ import annotations
import time
import logging
from datetime import datetime, timezone, timedelta
from services import live_guardrails as lg
from services.broker import get_broker
from services.simulation_service import analyze_symbol, _is_market_open, seconds_until_open
from services.market_service import get_symbols
from services.trading_helpers import compute_qty, get_trades, get_holdings, get_cash

lg.start_guardrails_auto_seller()
logger = logging.getLogger("live")

def run_live_loop(settings, broker_mode: str = "SIM", picks: int = 1):
    broker = get_broker(broker_mode)
    symbols = get_symbols(simulation=True)

    strict_signals = getattr(settings, 'strict_buy_signals', 4)
    require_sma20  = getattr(settings, 'require_sma20', True)
    req            = set(getattr(settings, 'required_filters', []))  # e.g. {'adx','macd'}

    while True:
        # Market hours check
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[LIVE] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        logger.info("[LIVE] 🔁 Starting scan loop iteration")
        candidates = []  # (sym, price, triggered)

        # Scan pass
        for sym in symbols:
            try:
                price, triggered, passed = analyze_symbol(sym, settings)
            except Exception as e:
                logger.exception(f"{sym}: analyze_symbol crashed — {e}")
                continue
            if not passed or price is None:
                continue

            tokens = [(t or '').replace(' ', '').lower() for t in (triggered or [])]
            sig_count = len(tokens)
            has_sma20 = any('price>sma20' in t or 'price>sma(20)' in t for t in tokens)
            has_adx   = any(t.startswith('adx') or 'adx>=' in t for t in tokens)
            has_macd  = any('macd' in t for t in tokens)
            meets_reqs = (('adx' not in req or has_adx) and ('macd' not in req or has_macd))

            if (sig_count >= strict_signals) and (not require_sma20 or has_sma20) and meets_reqs:
                candidates.append((sym, float(price), list(triggered)))

        # Nothing to do this round
        if not candidates:
            logger.info("[LIVE] no candidates this round")
            time.sleep(getattr(settings, "poll_interval", 5.0))
            continue

        # Rank candidates
        def _score(sym, price, triggered):
            return len(triggered) * 10 + price * 0.01
        ranked = sorted(candidates, key=lambda t: _score(*t), reverse=True)

        # --- context used by risk gates / qty calc -------------------------
        try:
            acct = broker.get_account_summary() or {}
            live_bp = float(acct.get("buying_power") or acct.get("settled_cash") or 0.0)
        except Exception as e:
            logger.warning(f"[LIVE] account summary failed: {e}")
            live_bp = None

        trade_log = get_trades(10000)
        holdingsL = {s: {"qty": q, "avg_cost": ac, "last_price": lp}
                     for s, q, ac, lp in get_holdings()}

        pyramid_rules = {
            "max_adds": 2,
            "min_add_interval_s": 300,
            "min_add_distance_pct": 1.0,
            "max_position_qty": 999999,
            "t_plus_settlement_days": 2
        }

        def _get_buy_events(sym):
            ev = []
            for t in (trade_log or []):
                if (t.get("symbol") == sym) and (str(t.get("action","")).upper() == "BUY"):
                    ts = t.get("trade_time")
                    try:
                        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        dt = datetime.now(timezone.utc)
                    ev.append({"time": dt,
                               "price": float(t.get("price") or 0.0),
                               "qty":   int(float(t.get("qty") or 0))})
            return sorted(ev, key=lambda e: e["time"])

        def _pyramid_ok(sym, price, qty, rules):
            pos = holdingsL.get(sym, {"qty": 0, "avg_cost": None, "last_price": None})
            buys = _get_buy_events(sym)
            reasons = []

            # cash gate: prefer live buying power, fallback to sim cash
            available = live_bp if live_bp is not None else get_cash()
            if (available - price * qty) < 1.00:
                reasons.append("cash")

            if not buys:
                if qty > rules["max_position_qty"]:
                    reasons.append("max_qty")
                return (len(reasons) == 0), reasons

            adds = max(len(buys) - 1, 0)
            last_fill_px = buys[-1]["price"]
            first_buy_dt = buys[0]["time"]
            last_add_dt  = buys[-1]["time"]

            if adds >= rules["max_adds"]:
                reasons.append("max_adds")

            since = (datetime.now(timezone.utc) - last_add_dt).total_seconds()
            if since < rules["min_add_interval_s"]:
                reasons.append("cooldown")

            min_px = last_fill_px * (1 + rules["min_add_distance_pct"]/100.0)
            if price < min_px:
                reasons.append("distance")

            if rules.get("t_plus_settlement_days", 0) > 0 and pos.get("qty", 0) > 0:
                earliest_next = first_buy_dt + timedelta(days=rules["t_plus_settlement_days"])
                if datetime.now(timezone.utc) < earliest_next:
                    reasons.append("t+2")

            if (pos.get("qty", 0) + qty) > rules["max_position_qty"]:
                reasons.append("max_qty")

            return (len(reasons) == 0), reasons
        # -------------------------------------------------------------------

        # Guardrail: only one live position / one buy per day
        if lg.has_bought_today() or lg.open_position_exists():
            logger.info("[GR] Buy gate closed (already bought today or an open position exists)")
            time.sleep(getattr(settings, "poll_interval", 5.0))
            continue

        # Try to buy top-ranked candidate that passes gates
        purchased = False
        for sym, price, triggered in ranked:
            if len(triggered) < strict_signals:
                continue

            sim_qty = compute_qty(settings, price)
            qty = min(sim_qty, int(live_bp // price)) if live_bp is not None else sim_qty
            if qty < 1:
                logger.info(f"[LIVE] Skip {sym}: qty < 1 (price={price:.2f}, live_bp={live_bp})")
                continue

            ok, why = _pyramid_ok(sym, price, qty, pyramid_rules)
            if not ok:
                logger.info(f"[LIVE] Blocked {sym} by pyramiding: {','.join(why)}")
                continue

            try:
                resp = broker.buy(sym, qty, price)    # ⬅️ no 'armed' check
                logger.info(f"[LIVE] ✅ BUY {sym} x{qty} @ {price:.2f} via {broker.name} -> {resp}")
                lg.record_entry(sym, qty)             # ⬅️ arm the auto-seller for next open
                purchased = True
                break
            except Exception as e:
                logger.exception(f"[LIVE] BUY failed for {sym}: {e}")

        if not purchased:
            logger.info("[LIVE] ranked selection found no purchasable candidates (all gated)")

        time.sleep(getattr(settings, "poll_interval", 5.0))
