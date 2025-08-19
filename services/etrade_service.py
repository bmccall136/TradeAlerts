# services/etrade_service.py
import os, json, requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

BASE_URL = os.getenv("ETRADE_API_HOST", "https://api.etrade.com")
def get_equity_value() -> float:
    """Total account value = cash-ish + sum of market values."""
    aid = _primary_account_id()

    # Balance: prefer netCash, else money market balance
    bj = _eget(f"/v1/accounts/{aid}/balance.json", {"instType": "BROKERAGE"}).json()
    b  = bj.get("BalanceResponse", {}) or {}
    cashish = (
        (b.get("Computed", {}) or {}).get("netCash")
        or (b.get("Cash", {}) or {}).get("moneyMktBalance")
        or 0.0
    )

    # Portfolio: sum marketValue
    pj = _eget(f"/v1/accounts/{aid}/portfolio.json", {"instType": "BROKERAGE"}).json()
    mv_total = 0.0
    try:
        acct = pj["PortfolioResponse"]["AccountPortfolio"][0]
        pos  = acct.get("Position") or []
        if isinstance(pos, dict):
            pos = [pos]
        for p in pos:
            mv_total += float(p.get("marketValue") or 0.0)
    except Exception:
        pass

    return round(float(cashish) + float(mv_total), 2)

def _read_tokens_json():
    """Fallback to etrade_tokens.json if env is not set."""
    p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "etrade_tokens.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            j = json.load(f)
        return {
            "ck":  j.get("consumer_key")  or j.get("key"),
            "cs":  j.get("consumer_secret") or j.get("secret"),
            "tok": j.get("oauth_token"),
            "ts":  j.get("oauth_token_secret"),
        }
    except Exception:
        return {"ck": None, "cs": None, "tok": None, "ts": None}

def _oauth1():
    ck  = os.getenv("ETRADE_CONSUMER_KEY")    or os.getenv("CONSUMER_KEY")    or os.getenv("ETRADE_API_KEY")
    cs  = os.getenv("ETRADE_CONSUMER_SECRET") or os.getenv("CONSUMER_SECRET") or os.getenv("ETRADE_API_SECRET")
    tok = os.getenv("OAUTH_TOKEN")            or os.getenv("ETRADE_OAUTH_TOKEN")
    ts  = os.getenv("OAUTH_TOKEN_SECRET")     or os.getenv("ETRADE_OAUTH_TOKEN_SECRET")
    if not all([ck, cs, tok, ts]):
        fb = _read_tokens_json()
        ck  = ck  or fb["ck"]; cs = cs or fb["cs"]; tok = tok or fb["tok"]; ts = ts or fb["ts"]
    if not all([ck, cs, tok, ts]):
        raise RuntimeError("Missing E*TRADE OAuth creds (env variables or etrade_tokens.json).")
    return OAuth1(ck, cs, tok, ts, signature_type="auth_header")

def _with_ck(params=None):
    """Add consumerKey param some account endpoints require."""
    p = dict(params or {})
    ck = (os.getenv("ETRADE_CONSUMER_KEY") or os.getenv("CONSUMER_KEY") or os.getenv("ETRADE_API_KEY"))
    if ck:
        p.setdefault("consumerKey", ck)
    return p

def _eget(path: str, params: dict | None = None):
    r = requests.get(
        BASE_URL + path,
        params=_with_ck(params),
        auth=_oauth1(),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r

# ---------- Public API ----------

def _primary_account_id() -> str:
    """Use env override if present to avoid list.json; else fetch it."""
    aid = os.getenv("ETRADE_ACCOUNT_ID_KEY") or os.getenv("ACCOUNT_ID_KEY")
    if aid:
        return aid
    j = _eget("/v1/accounts/list.json").json()
    accounts = j.get("AccountListResponse", {}).get("Accounts", {}).get("Account", [])
    if isinstance(accounts, dict):
        accounts = [accounts]
    if not accounts:
        raise RuntimeError("No E*TRADE accounts returned.")
    return accounts[0].get("accountIdKey") or accounts[0].get("accountId")

def fetch_etrade_quote(symbol: str):
    """Return last price (float) if possible; else the raw quote dict."""
    resp = _eget(f"/v1/market/quote/{symbol}.json")
    j = resp.json()
    try:
        qd = j["QuoteResponse"]["QuoteData"][0]
        allq = qd.get("All", {})
        last = allq.get("lastTrade") or allq.get("lastPrice") or qd.get("lastTrade")
        return float(last)
    except Exception:
        return j

def get_account_summary() -> dict:
    aid = _primary_account_id()
    j = _eget(f"/v1/accounts/{aid}/balance.json", {"instType": "BROKERAGE"}).json()
    return j

def get_positions() -> list[dict]:
    """Return a flat list of positions: symbol/qty/price_paid/last_price."""
    aid = _primary_account_id()
    j = _eget(f"/v1/accounts/{aid}/portfolio.json", {"instType": "BROKERAGE"}).json()

    out = []
    try:
        pr = j.get("PortfolioResponse", {})
        aps = pr.get("AccountPortfolio", [])
        if isinstance(aps, dict):
            aps = [aps]

        def _pick(d, *paths, default=None):
            for p in paths:
                cur = d
                try:
                    for k in p.split("."):
                        cur = (cur[0] if isinstance(cur, list) else cur).get(k)
                    if cur not in (None, "", "-", "NA"):
                        return cur
                except Exception:
                    pass
            return default

        for ap in aps or []:
            pos = ap.get("Position")
            if not pos:
                continue
            pos = [pos] if isinstance(pos, dict) else pos
            for p in pos:
                prod = p.get("Product", {}) or {}
                sym  = (prod.get("symbol") or "").upper()
                qty  = float(p.get("quantity") or p.get("qty") or 0)
                paid = float(p.get("pricePaid") or p.get("averagePrice") or 0)
                last = _pick(p,
                             "Quick.quote.lastTrade",
                             "Quick.quote.lastPrice",
                             "Quick.lastTrade",
                             default=0.0)
                last = float(last or 0.0)
                out.append({
                    "symbol": sym, "qty": qty,
                    "price_paid": paid, "last_price": last,
                })
    except Exception:
        pass

    return out
