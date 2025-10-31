import os, re, sys
from io import StringIO

ROOT = r"C:\TradeAlerts"
URL  = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

def fetch_html(url):
    import requests
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    r = requests.get(url, headers=hdrs, timeout=20)
    r.raise_for_status()
    return r.text

def parse_symbols(html):
    # Try pandas on the fetched HTML string first (works even when direct read_html 403s)
    try:
        import pandas as pd
        dfs = pd.read_html(StringIO(html))
        # Heuristic: pick first table that has a 'Symbol' column
        for df in dfs:
            cols = [c.lower() for c in df.columns.astype(str).tolist()]
            if any(c == "symbol" for c in cols):
                sym_col = df.columns[[c == "symbol" for c in cols][0]]
                raw = [str(s).strip() for s in df[sym_col].tolist()]
                return sorted(set(raw))
    except Exception:
        pass

    # Fallback: simple HTML scrape
    import bs4
    soup = bs4.BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.wikitable")
    syms = []
    if table:
        rows = table.select("tr")
        for tr in rows[1:]:
            tds = tr.find_all(["td","th"])
            if not tds: 
                continue
            cell = tds[0].get_text(strip=True)
            if cell and cell.lower() != "symbol":
                syms.append(cell)
    return sorted(set(syms))

def main():
    try:
        html = fetch_html(URL)
    except Exception as e:
        print(f"[error] couldn't fetch Wikipedia: {e}")
        sys.exit(1)

    syms = parse_symbols(html)
    if not syms:
        print("[error] parsed 0 symbols — aborting")
        sys.exit(2)

    clean = sorted({s.replace(".", "-") for s in syms})
    raw_path   = os.path.join(ROOT, "sp500_symbols.txt")
    clean_path = os.path.join(ROOT, "sp500_symbols_clean.txt")

    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("\n".join(syms))
    with open(clean_path, "w", encoding="utf-8") as f:
        f.write("\n".join(clean))

    print(f"[done] wrote {len(syms)} symbols to sp500_symbols.txt and {len(clean)} to sp500_symbols_clean.txt")

if __name__ == "__main__":
    try:
        import requests, bs4  # ensure deps
    except ImportError:
        print("[info] installing missing deps: requests, beautifulsoup4")
        import subprocess, sys as _sys
        subprocess.check_call([_sys.executable, "-m", "pip", "install", "-q", "requests", "beautifulsoup4"])
    main()