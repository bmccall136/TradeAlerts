import sqlite3
import pytest
import os
import tempfile

from dashboard import create_app
import config
from importlib import reload

@pytest.fixture
def client(tmp_path, monkeypatch):
    alert_db = tmp_path / 'alerts.db'
    sim_db = tmp_path / 'sim.db'
    conn = sqlite3.connect(str(alert_db))
    conn.execute("""CREATE TABLE alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, name TEXT, signal TEXT, confidence INTEGER, price REAL, timestamp TEXT,
        type TEXT, sparkline TEXT, triggers TEXT, vwap REAL
    )""")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(sim_db))
    conn.execute("CREATE TABLE state (cash REAL);")
    conn.execute("INSERT INTO state VALUES (5000.0);")
    conn.execute("CREATE TABLE holdings (symbol TEXT, quantity REAL, avg_price REAL);")
    conn.execute("CREATE TABLE trades (timestamp TEXT, symbol TEXT, action TEXT, quantity REAL, price REAL);")
    conn.commit()
    conn.close()
    monkeypatch.setenv('ALERT_DB', str(alert_db))
    monkeypatch.setenv('SIM_DB', str(sim_db))
    reload(config)
    import services.alert_service; reload(services.alert_service)
    import services.simulation_service; reload(services.simulation_service)
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()

def test_alert_post_and_get(client):
    payload = {
        'symbol': 'INTG',
        'name': 'Integration Corp',
        'signal': 'BUY',
        'confidence': 100,
        'price': 50.0,
        'timestamp': '2025-05-02 12:30:00',
        'type': 'buy',
        'sparkline': '',
        'triggers': '',
        'vwap': 0.0
    }
    resp = client.post('/', json=payload)
    assert resp.status_code == 204
    resp = client.get('/')
    assert b'INTG' in resp.data

def test_simulation_reset(client):
    resp = client.post('/simulation/reset')
    assert resp.status_code == 204
    resp = client.get('/simulation/')
    assert b'Cash:' in resp.data
