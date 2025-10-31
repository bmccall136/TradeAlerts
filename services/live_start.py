#!/usr/bin/env python3
import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("launcher")

ROOT = os.path.abspath(os.path.dirname(__file__))
SETTINGS_PATH = os.path.join(ROOT, "live_settings.json")
SYMS_RAW = os.path.join(ROOT, "sp500_symbols.txt")
SYMS_CLEAN = os.path.join(ROOT, "sp500_symbols_clean.txt")
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm_mode(v):
    v = str(v or "SIM").strip().upper()
    return "LIVE" if v in ("LIVE", "ETRADE", "REAL") else "SIM"


def _fetch_html(url: str) -> str:
    import requests
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    r = requests.get(url, headers=hdrs, timeout=20)
    r.raise_for_status()
    return r.text


def _parse_symbols(html: str):
    # Try pandas on the fetched HTML (works even when direct read_html 403s)
    try:
        import pandas as pd  # type: ignore
        from io import StringIO
        dfs = pd.read_html(StringIO(html))
        for df in dfs:
            cols = [str(c).strip().lower() for c in df.columns.tolist()]
            if "symbol" in cols:
                # pick that column by exact name position
                idx = cols.index("symbol")
                col = df.columns[idx]
                raw = [str(s).strip() for s in df[col].tolist()]
                return sorted(set(raw))
    except Exception:
        pass

    # Fallback: BeautifulSoup scrape
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.wikitable")
        syms = []
        if table:
            rows = table.select("tr")
            for tr in rows[1:]:
                tds = tr.find_all(["td", "th"])
                if not tds:
                    continue
                cell = tds[0].get_text(strip=True)
                if cell and cell.lower() != "symbol":
                    syms.append(cell)
        return sorted(set(syms))
    except Exception:
        return []


def _refresh_sp500_if_stale(max_age_hours=24, force=False):
    """Refresh S&P500 into raw+clean files (handles Wikipedia 403, no hard deps)."""
    try:
        need = force or (not os.path.exists(SYMS_CLEAN)) or (
            time.time() - os.path.getmtime(SYMS_CLEAN) > max_age_hours * 3600
        )
        if not need:
            age_hr = (time.time() - os.path.getmtime(SYMS_CLEAN)) / 3600
            log.info("ℹ️  Using cached %s (%.1f h old)", SYMS_CLEAN, age_hr)
            return

        log.info("🌐 Refreshing S&P 500 symbols from Wikipedia…")
        html = _fetch_html(WIKI_URL)
        syms_raw = _parse_symbols(html)
        if not syms_raw:
            raise RuntimeError("parsed 0 symbols")

        syms_clean = sorted({s.replace(".", "-") for s in syms_raw})
        with open(SYMS_RAW, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(set(syms_raw))))
        with open(SYMS_CLEAN, "w", encoding="utf-8") as f:
            f.write("\n".join(syms_clean))

        log.info("✅ Updated %s (%d) and %s (%d)", SYMS_RAW, len(syms_raw), SYMS_CLEAN, len(syms_clean))
    except Exception as e:
        log.warning("⚠️  Could not refresh S&P 500 list: %s", e)


def main():
    log.info("▶️  Live launcher starting…")
    log.info("GUARDRAILS_ENABLED = %s", str(os.getenv("GUARDRAILS_ENABLED", "true")).lower())
    log.info("LIVE_SAFE_MODE     = %s", str(os.getenv("LIVE_SAFE_MODE", "true")).lower())

    data = load_json(SETTINGS_PATH)
    raw_mode = data.get("broker_mode", "LIVE")
    mode = _norm_mode(os.getenv("BROKER_MODE") or raw_mode)

    force_now = str(os.getenv("REFRESH_SP500_NOW", "0")).strip().lower() in ("1", "true")
    _refresh_sp500_if_stale(max_age_hours=24, force=force_now)

    from services.market_service import get_symbols
    symbols = get_symbols(SYMS_CLEAN)

    from services.live_loop import run_live_loop
    log.info("🔧 Using live settings from %s", SETTINGS_PATH)
    log.info("▶️  Live loop starting (mode=%s)", mode)
    log.info("📈 Universe size: %d (first 5: %s)", len(symbols), ", ".join(symbols[:5]) if symbols else "")
    run_live_loop(data, symbols, broker_mode=mode)


if __name__ == "__main__":
    sys.exit(main())
