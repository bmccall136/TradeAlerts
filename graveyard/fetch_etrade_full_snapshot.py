# fetch_etrade_full_snapshot.py
#
# Snapshot what E*TRADE actually thinks your account looks like.
# Uses XML responses from /balance and /portfolio and reads your existing .env:
#   ETRADE_API_KEY, ETRADE_API_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET,
#   ETRADE_ENV, ETRADE_ACCOUNT_ID_KEY

import os
from decimal import Decimal, ROUND_HALF_UP
from pprint import pprint
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session


def d(x):
    """Decimal helper for money."""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _clean(v: str | None) -> str | None:
    """Strip surrounding quotes if present."""
    if v is None:
        return None
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _get_xml(sess: OAuth1Session, url: str, params: dict | None = None) -> ET.Element:
    """GET helper that returns an XML ElementTree root and prints debug on error."""
    params = dict(params or {})
    r = sess.get(url, params=params)
    try:
        r.raise_for_status()
    except Exception:
        print(f"\nERROR: HTTP {r.status_code} for {url}")
        print("Response text (first 1000 chars):")
        print(r.text[:1000])
        raise

    text = r.text
    # Debug header
    print(f"\nDEBUG: GET {url} -> {r.status_code}, Content-Type={r.headers.get('Content-Type')}")
    # print("DEBUG raw XML (first 400 chars):", text[:400])

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        print("\nERROR: Failed to parse XML:")
        print(text[:1000])
        raise

    return root


def main():
    # Load from .env (your existing file in C:\TradeAlerts)
    load_dotenv()

    consumer_key = _clean(os.getenv("ETRADE_API_KEY"))
    consumer_secret = _clean(os.getenv("ETRADE_API_SECRET"))
    oauth_token = _clean(os.getenv("OAUTH_TOKEN"))
    oauth_token_secret = _clean(os.getenv("OAUTH_TOKEN_SECRET"))
    env = (os.getenv("ETRADE_ENV") or "production").lower()
    account_key = _clean(os.getenv("ETRADE_ACCOUNT_ID_KEY"))

    if env == "sandbox":
        base = "https://apisb.etrade.com"
    else:
        base = "https://api.etrade.com"

    if not all([consumer_key, consumer_secret, oauth_token, oauth_token_secret, account_key]):
        raise SystemExit(
            "Missing one or more E*TRADE env vars in .env.\n"
            "Expected: ETRADE_API_KEY, ETRADE_API_SECRET, OAUTH_TOKEN, "
            "OAUTH_TOKEN_SECRET, ETRADE_ACCOUNT_ID_KEY (and optional ETRADE_ENV)."
        )

    sess = OAuth1Session(
        client_key=consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret,
    )

    print(f"Using account_key={account_key!r} (from ETRADE_ACCOUNT_ID_KEY)\n")

    # === 1) Balances ===
    print("=== 1) /v1/accounts/{accountKey}/balance (XML) ===")
    bal_root = _get_xml(
        sess,
        f"{base}/v1/accounts/{account_key}/balance",
        params={"instType": "BROKERAGE", "realTimeNAV": "true"},
    )

    # Expecting something like <BalanceResponse><Computed>...</Computed>...</BalanceResponse>
    comp = bal_root.find(".//Computed")
    if comp is None:
        print("\nWARNING: No <Computed> block found in BalanceResponse. Full XML:")
        print(ET.tostring(bal_root, encoding="unicode"))
        comp_vals = {}
    else:
        comp_vals = {child.tag: child.text for child in comp}

    print("\n--- Raw Computed values from balance ---")
    pprint(comp_vals)

    def dec_from_comp(name: str, default: str = "0") -> Decimal:
        val = comp_vals.get(name, default)
        try:
            return d(val)
        except Exception:
            return d(default)

    cash_balance = dec_from_comp("cashBalance", comp_vals.get("netCash", "0"))
    cash_buying_power = dec_from_comp("cashBuyingPower", "0")
    margin_buying_power = dec_from_comp("marginBuyingPower", "0")
    account_balance = dec_from_comp("accountBalance", "0")

    print("\n--- Parsed balances ---")
    print(f"cash_balance        : {cash_balance}")
    print(f"cash_buying_power   : {cash_buying_power}")
    print(f"margin_buying_power : {margin_buying_power}")
    print(f"account_balance     : {account_balance}  (may or may not match Total Assets)")

    # === 2) Portfolio ===
    print("\n=== 2) /v1/accounts/{accountKey}/portfolio (XML) ===")
    port_root = _get_xml(
        sess,
        f"{base}/v1/accounts/{account_key}/portfolio",
        params={
            "count": 200,
            "sortBy": "SYMBOL",
            "sortOrder": "ASC",
            "totals": "true",
        },
    )

    # Expecting something like <PortfolioResponse><AccountPortfolio>...</AccountPortfolio>...</PortfolioResponse>
    acct_ports = port_root.findall(".//AccountPortfolio")
    if not acct_ports:
        print("\nWARNING: No <AccountPortfolio> found in PortfolioResponse. Full XML:")
        print(ET.tostring(port_root, encoding="unicode"))

    total_mv = Decimal("0")
    for acct_port in acct_ports:
        for pos in acct_port.findall(".//Position"):
            # Try marketValue first, fall back to totalMarketValue
            mv_text = pos.findtext("marketValue")
            if mv_text is None:
                mv_text = pos.findtext("totalMarketValue", "0")
            try:
                total_mv += Decimal(str(mv_text or "0"))
            except Exception:
                continue

    total_mv = total_mv.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    print("\n--- Portfolio totals ---")
    print(f"positions_market_value: {total_mv}")

    # === 3) Our NAV guess: cash + positions ===
    nav_guess = (cash_balance + total_mv).quantize(Decimal("0.01"))

    print("\n=== 3) Snapshot summary ===")
    print(f"Approx NAV (cash + positions MV): {nav_guess}")
    print(f"Cash balance              : {cash_balance}")
    print(f"Cash buying power         : {cash_buying_power}")
    print(f"Margin buying power       : {margin_buying_power}")
    print(f"Positions market value    : {total_mv}")
    print("\nCompare:")
    print("  • Approx NAV vs E*TRADE 'Total Assets / Net Account Value'")
    print("  • cash_buying_power vs 'Cash purchasing power' in the UI")


if __name__ == "__main__":
    main()
