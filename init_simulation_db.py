import sqlite3
import os
import json
from datetime import datetime
from settings import SIMULATION_DB

# Path to your simulation database file; adjust as needed
SIM_DB = os.path.join(os.getcwd(), 'simulation.db')

def init_simulation_db():
    print("🔧 initializing simulation.db schema…")

    # Load starting_cash from config
    try:
        with open("simulation_config.json") as f:
            cfg = json.load(f)
            starting_cash = float(cfg.get("starting_cash", 10000))
    except Exception as e:
        print(f"⚠️ Failed to load starting_cash from config: {e}")
        starting_cash = 10000

    conn = sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
    cur = conn.cursor()

    # drop tables if they exist
    cur.execute("DROP TABLE IF EXISTS state;")
    cur.execute("DROP TABLE IF EXISTS holdings;")
    cur.execute("DROP TABLE IF EXISTS simulation_trades;")

    # recreate state with cash & realized_pl
    cur.execute("""
      CREATE TABLE state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        cash REAL DEFAULT 0,
        realized_pl REAL DEFAULT 0
      );
    """)

    # recreate holdings
    # recreate positions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol    TEXT,
            entry_ts  TIMESTAMP,
            entry_px  REAL,
            qty       INTEGER,
            stop_px   REAL,
            target_px REAL
        );
    """)
