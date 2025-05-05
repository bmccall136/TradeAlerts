import sqlite3
import tempfile
import pytest

import config
from importlib import reload

@pytest.fixture
def temp_sim_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE state (cash REAL);")
    conn.execute("INSERT INTO state (cash) VALUES (5000.0);")
    conn.execute("CREATE TABLE holdings (symbol TEXT, quantity REAL, avg_price REAL);")
    conn.execute("CREATE TABLE trades (timestamp TEXT, symbol TEXT, action TEXT, quantity REAL, price REAL);")
    conn.commit()
    conn.close()
    monkeypatch.setenv('SIM_DB', path)
    reload(config)
    import services.simulation_service as svc
    reload(svc)
    return svc

def test_reset_state(temp_sim_db):
    svc = temp_sim_db
    conn = sqlite3.connect(config.Config.SIM_DB)
    conn.execute("INSERT INTO holdings VALUES ('XYZ', 10, 50);")
    conn.execute("INSERT INTO trades VALUES ('t', 'XYZ', 'BUY', 10, 50);")
    conn.commit()
    conn.close()
    svc.reset_state(starting_cash=10000.0)
    state = svc.get_simulation_state()
    assert state['cash'] == 10000.0
    assert state['holdings'] == []
    assert state['trades'] == []

def test_record_and_get_state(temp_sim_db):
    svc = temp_sim_db
    svc.record_trade('2025-05-02 12:00:00', 'LMN', 'BUY', 5, 200.0)
    state = svc.get_simulation_state()
    assert len(state['trades']) == 1
    assert state['trades'][0][1] == 'LMN'
