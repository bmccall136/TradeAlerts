"""
mrna_sell_diag_v8b.py — lean into the one shape that touched the API: place_equity_order(preview_full).

Why this version?
- Your logs showed a real POST only on: place_equity_order(preview_full) -> 500 transient.
- Other shapes were rejected by the wrapper before hitting the API.
- v8b retries the working shape a few times, then (only if needed) falls back to the other shapes.

USAGE:
  python mrna_sell_diag_v8b.py --sell --debug
  python mrna_sell_diag_v8b.py --sell --limit 27.05
  python mrna_sell_diag_v8b.py --sell --place-mode inner    # force preview_inner
  python mrna_sell_diag_v8b.py --sell --place-mode auto     # try full -> inner -> acct+full -> acct+inner
"""

import argparse
import json
import os
import sys
import time
from typing import Any

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from services import etrade_service as et

SYMBOL = "MRNA"


def _fmt(o: Any) -> str:
    try:
        return json.dumps(o, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(o)


def _f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def get_acct_key() -> str:
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k:
                return str(k)
        except Exception:
            pass
    if hasattr(et, "account_id_key"):
        k = et.account_id_key
        if k:
            return str(k)
    raise RuntimeError("Could not determine account_id_key")


def available_to_sell(acct_key: str, symbol: str) -> float:
    if hasattr(et, "available_to_sell"):
        try:
            return _f(et.available_to_sell(acct_key, symbol), 0.0)
        except Exception:
            pass
    return 0.0


def _maybe_pick(v, *keys):
    if not isinstance(v, dict):
        return None
    for k in keys:
        if k in v:
            return v[k]
        cap = k[0].upper() + k[1:]
        low = k.lower()
        up = k.upper()
        for kk in (cap, low, up):
            if kk in v:
                return v[kk]
    return None


def best_quote(symbol: str, debug=False) -> dict[str, float]:
    out = {"bid": 0.0, "last": 0.0}
    # fetch_etrade_quote
    try:
        q = et.fetch_etrade_quote(symbol)
        if isinstance(q, dict):
            out["bid"] = max(
                out["bid"], _f(_maybe_pick(q, "bid", "bidPrice", "bestBid"), 0.0)
            )
            out["last"] = max(
                out["last"],
                _f(_maybe_pick(q, "last", "lastPrice", "lastTrade", "close"), 0.0),
            )
            for nested_key in ("All", "ExtendedHourQuoteDetail"):
                n = q.get(nested_key)
                if isinstance(n, dict):
                    out["bid"] = max(
                        out["bid"],
                        _f(_maybe_pick(n, "bid", "bidPrice", "bestBid"), 0.0),
                    )
                    out["last"] = max(
                        out["last"],
                        _f(
                            _maybe_pick(n, "last", "lastPrice", "lastTrade", "close"),
                            0.0,
                        ),
                    )
    except Exception:
        pass
    # get_quote
    try:
        g = et.get_quote(symbol)
        if isinstance(g, dict):
            QR = _maybe_pick(g, "QuoteResponse", "quoteResponse") or {}
            qd = _maybe_pick(QR, "QuoteData", "quoteData")
            if isinstance(qd, list) and qd:
                qd = qd[0]
            if isinstance(qd, dict):
                for nested_key in (
                    "All",
                    "all",
                    "ExtendedHourQuoteDetail",
                    "extendedHourQuoteDetail",
                ):
                    n = qd.get(nested_key)
                    if isinstance(n, dict):
                        out["bid"] = max(
                            out["bid"],
                            _f(_maybe_pick(n, "bid", "bidPrice", "bestBid"), 0.0),
                        )
                        out["last"] = max(
                            out["last"],
                            _f(
                                _maybe_pick(
                                    n, "last", "lastPrice", "lastTrade", "close"
                                ),
                                0.0,
                            ),
                        )
    except Exception:
        pass
    return out


def preview(acct_key: str, symbol: str, qty: int, limit_price: float):
    return et.preview_equity_order(
        account_id_key=acct_key,
        action="SELL",
        symbol=symbol,
        qty=qty,
        price=float(limit_price),
    )


def place_with_retries(fn, payload, debug=False, tries=3, delay=0.8):
    for i in range(1, tries + 1):
        try:
            return fn(payload), f"place(preview_full) attempt {i}"
        except Exception as e:
            msg = str(e)
            if debug:
                print(f"[DBG] place(preview_full) attempt {i} failed:", msg)
            if "service is not currently available" in msg and i < tries:
                time.sleep(delay)
                continue
            # if wrapper says "preview response missing Order", it probably wanted full object; we ARE sending it; keep retrying
            if "preview response missing Order" in msg and i < tries:
                time.sleep(delay)
                continue
            # otherwise give up
            break
    return None, "place(preview_full) exhausted"


def place_fallbacks(acct_key, prev, debug=False):
    inner = prev.get("PreviewOrderResponse") or prev.get("previewOrderResponse")
    if not isinstance(inner, dict):
        return None, "no PreviewOrderResponse in preview"
    fn = et.place_equity_order

    # 2) inner only
    try:
        return fn(inner), "place(preview_inner)"
    except Exception as e:
        if debug:
            print("[DBG] place(preview_inner) failed:", e)

    # 3) acct + full
    try:
        return fn(acct_key, prev), "place(acct_key, preview_full)"
    except Exception as e:
        if debug:
            print("[DBG] place(acct_key, preview_full) failed:", e)

    # 4) acct + inner
    try:
        return fn(acct_key, inner), "place(acct_key, preview_inner)"
    except Exception as e:
        if debug:
            print("[DBG] place(acct_key, preview_inner) failed:", e)

    return None, "all fallbacks failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sell", nargs="?", const="__AUTO__", help="sell all available if omitted"
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--limit", type=float, help="explicit limit price (overrides quotes)"
    )
    ap.add_argument("--offset", type=float, default=0.02)
    ap.add_argument("--use-last", action="store_true")
    ap.add_argument(
        "--place-mode",
        choices=["full", "inner", "auto"],
        default="full",
        help="placement shape to use",
    )
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    avail = available_to_sell(acct_key, SYMBOL)
    print(f"[POS] {SYMBOL}: available_to_sell={avail}")

    if args.sell is None:
        return

    qty = avail if args.sell == "__AUTO__" else _f(args.sell, -1)
    if qty <= 0:
        print("[SELL] Aborting: qty <= 0")
        return
    if qty > avail:
        if args.force:
            print(f"[SELL] Requested {qty} > available {avail}; clamping.")
            qty = avail
        else:
            print(
                f"[SELL] Requested {qty} exceeds available {avail}. Use --force or cancel reserving orders."
            )
            return
    qty = int(qty)
    if qty <= 0:
        print("[SELL] Fractional only; route likely disallows fractional sells.")
        return

    # price
    if args.limit and args.limit > 0:
        price = float(args.limit)
        print(f"[QUOTE] using manual --limit {price:.2f}")
    else:
        q = best_quote(SYMBOL, debug=args.debug)
        src = "last" if args.use_last else "bid"
        base = q.get(src, 0.0) or q.get("last" if src == "bid" else "bid", 0.0)
        if base <= 0:
            print(
                "[QUOTE] Could not get a valid price from any helper. Provide --limit <price> to override."
            )
            return
        price = max(0.01, base - args.offset)
        print(
            f"[QUOTE] {SYMBOL} {src.upper()}={base:.2f} -> limit={price:.2f} (offset {args.offset:.2f})"
        )

    # preview
    try:
        prev = preview(acct_key, SYMBOL, qty, price)
    except Exception as e:
        print("[PREVIEW] failed:", e)
        return
    print("[PREVIEW] ok")
    if args.debug:
        print(_fmt(prev))

    # place
    fn = et.place_equity_order
    if args.place_mode == "full":
        resp, how = place_with_retries(fn, prev, debug=args.debug, tries=3)
        if resp is None:
            # try conservative fallbacks
            resp, how = place_fallbacks(acct_key, prev, debug=args.debug)
    elif args.place_mode == "inner":
        inner = prev.get("PreviewOrderResponse") or prev.get("previewOrderResponse")
        if not isinstance(inner, dict):
            print("[SELL] no PreviewOrderResponse in preview")
            return
        # attempt inner with light retries
        ok = None
        how = ""
        for i in range(1, 3):
            try:
                ok = fn(inner)
                how = f"place(preview_inner) attempt {i}"
                break
            except Exception as e:
                if args.debug:
                    print(f"[DBG] place(preview_inner) attempt {i} failed:", e)
                time.sleep(0.6)
        resp = ok
        if resp is None:
            resp, how = place_fallbacks(acct_key, prev, debug=args.debug)
    else:  # auto
        # try full with 2 attempts then fallbacks
        resp, how = place_with_retries(fn, prev, debug=args.debug, tries=2)
        if resp is None:
            resp, how = place_fallbacks(acct_key, prev, debug=args.debug)

    if resp is None:
        print(f"[SELL] {how}")
        return
    print(f"[SELL] via {how} -> ok")
    print(_fmt(resp))


if __name__ == "__main__":
    main()
