import pandas as pd

# Wikipedia page for S&P 500 constituents
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

def get_sp500_symbols(filepath="sp500_symbols.txt"):
    tables = pd.read_html(WIKI_URL, attrs={"id": "constituents"})
    df = tables[0]
    # Some tickers use "." for class shares, Yahoo wants "-" instead (e.g. BRK.B → BRK-B)
    symbols = df["Symbol"].str.replace(".", "-", regex=False)
    # Drop anything that's empty or not a string
    symbols = symbols[symbols.notnull() & symbols.str.match(r"^[A-Z0-9\-]+$")]
    with open(filepath, "w") as f:
        for sym in symbols:
            f.write(f"{sym}\n")
    print(f"Updated {filepath} with {len(symbols)} tickers.")

if __name__ == "__main__":
    get_sp500_symbols()
