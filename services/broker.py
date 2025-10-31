# services/broker.py
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any

import requests
from requests_oauthlib import OAuth1

log = logging.getLogger(__name__)

# ── env loading ────────────────────────────────────────────────────────────────
try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(), override=True)
except Exception:
    pass

def _alias_env(a: str, b: str) -> None:
    va, vb = os.getenv(a), os.getenv(b)
    if va and not vb:
        os.environ[b] = va
    if vb and not va:
        os.environ[a] = vb

for A, B in [
    ("OAUTH_TOKEN", "ETRADE_ACCESS_TOKEN"),
    ("OAUTH_TOKEN_SECRET", "ETRADE_ACCESS_TOKEN_SECRET"),
    ("ETRADE_CONSUMER_KEY", "CONSUMER_KEY"),
    ("ETRADE_CONSUMER_SECRET", "CONSUMER_SECRET"),
]:
    _alias_env(A, B)

os.environ.setdefault("ETRADE_API_HOST", "https://api.etrade.com")

# ── utils ─────────────────────────────────────────────────────────────────────
def _normalize_symbol(sym: str) -> str:
    if not sym:
        return sym
    s = sym.upper().strip()
    if "-" in s and len(s.split("-")[-1]) <= 2:
        s = s.replace("-", ".")
    return s

def _tick_size(price: float) -> float:
    return 0.01 if (price or 0) >= 1 else 0.0001

def _round_limit(price: float | None, side: str) -> float | None:
    if price is None:
        return None
    t = _tick_size(price)
    q = price / t
    q = math.floor(q) if str(side).upper().startswith("BUY") else math.ceil(q)
    px = q * t
    return float(f"{px:.2f}" if t == 0.01 else f"{px:.4f}")

def _round4(x: float | None) -> float | None:
    return None if x is None else float(f"{float(x):.4f}")

def _num(x) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(",", "").strip()
        return float(s) if s not in ("", "None") else None
    except Exception:
        return None

def _pick_first(*vals) -> float | None:
    for v in vals:
        n = _num(v)
        if n is not None:
            return n
    return None

# ── error ─────────────────────────────────────────────────────────────────────
class ETradeHTTPError(RuntimeError):
    def __init__(self, status_code: int, payload: Any):
        super().__init__(f"{status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload

# ── low-level E*TRADE client subset ───────────────────────────────────────────
class ETradeService:
    def __init__(self) -> None:
        host = os.getenv("ETRADE_API_HOST", "https://api.etrade.com").rstrip("/")
        self.base = f"{host}/v1"

        ck = os.getenv("ETRADE_CONSUMER_KEY")
        cs = os.getenv("ETRADE_CONSUMER_SECRET")
        at = os.getenv("ETRADE_ACCESS_TOKEN")
        ats = os.getenv("ETRADE_ACCESS_TOKEN_SECRET")
        missing = [n for n, v in [
            ("ETRADE_CONSUMER_KEY", ck),
            ("ETRADE_CONSUMER_SECRET", cs),
            ("ETRADE_ACCESS_TOKEN", at),
            ("ETRADE_ACCESS_TOKEN_SECRET", ats),
        ] if not v]
        if missing:
            raise RuntimeError(f"Missing env: {', '.join(missing)}")

        self.session = requests.Session()
        self.session.auth = OAuth1(ck, cs, at, ats)

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "Accept": "application/json"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base}{path}"
        r = self.session.get(url, params=params, headers=self._headers(), timeout=30)
        if r.status_code >= 400:
            try:
                body = r.json()
            except Exception:
                body = r.text
            log.error("GET %s -> %s\n%s", url, r.status_code, body)
            raise ETradeHTTPError(r.status_code, body)
        try:
            return r.json()
        except Exception:
            return {}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base}{path}"
        r = self.session.post(url, data=json.dumps(payload), headers=self._headers(), timeout=30)
        if r.status_code >= 400:
            try:
                body = r.json()
            except Exception:
                body = r.text
            try:
                dbg = json.dumps(payload, indent=2)
            except Exception:
                dbg = str(payload)
            log.error("POST %s -> %s\npayload=%s\nresp=%s", url, r.status_code, dbg, body)
            raise ETradeHTTPError(r.status_code, body)
        try:
            return r.json()
        except Exception:
            return {}

    # accounts
    def list_accounts(self) -> dict[str, Any]:
        return self._get("/accounts/list.json")

    def first_account_id_key(self) -> str | None:
        try:
            data = self.list_accounts()
            a = (data.get("AccountListResponse", {})
                     .get("Accounts", {})
                     .get("Account", []))
            if isinstance(a, list) and a:
                return a[0].get("accountIdKey")
        except Exception as e:
            log.exception("Failed to list accounts: %s", e)
        return None

    def get_balances(self, account_id_key: str, realtime: bool = True) -> dict:
        params = {"instType": "BROKERAGE"}
        if realtime:
            params["realTimeNAV"] = "true"
        return self._get(f"/accounts/{account_id_key}/balance.json", params=params)

    # orders subset
    def preview_equity_order(self, account_id_key: str, symbol: str, quantity: int,
                             price: float | None, action: str,
                             order_term: str = "GOOD_FOR_DAY",
                             market_session: str = "REGULAR",
                             price_type: str | None = None,
                             client_order_id: str | None = None,
                             all_or_none: bool = False,
                             stop_price: float | None = None,
                             offset_type: str | None = None,
                             offset_value: float | None = None) -> dict[str, Any]:

        if client_order_id is None:
            client_order_id = f"TA{int(time.time()*1000)%1_000_000_000}"

        pt = (price_type or ("LIMIT" if price is not None else "MARKET")).upper()
        order = {
            "allOrNone": bool(all_or_none),
            "priceType": pt,
            "orderTerm": order_term,
            "marketSession": market_session,
            **({"limitPrice": _round4(price)} if price is not None else {}),
            **({"stopPrice": _round4(stop_price)} if stop_price is not None else {}),
            "Instrument": [{
                "Product": {"securityType": "EQ", "symbol": symbol},
                "orderAction": action,
                "quantityType": "QUANTITY",
                "quantity": int(quantity),
            }],
        }
        if pt in ("TRAILING_STOP_PRCT", "TRAILING_STOP_CNST"):
            if offset_value is None:
                raise ValueError("offset_value required for trailing stops")
            order["offsetType"] = offset_type or pt
            order["offsetValue"] = float(offset_value)

        payload = {
            "PreviewOrderRequest": {
                "orderType": "EQ",
                "clientOrderId": client_order_id,
                "Order": [order],
            }
        }
        return self._post(f"/accounts/{account_id_key}/orders/preview.json", payload)

    def place_equity_order(self, account_id_key: str, symbol: str, quantity: int,
                           price: float | None, action: str, preview_id: int,
                           order_term: str = "GOOD_FOR_DAY",
                           market_session: str = "REGULAR",
                           price_type: str | None = None,
                           client_order_id: str | None = None,
                           all_or_none: bool = False,
                           stop_price: float | None = None,
                           offset_type: str | None = None,
                           offset_value: float | None = None) -> dict[str, Any]:

        if client_order_id is None:
            client_order_id = f"TA{int(time.time()*1000)%1_000_000_000}"

        pt = (price_type or ("LIMIT" if price is not None else "MARKET")).upper()
        order = {
            "allOrNone": bool(all_or_none),
            "priceType": pt,
            "orderTerm": order_term,
            "marketSession": market_session,
            **({"limitPrice": _round4(price)} if price is not None else {}),
            **({"stopPrice": _round4(stop_price)} if stop_price is not None else {}),
            "Instrument": [{
                "Product": {"securityType": "EQ", "symbol": symbol},
                "orderAction": action,
                "quantityType": "QUANTITY",
                "quantity": int(quantity),
            }],
        }
        if pt in ("TRAILING_STOP_PRCT", "TRAILING_STOP_CNST"):
            if offset_value is None:
                raise ValueError("offset_value required for trailing stops")
            order["offsetType"] = offset_type or pt
            order["offsetValue"] = float(offset_value)

        payload = {
            "PlaceOrderRequest": {
                "orderType": "EQ",
                "clientOrderId": client_order_id,
                "PreviewIds": [{"previewId": int(preview_id)}],
                "Order": [order],
            }
        }
        return self._post(f"/accounts/{account_id_key}/orders/place.json", payload)

# ── Broker facade (LIVE) ──────────────────────────────────────────────────────
class LiveBroker:
    """Balances + orders for LIVE; cash-account friendly (ATT-first)."""

    def __init__(self, mode: str = "LIVE") -> None:
        self.mode = (mode or "LIVE").upper()
        self.name = "E*TRADE"
        self._et = ETradeService()

        env_key = (os.getenv("ETRADE_ACCOUNT_ID_KEY")
                   or os.getenv("ETRADE_ACCOUNT_KEY") or None)
        api_key = None
        try:
            api_key = self._et.first_account_id_key()
        except Exception as e:
            log.warning("[LIVE] first_account_id_key failed at init: %s", e)

        self._account_id_key = env_key or api_key or ""
        if not self._account_id_key:
            log.warning("[LIVE] starting without accountIdKey; will lazy-refresh on first account call")

        # small TTL caches
        self._pp_cache = {"ts": 0.0, "pp": None}
        self._pp_ttl = float(os.getenv("LIVE_FUNDS_TTL_SEC", "15"))
        self._last_bp: float | None = None
        self._bp_ts: float = 0.0
        self._bp_ttl = int(os.getenv("LIVE_BP_TTL_SECONDS", "45"))

    @property
    def account_id_key(self) -> str:
        return self._account_id_key

    def get_available_to_trade(self) -> float:
        """
        Return available buying power for placing new orders.
        Works for cash accounts (no settledCash quirk) and margin, too.
        """
        try:
            summ = self.get_account_summary() or {}
            # Your normalizer may already produce buying_power; fall back to common keys.
            bp = (
                summ.get("buying_power")
                or summ.get("cashBuyingPower")
                or summ.get("marginBuyingPower")
                or summ.get("availableToTrade")  # if already normalized
                or 0.0
            )
            return float(bp)
        except Exception:
            return 0.0

    def _refresh_account_id_key(self) -> bool:
        try:
            data = self._et.list_accounts()
        except Exception as e:
            log.exception("[LIVE] failed to refresh accountIdKey: %s", e)
            return False

        alr = data.get("AccountListResponse") or {}
        acs = (alr.get("Accounts") or {}).get("Account") or []
        if isinstance(acs, dict):
            acs = [acs]
        if not acs:
            return False

        new_key = None
        for a in acs:
            if str(a.get("accountMode") or "").upper() == "BROKERAGE":
                new_key = a.get("accountIdKey") or a.get("accountId")
                break
        if not new_key:
            a0 = acs[0]
            new_key = a0.get("accountIdKey") or a0.get("accountId")

        if new_key and new_key != getattr(self, "_account_id_key", None):
            log.warning("[LIVE] accountIdKey changed %s -> %s", getattr(self, "_account_id_key", None), new_key)
            self._account_id_key = new_key
            return True
        return bool(new_key)

    # balances parsing (returns simple UI dict)
    def _balances_ui(self) -> dict[str, float | None]:
        try:
            br = self._et.get_balances(self._account_id_key, realtime=True).get("BalanceResponse", {})
        except Exception as e:
            log.warning("[LIVE] balances fetch failed: %s", e)
            return {"available_to_trade": None, "available_to_withdraw": None, "settled_cash": None,
                    "buying_power": None, "nav": None, "positions_value": None}

        comp = br.get("Computed") or {}
        cash = br.get("Cash") or {}
        rtv  = comp.get("RealTimeValues") if isinstance(comp.get("RealTimeValues"), dict) else {}

        buying_power = _pick_first(
            comp.get("cashAvailableForWithdrawal"),
            comp.get("cashAvailableForInvestment"),
            comp.get("settledCashForInvestment"),
            comp.get("cashBuyingPower"),
            comp.get("marginBuyingPower"),
        )
        available_to_trade = _pick_first(
            comp.get("cashAvailableForInvestment"),
            comp.get("cashBuyingPower"),
        )
        available_to_withdraw = _pick_first(
            comp.get("cashAvailableForWithdrawal"),
            comp.get("totalAvailableForWithdrawal"),
        )
        settled_cash = _pick_first(
            comp.get("settledCashForInvestment"),
            cash.get("settledCash"),
        )
        positions_value = _pick_first(
            (rtv or {}).get("netMv"),
            comp.get("netMv"),
        )
        nav = _pick_first(
            (rtv or {}).get("totalAccountValue"),
            (_pick_first(comp.get("netCash"), 0.0) + _pick_first((rtv or {}).get("netMv"), comp.get("netMv"), 0.0)),
        )

        # keep a conservative BP cached
        for k in ("cashAvailableForWithdrawal","cashAvailableForInvestment","cashBuyingPower","marginBuyingPower"):
            v = _num(comp.get(k))
            if v is not None:
                self._last_bp = float(v); self._bp_ts = time.time()
                break

        return {
            "buying_power": buying_power,
            "available_to_trade": available_to_trade,
            "available_to_withdraw": available_to_withdraw,
            "settled_cash": settled_cash,
            "nav": nav,
            "positions_value": positions_value,
        }

    def get_account_summary(self) -> dict[str, Any]:
        try:
            br_full = self._et.get_balances(self._account_id_key, realtime=True).get("BalanceResponse", {})
        except Exception as e:
            log.warning("[LIVE] balances fetch failed: %s", e)
            br_full = {}
        ui = self._balances_ui()
        return {"raw": br_full, "ui": ui}

    # — public accessors used by loops/UI —
    def get_available_to_trade(self) -> float:
        ui = self._balances_ui()
        return float(ui.get("available_to_trade") or 0.0)

    def get_settled_cash(self) -> float:
        ui = self._balances_ui()
        return float(ui.get("settled_cash") or 0.0)

    def get_buying_power(self, fresh: bool = False) -> float | None:
        if ((not fresh) and (self._last_bp is not None) and (time.time() - self._bp_ts < self._bp_ttl)):
            return self._last_bp
        ui = self._balances_ui()
        bp = ui.get("buying_power")
        if bp is not None:
            self._last_bp = float(bp); self._bp_ts = time.time()
        return self._last_bp

    # portfolio (optional)
    def get_portfolio(self) -> dict:
        if not self._account_id_key and not self._refresh_account_id_key():
            return {}
        try:
            return self._et._get(f"/accounts/{self._account_id_key}/portfolio.json", {"instType":"BROKERAGE"}) or {}
        except Exception:
            return {}

    # trades
    def _fresh_funds(self) -> float | None:
        now = time.time()
        if self._pp_cache["pp"] is not None and (now - self._pp_cache["ts"]) < self._pp_ttl:
            return self._pp_cache["pp"]
        try:
            att = _num(self._balances_ui().get("available_to_trade"))
            self._pp_cache.update(ts=now, pp=(None if att is None else float(att)))
            return self._pp_cache["pp"]
        except Exception as e:
            log.warning("[LIVE] fresh funds read failed: %s", e)
            return self._pp_cache["pp"]

    def buy(self, symbol: str, quantity: int, price: float | None = None, **kw):
        return self._trade("BUY", symbol, quantity, price, **kw)

    def sell(self, symbol: str, quantity: int, price: float | None = None, **kw):
        return self._trade("SELL", symbol, quantity, price, **kw)

    def _trade(self, action: str, symbol: str, quantity: int, price: float | None, **kw) -> dict[str, Any]:
        q = int(max(0, quantity))
        sym = _normalize_symbol(symbol)
        px = _round_limit(price, action) if price is not None else None
        log.info("[LIVE] %s request for %s x%d @%s", action, sym, q, px)

        # pre-size via Available-to-Trade
        bp = self._fresh_funds()
        if isinstance(bp, (int, float)) and (px or 0) > 0:
            afford = int(max(0.0, float(bp) - 0.01) // float(px))
            if afford < q:
                log.info("[LIVE] resizing by funds %s: q %d→%d (att=%.2f, px=%.4f)", sym, q, afford, bp, px or 0.0)
                q = afford
        else:
            log.info("[LIVE] funds check skipped (unavailable)")

        if q <= 0:
            return {"ok": False, "reason": "INSUFFICIENT_FUNDS" if isinstance(bp, (int, float)) else "QTY_LT_ONE",
                    "fresh_pp": (None if bp is None else round(float(bp), 2)), "px": px}

        # preview
        try:
            prev = self._et.preview_equity_order(self._account_id_key, sym, q, px, action, **kw)
        except ETradeHTTPError as e:
            msg = str(e.payload) if hasattr(e, "payload") else str(e)
            short = None
            try:
                s = json.dumps(e.payload) if isinstance(e.payload, dict) else str(e.payload)
                import re
                m = re.search(r"approximately\s*\$([0-9]+(?:\.[0-9]+)?)", s, re.I)
                if m:
                    short = float(m.group(1))
            except Exception:
                pass
            log.info("[LIVE] preview rejected %s (att=%.2f, px=%.4f, q=%d, shortfall=%s)",
                     sym, float(bp or 0), float(px or 0), q, (f"${short:.2f}" if short is not None else "n/a"))
            return {"ok": False, "reason": "INSUFFICIENT_FUNDS", "error": msg, "fresh_pp": round(float(bp or 0), 2),
                    "px": px, "q": q, "shortfall": short}
        except Exception as e:
            log.exception("[LIVE] preview error")
            return {"ok": False, "reason": "EXCEPTION", "error": str(e)}

        # extract previewId
        def _dig_preview_id(node) -> int | None:
            if isinstance(node, dict):
                for k in ("previewId","PreviewId","preview_id","PreviewID","previewID"):
                    if k in node:
                        try: return int(node[k])
                        except Exception: pass
                for v in node.values():
                    got = _dig_preview_id(v)
                    if got is not None: return got
            elif isinstance(node, (list, tuple)):
                for it in node:
                    got = _dig_preview_id(it)
                    if got is not None: return got
            return None

        preview_id = _dig_preview_id(prev)
        if preview_id is None:
            # try numeric-account fallback if present
            acct_num = None
            por = prev.get("PreviewOrderResponse") if isinstance(prev, dict) else None
            if isinstance(por, dict):
                acct_num = por.get("accountId") or por.get("accountID")
            if acct_num:
                try:
                    prev2 = self._et.preview_equity_order(acct_num, sym, q, px, action, **kw)
                    preview_id = _dig_preview_id(prev2)
                    if preview_id is None:
                        return {"ok": False, "reason": "PREVIEW_ID_MISSING_NUMERIC", "preview": prev2}
                    prev = prev2
                except Exception as e:
                    return {"ok": False, "reason": "PREVIEW_FALLBACK_EXCEPTION", "error": str(e), "preview": prev}
            else:
                return {"ok": False, "reason": "PREVIEW_ID_MISSING", "preview": prev}

        # place
        try:
            placed = self._et.place_equity_order(self._account_id_key, sym, q, px, action, preview_id, **kw)
        except Exception as e:
            log.exception("[LIVE] place error")
            return {"ok": False, "reason": "EXCEPTION", "error": str(e), "preview": prev}

        if isinstance(placed, dict) and not any(k in placed for k in ("error","Error","errors")):
            return {"ok": True, "resp": placed}
        return {"ok": False, "reason": "BROKER_REJECT", "resp": placed, "preview": prev}

# singleton
_singleton: LiveBroker | None = None
def get_broker(mode: str | None = "LIVE") -> LiveBroker:
    global _singleton
    if _singleton is None:
        _singleton = LiveBroker(mode)
    return _singleton
