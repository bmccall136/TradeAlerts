CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    alert_type TEXT,
    price REAL,
    confidence REAL,
    timestamp TEXT,
    triggers TEXT,
    sparkline TEXT,
    cleared INTEGER DEFAULT 0
);
