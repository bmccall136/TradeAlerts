import json
import os
import datetime as dt

# Default path for your contributions file
CONTRIB_PATH = os.environ.get("CONTRIB_PATH", r"C:\TradeAlerts\contributions.json")


def _load():
    """
    Load contributions.json in a very forgiving way.

    Expected format:
    {
        "entries": [
            {"date": "2025-11-11", "amount": 2000.00, "note": "Deposit"},
            ...
        ]
    }
    """
    try:
        if not os.path.exists(CONTRIB_PATH):
            return {"entries": []}

        # Read as bytes so we can strip UTF-8 BOM if needed
        with open(CONTRIB_PATH, "rb") as f:
            raw = f.read()

        # Strip UTF-8 BOM if present
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]

        # Decode to text and parse JSON
        text = raw.decode("utf-8", errors="replace")
        data = json.loads(text)

        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data

        # If structure isn't as expected, treat as empty
        return {"entries": []}
    except Exception:
        # On any error, just act like there are no contributions
        return {"entries": []}


def get_total_contributions(since_iso: str = "2025-08-22") -> float:
    """
    Sum all contributions with date >= since_iso (YYYY-MM-DD).
    """
    data = _load()
    total = 0.0

    try:
        cutoff = dt.datetime.fromisoformat(str(since_iso).strip())
    except Exception:
        # If the cutoff is bad, just treat as far future so nothing counts
        return 0.0

    for e in data.get("entries", []):
        try:
            date_str = str(e.get("date", "")).strip()
            amt = float(e.get("amount", 0) or 0.0)
            if not date_str:
                continue

            d = dt.datetime.fromisoformat(date_str)
            if d >= cutoff:
                total += amt
        except Exception:
            # Ignore bad rows
            continue

    return round(total, 2)
