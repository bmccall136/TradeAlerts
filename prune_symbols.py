# prune_symbols.py

import yfinance as yf

RAW_PATH   = 'sp500_symbols.txt'
CLEAN_PATH = 'sp500_symbols_clean.txt'

def prune_sp500(raw_path=RAW_PATH, clean_path=CLEAN_PATH):
    with open(raw_path) as f:
        raw = [line.strip() for line in f if line.strip()]

    clean = []
    for sym in raw:
        yf_sym = sym.replace('.', '-')  # BRK.B -> BRK-B
        try:
            df = yf.Ticker(yf_sym).history(period='1d')
        except Exception as e:
            print(f"[ERROR] {sym}: fetch failed ({e}), skipping.")
            continue
        if df is None or df.empty:
            print(f"[WARN] No data for {sym} (tried {yf_sym}), skipping.")
        else:
            clean.append(sym)

    with open(clean_path, 'w') as f:
        for sym in clean:
            f.write(sym + '\n')

    print(f"✔️  Clean list written to {clean_path} ({len(clean)} symbols)")

if __name__ == "__main__":
    prune_sp500()
