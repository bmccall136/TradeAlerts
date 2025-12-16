"""
Quick sanity-check script to see what E*TRADE says your account
numbers are, using the same services/etrade_service wrapper that
live.py and dashboard.py use.

Run with:

    cd C:\TradeAlerts
    python fetch_etrade_summary.py
"""

from pprint import pprint
import logging

from services import etrade_service as et


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("=== Fetching E*TRADE account summary via API ===")
    try:
        acct = et.get_account_summary() or {}
    except Exception as exc:
        print("\nERROR: get_account_summary() failed:\n", exc)
        print(
            "\nIf this says something like oauth_problem=token_expired, "
            "run your auth shortcut / token refresh and try again."
        )
        return

    raw = acct.get("raw") or {}
    comp = raw.get("Computed") or {}

    print("\n--- Normalized view (what TradeAlerts already uses) ---")
    print(f"account_id          : {acct.get('account_id')}")
    print(f"account_key         : {acct.get('account_key')}")
    print(f"account_type        : {acct.get('account_type')}")
    print(f"account_type_display: {acct.get('account_type_display')}")
    print()
    print(f"NAV (nav)           : {acct.get('nav')}")
    print(f"Cash balance        : {acct.get('cash_balance')}")
    print(f"Available funds     : {acct.get('available_funds')}")
    print(f'UI buying power     : {acct.get("buying_power")}')
    print(f"Positions value     : {acct.get('positions_value')}")

    print("\n--- Raw Computed block from E*TRADE (for comparison) ---")
    keys_of_interest = [
        "netAccountValue",
        "cashBalance",
        "cashAvailableForInvestment",
        "cashBuyingPower",
        "marginBuyingPower",
        "netCash",
        "dayTraderBuyingPower",
    ]
    for k in keys_of_interest:
        if k in comp:
            print(f"{k:26s}: {comp.get(k)}")

    print("\n--- Full raw payload (debug) ---")
    pprint(raw)


if __name__ == "__main__":
    main()
