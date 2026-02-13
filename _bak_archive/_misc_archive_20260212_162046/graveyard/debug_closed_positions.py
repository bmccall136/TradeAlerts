from __future__ import annotations

import json
from datetime import date, timedelta

from services import etrade_service as et


def main() -> None:
    # Use the same helpers etrade_service already uses
    acct = et.account_id_key()
    sess = et.get_oauth_session()

    # Pull a small recent window so output isn't insane
    end = date.today()
    start = end - timedelta(days=10)

    # These helpers exist in etrade_service; we reuse them to format dates
    from services.etrade_service import _ymd  # type: ignore

    url = f"https://api.etrade.com/v1/accounts/{acct}/gainloss/closedpositions.json"
    params = {
        "startDate": _ymd(start),
        "endDate": _ymd(end),
    }

    print("Requesting:", url, "params:", params, flush=True)
    resp = sess.get(url, params=params, timeout=20)
    print("Status:", resp.status_code, flush=True)

    try:
        data = resp.json()
    except Exception as e:
        print("JSON decode error:", e)
        print("Body (first 500 chars):")
        print(resp.text[:500])
        return

    # Show only a few closed positions so we can map fields precisely
    closed = (
        (data.get("ClosedPositions") or {}).get("closedPosition")
        or data.get("closedPosition")
        or []
    )
    if isinstance(closed, dict):
        closed = [closed]

    print(f"Closed positions returned: {len(closed)}")
    for row in closed[:5]:
        print("-" * 60)
        print(json.dumps(row, indent=2)[:1000])  # trim just in case


if __name__ == "__main__":
    main()
