import sqlite3
from flask import Flask, render_template, request, redirect, send_file
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf
import pandas as pd
import io
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

app = Flask(__name__)
DATABASE = 'alerts_clean.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def purge_old_alerts():
    cutoff = datetime.now() - timedelta(hours=1)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    conn.execute("DELETE FROM alerts WHERE timestamp < ?", (cutoff_str,))
    conn.commit()
    conn.close()

def get_alerts(filter_type='all'):
    # ... existing get_alerts code ...
    conn = get_db_connection()
    cur = conn.cursor()
    # filters omitted for brevity
    cur.execute("SELECT * FROM alerts ORDER BY timestamp DESC")
    alerts = cur.fetchall()
    conn.close()
    return alerts

@app.route('/')
def index():
    filter_type = request.args.get('filter', 'all')
    alerts = get_alerts(filter_type)
    return render_template('index.html', alerts=alerts, filter=filter_type)

@app.route('/alerts', methods=['POST'])
def receive_alert():
    data = request.get_json()
    print(f"[DEBUG] Received alert: {data}")  # Debug print
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO alerts (symbol, name, signal, confidence, price, sparkline, timestamp, chart_url, triggers) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (data.get('symbol'), data.get('name'), data.get('signal'), data.get('confidence'),
         data.get('price'), data.get('sparkline'), data.get('timestamp'),
         data.get('chart_url'), data.get('triggers'))
    )
    conn.commit()
    conn.close()
    return 'OK', 200

# ... chart_view and other routes omitted for brevity ...

if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    scheduler.add_job(purge_old_alerts, 'interval', minutes=15)
    scheduler.start()
    app.run(debug=True)