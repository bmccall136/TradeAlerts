
# symbols.py

import os

# Path resolution for sp500 list
filename = os.getenv("SP500_FILE", "sp500.txt")
base_dir = os.path.dirname(os.path.abspath(__file__))
symbols_path = filename if os.path.isabs(filename) else os.path.join(base_dir, filename)

# Load raw S&P 500 symbols
with open(symbols_path) as f:
    SP500_SYMBOLS = [line.strip() for line in f if line.strip()]

# Optional mapping function if any tickers need adjustment for Yahoo Finance
def map_symbol(symbol):
    # e.g., BRK.B -> BRK-B
    return symbol.replace(".", "-")
