-- 1. Rename the existing table
ALTER TABLE alerts RENAME TO alerts_old;

-- 2. Create a new table WITHOUT the `time` column
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    timestamp TEXT,
    name TEXT,
    price REAL,
    triggers TEXT,
    sparkline TEXT,
    vwap REAL,
    vwap_diff REAL,
    cleared INTEGER DEFAULT 0
);

-- 3. Copy data (excluding 'time') from the old table to the new table
INSERT INTO alerts (id, symbol, timestamp, name, price, triggers, sparkline, vwap, vwap_diff, cleared)
SELECT id, symbol, timestamp, name, price, triggers, sparkline, vwap, vwap_diff, cleared FROM alerts_old;

-- 4. Drop the old table
DROP TABLE alerts_old;
