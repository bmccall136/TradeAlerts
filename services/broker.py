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

# ── .env helpers ──────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
def _normalize_symbol(sym: str) -> str:
    if not sym:
        return sym
    s = sym.upper().strip()
    # prefer dot for class shares (E*TRADE accepts either, normalize once)
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
    # E*TRADE accepts 2dp >=$1, 4dp for sub-dollar
    return float(f"{px:.2f}" if t == 0.01 else f"{px:.4f}")


def _round4(x: float | None) -> float | None:
    return None if x is None else float(f"{float(x):.4f}")


# ──────────────────────────────────────────────────────────────────────────────
# Error
# ──────────────────────────────────────────────────────────────────────────────
class ETradeHTTPError(RuntimeError):
    def __init__(self, status_code: int, payload: Any):
        super().__init__(f"{status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload


# ──────────────────────────────────────────────────────────────────────────────
# E*TRADE raw client (minimal subset we use)
# ──────────────────────────────────────────────────────────────────────────────
class ETradeService:
    def __init__(self) -> None:
        host = os.getenv("ETRADE_API_HOST", "https://api.etrade.com").rstrip("/")
        self.base = f"{host}/v1"

        ck = os.getenv("ETRADE_CONSUMER_KEY")
        cs = os.getenv("ETRADE_CONSUMER_SECRET")
        at = os.getenv("ETRADE_ACCESS_TOKEN")
        ats = os.getenv("ETRADE_ACCESS_TOKEN_SECRET")
        missing = [
            n
            for n, v in [
                ("ETRADE_CONSUMER_KEY", ck),
                ("ETRADE_CONSUMER_SECRET", cs),
                ("ETRADE_ACCESS_TOKEN", at),
                ("ETRADE_ACCESS_TOKEN_SECRET", ats),
            ]
            if not v
        ]
        if missing:
            raise RuntimeError(f"Missing env: {', '.join(missing)}")

        self.session = requests.Session()
        self.session.auth = OAuth1(ck, cs, at, ats)

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "Accept": "application/json"}

    def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
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
        r = self.session.post(
            url, data=json.dumps(payload), headers=self._headers(), timeout=30
        )
        if r.status_code >= 400:
            try:
                body = r.json()
            except Exception:
                body = r.text
            try:
                dbg = json.dumps(payload, indent=2)
            except Exception:
                dbg = str(payload)
            log.error(
                "POST %s -> %s\npayload=%s\nresp=%s", url, r.status_code, dbg, body
            )
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
            a = (
                data.get("AccountListResponse", {})
                .get("Accounts", {})
                .get("Account", [])
            )
            if isinstance(a, list) and a:
                return a[0].get("accountIdKey")
        except Exception as e:
            log.exception("Failed to list accounts: %s", e)
        return None

    # services/broker.py (inside class ETradeService)
    def get_balances(self, account_id_key: str, realtime: bool = True) -> dict:
        params = {"instType": "BROKERAGE"}
        if realtime:
            params["realTimeNAV"] = "true"
        return self._get(f"/accounts/{account_id_key}/balance.json", params=params)

    # quotes (batch)
    # services/broker.py (or broker_live.py)
    def get_quotes_batch(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        from services.etrade_service import get_quotes_map

        return get_quotes_map(symbols)

    # orders
    def preview_equity_order(
        self,
        account_id_key: str,
        symbol: str,
        quantity: int,
        price: float | None,
        action: str,
        order_term: str = "GOOD_FOR_DAY",
        market_session: str = "REGULAR",
        price_type: str | None = None,
        client_order_id: str | None = None,
        all_or_none: bool = False,
        stop_price: float | None = None,
        offset_type: str | None = None,
        offset_value: float | None = None,
    ) -> dict[str, Any]:
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
            "Instrument": [
                {
                    "Product": {"securityType": "EQ", "symbol": symbol},
                    "orderAction": action,
                    "quantityType": "QUANTITY",
                    "quantity": int(quantity),
                }
            ],
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

    def place_equity_order(
        self,
        account_id_key: str,
        symbol: str,
        quantity: int,
        price: float | None,
        action: str,
        preview_id: int,
        order_term: str = "GOOD_FOR_DAY",
        market_session: str = "REGULAR",
        price_type: str | None = None,
        client_order_id: str | None = None,
        all_or_none: bool = False,
        stop_price: float | None = None,
        offset_type: str | None = None,
        offset_value: float | None = None,
    ) -> dict[str, Any]:
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
            "Instrument": [
                {
                    "Product": {"securityType": "EQ", "symbol": symbol},
                    "orderAction": action,
                    "quantityType": "QUANTITY",
                    "quantity": int(quantity),
                }
            ],
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


# ──────────────────────────────────────────────────────────────────────────────
# Broker facade
# ──────────────────────────────────────────────────────────────────────────────
class LiveBroker:
    @property
    def account_id_key(self) -> str:
        return self._account_id_key

    def _ensure_account_key(self):
        # already cached?
        if getattr(self, "_account_id_key", None):
            return self._account_id_key

        # fetch and cache from /accounts/list.json
        j = self._get("/v1/accounts/list.json").json()
        acc = (j.get("AccountListResponse") or {}).get("Accounts", {}).get(
            "Account"
        ) or []
        if isinstance(acc, dict):
            acc = [acc]
        for a in acc:
            if a.get("institutionType") == "BROKERAGE" or a.get("accountType") in (
                "INDIVIDUAL",
                "JOINT",
                "IRA",
            ):
                self._account_id_key = a.get("accountIdKey") or a.get("accountId")
                break
        if not getattr(self, "_account_id_key", None):
            raise RuntimeError("Could not resolve accountIdKey from list.json")
        return self._account_id_key

    def get_account(self, path: str, params: dict | None = None):
        """
        Wrapper for account-scoped endpoints. `path` must be like '/balance.json'
        or '/portfolio.json' etc. We inject '/v1/accounts/{accountIdKey}'.
        """
        aid = self._ensure_account_key()

        # allow market endpoints to pass through untouched
        if path.startswith("/v1/"):
            url = path  # already full
        else:
            # ensure leading slash
            if not path.startswith("/"):
                path = "/" + path
            url = f"/v1/accounts/{aid}{path}"

        r = self._get(url, params or {})  # your existing OAuth1 GET
        # If the key got stale, refresh once on 100/102
        if r.status_code == 400:
            try:
                body = r.json().get("Error", {})
                if body.get("code") in (100, 102):
                    # refresh key and retry once
                    self._account_id_key = None
                    aid = self._ensure_account_key()
                    url = f"/v1/accounts/{aid}{path}"
                    r = self._get(url, params or {})
            except Exception:
                pass
        r.raise_for_status()
        return r.json() if url.endswith(".json") else r

    def get_account(self, path: str, params: dict | None = None) -> dict:
        """
        Public wrapper used by the dashboard. Accepts either a short path
        like '/balance.json' or a full '/accounts/<key>/balance.json'.
        Routes to the resilient _get_account which refreshes accountIdKey
        on code 100 and retries 5xx with backoff.
        """
        params = params or {}
        norm = path or ""
        if isinstance(norm, str) and norm.startswith("/accounts/"):
            parts = norm.split("/", 3)  # ["", "accounts", "<aid>", "rest..."]
            if len(parts) >= 4:
                norm = "/" + parts[3]
        return self._get_account(norm, params)

    def _refresh_account_id_key(self) -> bool:
        """Refresh self._account_id_key from /v1/accounts/list.json."""
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

        # Prefer brokerage; else first
        new_key = None
        for a in acs:
            if str(a.get("accountMode") or "").upper() == "BROKERAGE":
                new_key = a.get("accountIdKey") or a.get("accountId")
                break
        if not new_key:
            a0 = acs[0]
            new_key = a0.get("accountIdKey") or a0.get("accountId")

        if new_key and new_key != getattr(self, "_account_id_key", None):
            log.warning(
                "[LIVE] accountIdKey changed %s -> %s",
                getattr(self, "_account_id_key", None),
                new_key,
            )
            self._account_id_key = new_key
            return True
        return bool(new_key)

    # services/broker.py inside LiveBroker
    def get_portfolio(self) -> dict:
        return self._get_account("/portfolio.json", {"instType": "BROKERAGE"}) or {}

    def _get_account(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        norm = str(path or "")

        # these endpoints are NOT account-scoped
        if (
            norm.startswith("/accounts/list.json")
            or norm.startswith("/market/")
            or norm.startswith("/v1/market/")
        ):
            return self._et._get(norm, params)

        # Lazy resolve key if empty
        if not getattr(self, "_account_id_key", ""):
            if not self._refresh_account_id_key():
                log.error(
                    "[LIVE] no accountIdKey and refresh failed; returning {} for %s",
                    path,
                )
                return {}

        attempts = 0
        while True:
            attempts += 1
            try:
                # NEW (bypasses any instance-level monkey patch)
                return ETradeService._get(
                    self._et, f"/accounts/{self._account_id_key}{path}", params=params
                )
            except ETradeHTTPError as e:
                status = getattr(e, "status_code", None)
                payload = getattr(e, "payload", {}) or {}
                err = payload.get("Error") or {}
                code = err.get("code")
                msg = (err.get("message") or "").lower()

                # stale/wrong key
                if (
                    status
                    and 400 <= status < 500
                    and code == 100
                    and "belong to user" in msg
                ):
                    log.warning("[LIVE] code 100 on %s; refreshing accountIdKey", path)
                    if self._refresh_account_id_key():
                        continue
                    log.error("[LIVE] could not refresh accountIdKey; returning {}")
                    return {}

                # transient hiccup: retry up to 3 times
                if status and status >= 500 and attempts <= 3:
                    delay = 0.4 * (2 ** (attempts - 1)) + random.uniform(0, 0.25)
                    log.warning(
                        "[LIVE] %s on %s; retry %d in %.2fs",
                        status,
                        path,
                        attempts,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                log.error(
                    "[LIVE] _get_account failed %s %s -> returning {}", status, path
                )
                return {}

    def _fresh_funds(self) -> float | None:
        now = time.time()
        if (
            self._pp_cache["pp"] is not None
            and (now - self._pp_cache["ts"]) < self._pp_ttl
        ):
            return self._pp_cache["pp"]
        try:
            br = self._et.get_balances(self._account_id_key, realtime=True).get(
                "BalanceResponse", {}
            )
            comp = br.get("Computed", {}) or {}
            cash = br.get("Cash", {}) or {}

            # Most conservative & E*TRADE-consistent order
            for k in (
                "cashAvailableForWithdrawal",
                "cashAvailableForInvestment",
                "settledCashForInvestment",
                "cashBuyingPower",
                "marginBuyingPower",
            ):
                v = comp.get(k)
                if isinstance(v, (int, float)):
                    self._pp_cache.update(ts=now, pp=float(v))
                    return self._pp_cache["pp"]

            v = cash.get("cashAvailableForInvestment")
            self._pp_cache.update(
                ts=now, pp=(float(v) if isinstance(v, (int, float)) else None)
            )
            return self._pp_cache["pp"]
        except Exception as e:
            log.warning("[LIVE] fresh funds read failed: %s", e)
            return self._pp_cache["pp"]

    def get_account_summary(self) -> dict[str, Any]:
        try:
            br = self._et.get_balances(self._account_id_key, realtime=True).get(
                "BalanceResponse", {}
            )
            comp = br.get("Computed", {}) or {}
            cash = br.get("Cash", {}) or {}
            rtv = comp.get("RealTimeValues", {}) or {}

            # opportunistic cache refresh
            for k in (
                "cashAvailableForWithdrawal",
                "cashAvailableForInvestment",
                "cashBuyingPower",
                "marginBuyingPower",
            ):
                v = comp.get(k)
                if isinstance(v, (int, float)):
                    self._last_bp = float(v)
                    self._bp_ts = time.time()
                    break

            return {
                "Computed": comp,
                "Cash": cash,
                "RealTimeValues": rtv,
                # handy UI rollups
                "ui": {
                    "buying_power": next(
                        (
                            float(comp[k])
                            for k in (
                                "cashAvailableForWithdrawal",
                                "cashAvailableForInvestment",
                                "settledCashForInvestment",
                                "cashBuyingPower",
                                "marginBuyingPower",
                            )
                            if isinstance(comp.get(k), (int, float))
                        ),
                        None,
                    ),
                    "available_to_trade": comp.get("cashAvailableForInvestment"),
                    "available_to_withdraw": comp.get("cashAvailableForWithdrawal")
                    or comp.get("totalAvailableForWithdrawal"),
                    "settled_cash": comp.get("settledCashForInvestment")
                    or cash.get("settledCash"),
                    "nav": rtv.get("totalAccountValue")
                    or ((comp.get("netCash") or 0) + (rtv.get("netMv") or 0)),
                    "positions_value": rtv.get("netMv"),
                },
            }
        except Exception as e:
            log.exception("[LIVE] account summary error: %s", e)
            return {}

    def __init__(self, mode: str = "LIVE") -> None:
        self.mode = (mode or "LIVE").upper()
        self.name = "E*TRADE"
        self._et = ETradeService()

        # Try env first, then API, but never hard-fail here
        env_key = (
            os.getenv("ETRADE_ACCOUNT_ID_KEY")
            or os.getenv("ETRADE_ACCOUNT_KEY")
            or None
        )
        api_key = None
        try:
            api_key = self._et.first_account_id_key()
        except Exception as e:
            log.warning("[LIVE] first_account_id_key failed at init: %s", e)

        self._account_id_key = (
            env_key or api_key or ""
        )  # may be empty; lazy-refresh later
        if not self._account_id_key:
            log.warning(
                "[LIVE] starting without accountIdKey; will lazy-refresh on first account call"
            )

        # Caches / TTLs
        self._pp_cache = {"ts": 0.0, "pp": None}
        self._pp_ttl = float(os.getenv("LIVE_FUNDS_TTL_SEC", "15"))
        self._last_bp: float | None = None
        self._bp_ts: float = 0.0
        self._bp_ttl = int(os.getenv("LIVE_BP_TTL_SECONDS", "45"))

    def get_buying_power(self, fresh: bool = False) -> float | None:
        if (
            (not fresh)
            and (self._last_bp is not None)
            and (time.time() - self._bp_ts < self._bp_ttl)
        ):
            return self._last_bp
        try:
            br = self._et.get_balances(self._account_id_key, realtime=True).get(
                "BalanceResponse", {}
            )
            comp = br.get("Computed", {}) or {}
            # prefer conservative fields; fall back to BP
            for k in (
                "cashAvailableForWithdrawal",
                "cashAvailableForInvestment",
                "settledCashForInvestment",
                "cashBuyingPower",
                "marginBuyingPower",
            ):
                v = comp.get(k)
                if isinstance(v, (int, float)):
                    self._last_bp = float(v)
                    self._bp_ts = time.time()
                    return self._last_bp
        except Exception as e:
            log.warning("[LIVE] balances failed: %s; using cached BP if available", e)
            return self._last_bp
        return None

    # Public wrappers
    def buy(self, symbol: str, quantity: int, price: float | None = None, **kw):
        return self._trade("BUY", symbol, quantity, price, **kw)

    def sell(self, symbol: str, quantity: int, price: float | None = None, **kw):
        return self._trade("SELL", symbol, quantity, price, **kw)

    # Core trade
    def _trade(
        self, action: str, symbol: str, quantity: int, price: float | None, **kw
    ) -> dict[str, Any]:
        q = int(max(0, quantity))
        sym = _normalize_symbol(symbol)
        px = _round_limit(price, action) if price is not None else None
        log.info("[LIVE] %s request for %s x%d @%s", action, sym, q, px)

        # --- BEFORE preview, resize by fresh funds (prevents 8400 spam) ---
        bp = self._fresh_funds()
        if isinstance(bp, (int, float)) and (px or 0) > 0:
            afford = int(max(0.0, float(bp) - 0.01) // float(px))  # tiny penny buffer
            if afford < q:
                log.info(
                    "[LIVE] resizing by broker funds %s: q %d→%d (fresh_pp=%.2f, px=%.4f)",
                    sym,
                    q,
                    afford,
                    bp,
                    px or 0.0,
                )
                q = afford
        else:
            # When bp is None (401/429/etc), do NOT resize to zero
            log.info("[LIVE] funds check skipped (fresh funds unavailable)")

        # If qty ≤ 0, only call it INSUFFICIENT_FUNDS when funds were numeric
        if q <= 0:
            return {
                "ok": False,
                "reason": "INSUFFICIENT_FUNDS"
                if isinstance(bp, (int, float))
                else "QTY_LT_ONE",
                "fresh_pp": (None if bp is None else round(float(bp), 2)),
                "px": px,
            }

        # --- PREVIEW ---
        try:
            prev = self._et.preview_equity_order(
                self._account_id_key, sym, q, px, action, **kw
            )
        except ETradeHTTPError as e:
            msg = str(e.payload) if hasattr(e, "payload") else str(e)
            short = None
            try:
                s = (
                    json.dumps(e.payload)
                    if isinstance(e.payload, dict)
                    else str(e.payload)
                )
                import re

                m = re.search(r"approximately\s*\$([0-9]+(?:\.[0-9]+)?)", s, re.I)
                if m:
                    short = float(m.group(1))
            except Exception:
                pass
            log.info(
                "[LIVE] preview rejected %s (fresh_pp=%.2f, px=%.4f, q=%d, shortfall=%s)",
                sym,
                float(bp or 0),
                float(px or 0),
                q,
                (f"${short:.2f}" if short is not None else "n/a"),
            )
            return {
                "ok": False,
                "reason": "INSUFFICIENT_FUNDS",
                "error": msg,
                "fresh_pp": round(float(bp or 0), 2),
                "px": px,
                "q": q,
                "shortfall": short,
            }
        except Exception as e:
            log.exception("[LIVE] preview error")
            return {"ok": False, "reason": "EXCEPTION", "error": str(e)}

        # Dig previewId
        # --- Dig previewId (and adapt if missing) ---
        def _dig_preview_id(node) -> int | None:
            if isinstance(node, dict):
                for k in ("previewId","PreviewId","preview_id","PreviewID","previewID"):
                    if k in node:
                        try: return int(node[k])
                        except Exception: pass
                for v in node.values():
                    got = _dig_preview_id(v)
                    if got is not None:
                        return got
            elif isinstance(node, (list, tuple)):
                for it in node:
                    got = _dig_preview_id(it)
                    if got is not None:
                        return got
            return None

        def _maybe_numeric_account(node) -> str | None:
            if not isinstance(node, dict): 
                return None
            por = node.get("PreviewOrderResponse") or node.get("previewOrderResponse") or {}
            if isinstance(por, dict):
                aid = por.get("accountId") or por.get("accountID")
                if aid:
                    return str(aid)
            return None

        def _extract_err(node) -> tuple[int|None, str|None]:
            if not isinstance(node, dict):
                return None, None
            err = node.get("Error") or node.get("error")
            if isinstance(err, dict):
                code = err.get("code") or err.get("Code")
                try: code = int(code) if code is not None else None
                except Exception: pass
                msg = err.get("message") or err.get("Message")
                return code, (str(msg) if msg else None)
            for k in ("message","Message","description"):
                if isinstance(node.get(k), str):
                    return None, node[k]
            return None, None

        preview_id = _dig_preview_id(prev)

        # If previewId missing, try numeric-account fallback (the trick we used before)
        if preview_id is None:
            code, msg = _extract_err(prev)
            if code == 1036:
                return {"ok": False, "reason": "CLOSING_ONLY", "error": msg, "preview": prev}

            acct_num = _maybe_numeric_account(prev)
            if acct_num:
                try:
                    log.info("[LIVE] retry preview via numeric accountId=%s", acct_num)
                    prev2 = self._et.preview_equity_order(acct_num, sym, q, px, action, **kw)
                    preview_id = _dig_preview_id(prev2)
                    if preview_id is None:
                        c2, m2 = _extract_err(prev2)
                        reason = "PREVIEW_ID_MISSING_NUMERIC"
                        if c2 or m2: reason += f": code={c2} msg={m2}"
                        return {"ok": False, "reason": reason, "preview": prev2}
                    prev = prev2  # carry forward numeric-path preview
                except Exception as e:
                    return {"ok": False, "reason": "PREVIEW_FALLBACK_EXCEPTION", "error": str(e), "preview": prev}
            else:
                # No numeric hint given; surface any message we got
                reason = "PREVIEW_ID_MISSING"
                if msg: reason += f": {msg}"
                return {"ok": False, "reason": reason, "preview": prev}

        # --- PLACE ---
        try:
            placed = self._et.place_equity_order(self._account_id_key, sym, q, px, action, preview_id, **kw)
        except Exception as e:
            log.exception("[LIVE] place error")
            return {"ok": False, "reason": "EXCEPTION", "error": str(e), "preview": prev}

        # Normalize success
        if isinstance(placed, dict):
            if placed.get("ok") is True:  # some wrappers echo ok
                return {"ok": True, "resp": placed}
            if not any(k in placed for k in ("error","Error","errors")):
                return {"ok": True, "resp": placed}

        return {"ok": False, "reason": "BROKER_REJECT", "resp": placed, "preview": prev}


        # Normalize success
        if isinstance(placed, dict):
            if placed.get("ok") is True:
                return {"ok": True, "resp": placed}
            if not any(k in placed for k in ("error", "Error", "errors")):
                return {"ok": True, "resp": placed}

        return {"ok": False, "reason": "BROKER_REJECT", "resp": placed, "preview": prev}


# singleton
_singleton: LiveBroker | None = None


def get_broker(mode: str | None = "LIVE") -> LiveBroker:
    global _singleton
    if _singleton is None:
        _singleton = LiveBroker(mode)
    return _singleton
