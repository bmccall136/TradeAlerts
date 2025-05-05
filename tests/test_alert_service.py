import os
import sqlite3
import tempfile
import pytest

import config
from importlib import reload

@pytest.fixture
def temp_alert_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        name TEXT,
        signal TEXT,
        confidence INTEGER,
        price REAL,
        timestamp TEXT,
        type TEXT,
        sparkline TEXT,
        triggers TEXT,
        vwap REAL
    )""")
    conn.commit()
    conn.close()
    monkeypatch.setenv('ALERT_DB', path)
    reload(config)
    import services.alert_service as svc
    reload(svc)
    return svc

def test_insert_and_get_alerts(temp_alert_db):
    svc = temp_alert_db
    data = {
        'symbol': 'ABC',
        'name': 'Test Corp',
        'signal': 'BUY',
        'confidence': 90,
        'price': 123.45,
        'timestamp': '2025-05-02 12:00:00',
        'type': 'buy',
        'sparkline': '1,2,3',
        'triggers': 'MACD',
        'vwap': 124.0
    }
    svc.insert_alert(data)
    alerts = svc.get_alerts()
    assert len(alerts) == 1
    row = alerts[0]
    assert row[1] == 'ABC'
    assert row[3] == 'BUY'

def test_clear_alert(temp_alert_db):
    svc = temp_alert_db
    svc.insert_alert({'symbol': 'A', 'name': 'A', 'signal': 'BUY', 'confidence': 50, 'price': 10, 'timestamp': 't', 'type':'buy', 'sparkline':'', 'triggers':'', 'vwap':0})
    svc.insert_alert({'symbol': 'B', 'name': 'B', 'signal': 'SELL', 'confidence': 40, 'price': 20, 'timestamp': 't', 'type':'sell', 'sparkline':'', 'triggers':'', 'vwap':0})
    alerts = svc.get_alerts()
    assert len(alerts) == 2
    first_id = alerts[0][0]
    svc.clear_alert(first_id)
    alerts = svc.get_alerts()
    assert len(alerts) == 1
    assert alerts[0][1] == 'B'
