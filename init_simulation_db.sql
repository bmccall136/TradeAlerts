CREATE TABLE IF NOT EXISTS holdings (
    symbol TEXT PRIMARY KEY,
    qty INTEGER,
    avg_cost REAL,
    last_price REAL
);

CREATE TABLE IF NOT EXISTS account (
    cash_balance REAL
);
