import sqlite3
import json
from typing import List, Dict

DB_PATH = 'alerts.db'

def _get_conn():
    return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)

def _init_db():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            signal TEXT,
            confidence REAL,
            price REAL,
            timestamp TEXT,
            sparkline TEXT,
            triggers TEXT,
            vwap REAL
        )
    """)
    conn.commit()
    conn.close()

# Create table on import
_init_db()

def get_alerts(filter_signal: str = 'all') -> List[Dict]:
    conn = _get_conn()
    c = conn.cursor()

    if filter_signal.lower() in ('buy', 'sell'):
        c.execute(
            "SELECT id, symbol, name, signal, confidence, price, timestamp, sparkline, triggers, vwap "
            "FROM alerts WHERE lower(signal)=? ORDER BY timestamp DESC",
            (filter_signal.lower(),)
        )
    else:
        c.execute(
            "SELECT id, symbol, name, signal, confidence, price, timestamp, sparkline, triggers, vwap "
            "FROM alerts ORDER BY timestamp DESC"
        )

    rows = c.fetchall()
    conn.close()

    alerts = []
    for aid, sym, name, sig, conf, price, ts, spark, raw_triggers, vwap in rows:
        # Safe JSON parse
        try:
            triggers = json.loads(raw_triggers or '[]')
        except json.JSONDecodeError:
            triggers = []

        alerts.append({
            'id':        aid,
            'symbol':    sym,
            'name':      name,
            'signal':    sig or '',
            'confidence': conf or 0.0,
            'price':     price or 0.0,
            'timestamp': ts,
            'sparkline': spark or '',
            'triggers':  triggers,
            'vwap':      vwap or 0.0,
        })

    return alerts

def insert_alert(data: Dict) -> None:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO alerts
          (symbol, name, signal, confidence, price, timestamp, sparkline, triggers, vwap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          symbol=excluded.symbol,
          name=excluded.name,
          signal=excluded.signal,
          confidence=excluded.confidence,
          price=excluded.price,
          timestamp=excluded.timestamp,
          sparkline=excluded.sparkline,
          triggers=excluded.triggers,
          vwap=excluded.vwap
    """, (
        data.get('symbol'),
        data.get('name'),
        data.get('signal') or '',
        float(data.get('confidence', 0)),
        float(data.get('price', 0)),
        data.get('timestamp'),
        data.get('sparkline') or '',
        json.dumps(data.get('triggers', [])),
        float(data.get('vwap', 0)),
    ))
    conn.commit()
    conn.close()

def clear_alert(alert_id: str) -> None:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def clear_alerts_by_filter(filter_signal: str = 'all') -> None:
    conn = _get_conn()
    c = conn.cursor()
    if filter_signal.lower() in ('buy', 'sell'):
        c.execute("DELETE FROM alerts WHERE lower(signal)=?", (filter_signal.lower(),))
    else:
        c.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
