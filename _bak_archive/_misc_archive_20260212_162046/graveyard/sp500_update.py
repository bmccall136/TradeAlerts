# sp500_update.py
# Writes C:\TradeAlerts\sp500_symbols.txt (one symbol per line, BRK.B format)
# Fix: use a real User-Agent to avoid 403 from Wikipedia; robust table detection.

import io, re, sys, time

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
OUTPUT   = "sp500_symbols.txt"

HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
        "Gecko/20100101 Firefox/143.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://en.wikipedia.org/",
}

def _normalize(sym: str) -> str:
    s = (sym or "").strip().upper()
    # Keep dot-class tickers; drop footnote junk/whitespace
    s = re.sub(r"[^A-Z0-9.\-]", "", s)
    return s

def _unique_sorted(symbols):
    return sorted(set([s for s in symbols if s]))

def _fetch_html_with_retries(url, headers, tries=3, timeout=20):
    import requests
    last_err = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r.text
            last_err = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            last_err = e
        time.sleep(1 + i)
    raise last_err or RuntimeError("Failed to fetch HTML")

def _parse_with_bs4(html: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    # Prefer the table with id="constituents"; fall back to first wikitable having Symbol column
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        for t in soup.select("table.wikitable"):
            headers = [th.get_text(strip=True).lower() for th in t.select("tr th")]
            if any(h == "symbol" for h in headers):
                table = t
                break
    if table is None:
        raise RuntimeError("Could not find constituents table")

    symbols = []
    rows = table.select("tr")[1:]  # skip header
    for tr in rows:
        tds = tr.find_all("td")
        if not tds:
            continue
        sym = tds[0].get_text(strip=True)
        symbols.append(_normalize(sym))
    return _unique_sorted(symbols)

def _parse_with_pandas(html: str):
    import pandas as pd
    tables = pd.read_html(io.StringIO(html))
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if "symbol" in cols:
            syms = [_normalize(x) for x in t["Symbol"].tolist()]
            return _unique_sorted(syms)
    raise RuntimeError("pandas could not find a 'Symbol' column")

def main():
    html = None
    try:
        html = _fetch_html_with_retries(WIKI_URL, HDRS)
    except Exception as e:
        print("[ERROR] fetch failed:", e)

    syms = None
    if html:
        # Try pandas first (nice when available), then bs4
        try:
            syms = _parse_with_pandas(html)
            source = "pandas+UA"
        except Exception as e_pd:
            try:
                syms = _parse_with_bs4(html)
                source = "bs4+UA"
            except Exception as e_bs:
                print("[WARN] pandas+bs4 parse failed:", e_pd, "|", e_bs)

    if not syms:
        # Emergency fallback: write a small seed so the app can run; you can refresh later.
        seed = [
            "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","BRK.B","TSLA","LLY",
            "JPM","UNH","V","XOM","AVGO","JNJ","WMT","PG","MA","HD"
        ]
        syms = _unique_sorted(seed)
        source = "seed"

    with io.open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
        for s in syms:
            f.write(s + "\n")

    print(f"[OK] Wrote {len(syms)} symbols to {OUTPUT} (source={source}).")

if __name__ == "__main__":
    main()
