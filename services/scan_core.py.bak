# -*- coding: utf-8 -*-
from __future__ import annotations
import time, logging
from typing import Iterable, Sequence
from services.settings_schema import SimulationSettings
from services.market_service import get_symbols
from services.simulation_service import analyze_symbol, _is_market_open  # reuse
from services.broker_adapter import Broker

log = logging.getLogger("scan")

IGNORED_TICKERS = {"GEVO"}  # same ignore you wanted on Live

def run_scan_loop(broker: Broker, settings: SimulationSettings, symbols: Sequence[str] | None = None):
    if not symbols:
        symbols = get_symbols(simulation=False)  # for Live; pass simulation=True for sim page

    strict = getattr(settings, "strict_buy_signals", 4)
    require_sma20 = getattr(settings, "require_sma20", True)
    req = set(getattr(settings, "required_filters", []))  # {'adx','macd',...}

    while True:
        if settings.pause_when_market_closed and not _is_market_open():
            wait = getattr(settings, "poll_interval", 10.0)
            log.info(f"[SCAN] market closed; sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        candidates: list[tuple[str, float, list[str]]] = []

        for sym in symbols:
            if sym in IGNORED_TICKERS:
                continue
            try:
                price, triggered, _ = analyze_symbol(sym, settings)
            except Exception as e:
                log.exception(f"{sym}: analyze_symbol failed: {e}")
                continue
            if price is None:
                continue

            toks = [(t or "").replace(" ", "").lower() for t in (triggered or [])]
            sigs = len(toks)

            has_sma20 = any("price>sma20" in t or "price>sma(20)" in t for t in toks)
            has_adx   = any(t.startswith("adx") or "adx>=" in t for t in toks)
            has_macd  = any("macd" in t for t in toks)
            meets_req = (("adx" not in req or has_adx) and ("macd" not in req or has_macd))

            if (sigs >= strict) and (not require_sma20 or has_sma20) and meets_req:
                candidates.append((sym, float(price), list(triggered)))

        if candidates:
            # trivial rank: by signals then by price
            ranked = sorted(candidates, key=lambda t: (len(t[2]), t[1]), reverse=True)
            for sym, px, trigs in ranked:
                qty = max(1, int(getattr(settings, "default_qty", 1)))
                try:
                    ok = broker.buy(sym, qty, px) if getattr(settings, "armed", False) else True
                    if ok:
                        log.info(f"[SCAN] BUY {sym} x{qty} @ {px:.2f}  (sigs={len(trigs)} armed={getattr(settings,'armed',False)})")
                        break
                except Exception as e:
                    log.exception(f"BUY {sym} failed: {e}")
        else:
            log.info("[SCAN] no candidates this pass")

        time.sleep(getattr(settings, "poll_interval", 10.0))
