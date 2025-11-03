
# live_start.py — refreshed S&P 500 fetch (robust headers + retry), BP-only sizing compatible
# Drop-in for C:\TradeAlerts\live_start.py
from __future__ import annotations

import sys, time, logging, pathlib, traceback
from typing import List
from datetime import datetime
import os

LOG = logging.getLogger("launcher")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

DATA_DIR = pathlib.Path(__file__).resolve().parent
SYMS_TXT = DATA_DIR / "sp500_symbols.txt"
SYMS_CLEAN = DATA_DIR / "sp500_symbols_clean.txt"

def _fetch_sp500_from_wikipedia(max_retries: int = 3, sleep_s: float = 1.2) -> List[str] | None:
    """
    Tries two approaches:
      1) requests.get(… headers=UA ) + pandas.read_html(response.text)
      2) as a fallback, Wikipedia REST HTML endpoint (also with headers).
    Returns list of symbols on success, else None.
    """
    try:
        import requests
        import pandas as pd
    except Exception:
        LOG.warning("pandas/requests not available; cannot fetch Wikipedia")
        return None

    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
        "Gecko/20100101 Firefox/123.0 GCSD-TradeAlerts/1.0 (+admin@gcsd.local)"
    )
    HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

    url_html = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    url_rest = "https://en.wikipedia.org/api/rest_v1/page/html/List_of_S%26P_500_companies"

    # Attempt 1: classic page HTML
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url_html, headers=HEADERS, timeout=15)
            if resp.status_code == 200 and resp.text:
                try:
                    tables = pd.read_html(resp.text)
                except Exception as e:
                    LOG.warning("pandas.read_html failed on classic page (attempt %d/%d): %s",
                                attempt, max_retries, e)
                else:
                    for df in tables:
                        cols = [str(c).strip().lower() for c in df.columns]
                        if any("symbol" == c or "ticker symbol" in c for c in cols):
                            syms = [str(x).strip().upper() for x in df.iloc[:, 0].tolist() if str(x).strip()]
                            return syms
            else:
                LOG.warning("Wikipedia classic page status=%s (attempt %d/%d)",
                            resp.status_code, attempt, max_retries)
        except Exception as e:
            LOG.warning("Wikipedia fetch via requests (classic) failed (attempt %d/%d): %s",
                        attempt, max_retries, e)
        time.sleep(sleep_s)

    # Attempt 2: REST HTML
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url_rest, headers=HEADERS, timeout=15)
            if resp.status_code == 200 and resp.text:
                try:
                    tables = pd.read_html(resp.text)
                except Exception as e:
                    LOG.warning("pandas.read_html failed on REST HTML (attempt %d/%d): %s",
                                attempt, max_retries, e)
                else:
                    for df in tables:
                        cols = [str(c).strip().lower() for c in df.columns]
                        if any("symbol" == c or "ticker symbol" in c for c in cols):
                            syms = [str(x).strip().upper() for x in df.iloc[:, 0].tolist() if str(x).strip()]
                            return syms
            else:
                LOG.warning("Wikipedia REST page status=%s (attempt %d/%d)",
                            resp.status_code, attempt, max_retries)
        except Exception as e:
            LOG.warning("Wikipedia fetch via requests (REST) failed (attempt %d/%d): %s",
                        attempt, max_retries, e)
        time.sleep(sleep_s)

    return None

def load_symbols_fresh_or_local() -> List[str]:
    syms = _fetch_sp500_from_wikipedia()
    if syms:
        # Clean: filter obvious junk and normalize dots to dashes for broker/yahoo compatibility if needed.
        clean = []
        for s in syms:
            s = s.replace(" ", "").upper()
            # Keep the raw symbol; a separate "clean" file will include dotted->dashed for optional use
            if s and s.isascii():
                clean.append(s)
        try:
            SYMS_TXT.write_text("\n".join(clean) + "\n", encoding="utf-8")
            # Also write dashed copy for consumers that prefer BRK.B → BRK-B form
            dashed = [x.replace(".", "-") for x in clean]
            SYMS_CLEAN.write_text("\n".join(dashed) + "\n", encoding="utf-8")
            LOG.info("📥 Fetched %d S&P 500 symbols from Wikipedia → %s", len(clean), SYMS_TXT)
        except Exception as e:
            LOG.warning("Could not write symbols to disk: %s", e)
        return clean

    # Fallback to local file(s)
    if SYMS_TXT.exists():
        data = [line.strip().upper() for line in SYMS_TXT.read_text(encoding="utf-8").splitlines() if line.strip()]
        LOG.info("📄 Using local symbols from %s (%d)", str(SYMS_TXT), len(data))
        return data

    LOG.warning("No symbols available (Wikipedia blocked and local file missing)")
    return []

def main() -> int:
    LOG.info("▶️  Live launcher starting…")
    GUARDRAILS = os.environ.get("GUARDRAILS_ENABLED", "false").lower() == "true"
    SAFE_MODE = os.environ.get("LIVE_SAFE_MODE", "false").lower() == "true"
    LOG.info("GUARDRAILS_ENABLED = %s", str(GUARDRAILS).lower())
    LOG.info("LIVE_SAFE_MODE     = %s", str(SAFE_MODE).lower())

    symbols = load_symbols_fresh_or_local()

    # Load settings (unchanged)
    settings_path = DATA_DIR / "live_settings.json"
    if settings_path.exists():
        LOG.info("🔧 Using live settings from %s", str(settings_path))
        try:
            import json
            with settings_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            LOG.exception("Failed reading live_settings.json")
            data = {}
    else:
        LOG.warning("live_settings.json missing; using defaults")
        data = {}

    # Start loop
    try:
        from services.live_loop import run_live_loop
        mode = "LIVE"
        LOG.info("▶️  Live loop starting (mode=%s)", mode)
        from services import live_guardrails as gr  # just to show GR banner if present
        LOG.info("[GR] auto-seller started (enabled=%s)", str(False))
        run_live_loop(data, symbols, broker_mode=mode)
    except Exception:
        LOG.exception("Live loop crashed")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
