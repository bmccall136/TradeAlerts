# services/data_service.py
import os


def load_symbols(filename: str = "sp500_symbols.txt") -> list[str]:
    """
    Load a list of tickers from a file at the project root.
    Ignores blank lines and lines beginning with '#'.

    :param filename: Name of the symbols file in the project root
    :return: List of ticker strings
    """
    # Determine project root (one level up from this services/ folder)
    project_root = os.path.dirname(os.path.dirname(__file__))
    filepath = os.path.join(project_root, filename)

    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Symbols file not found: {filepath}")

    symbols: list[str] = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            symbols.append(line)
    return symbols
