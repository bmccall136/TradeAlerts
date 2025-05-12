
# symbols.py

# S&P 500 symbols list loaded from a flat file
with open("sp500_symbols.txt") as f:
    SP500_SYMBOLS = [line.strip() for line in f if line.strip()]

YAHOO_SYMBOL_MAP = {
    "BRK.B": "BRK-B",
    "BF.B": "BF-B"
}

def map_symbol(symbol):
    return YAHOO_SYMBOL_MAP.get(symbol, symbol)
