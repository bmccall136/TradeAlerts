-- You can't DROP COLUMN in SQLite easily, but you can recreate the table:

-- 1. Rename old table
ALTER TABLE holdings RENAME TO holdings_old;

-- 2. Create new holdings table (without last_price)
CREATE TABLE holdings (
    symbol TEXT PRIMARY KEY,
    qty INTEGER NOT NULL,
    avg_cost REAL NOT NULL
);

-- 3. Copy data over (skip last_price)
INSERT INTO holdings (symbol, qty, avg_cost)
SELECT symbol, qty, avg_cost FROM holdings_old;

-- 4. Drop old table
DROP TABLE holdings_old;
