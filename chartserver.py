from flask import Flask, render_template, request, jsonify
import sqlite3
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timedelta
from etrade_auth import get_etrade_session
from etrade_quotes import get_intraday_history

app = Flask(__name__)

@app.route('/')
def index():
    filter_mode = request.args.get('filter', 'all')
    conn = sqlite3.connect('alerts_clean.db')
    c = conn.cursor()

    if filter_mode in ['sniper', 'lax', 'breakout', 'sell']:
        c.execute("SELECT * FROM alerts WHERE signal_type = ? ORDER BY timestamp DESC", (filter_mode,))
    else:
        c.execute("SELECT * FROM alerts ORDER BY timestamp DESC")

    rows = c.fetchall()
    conn.close()
    return render_template('index.html', alerts=rows, filter_mode=filter_mode)

@app.route('/chart/<symbol>')
def chart(symbol):
    # Accept either 'time' or 'timestamp' query param
    alert_time_str = request.args.get('time') or request.args.get('timestamp')
    if not alert_time_str:
        return render_template("chart_error.html", error="No alert time provided.")

    try:
        alert_time = datetime.strptime(alert_time_str, "%Y-%m-%d %H:%M:%S")
        session = get_etrade_session()
        chart_data = get_intraday_history(symbol, session)
    except Exception as e:
        return render_template("chart_error.html", error=f"Failed to load chart data: {e}")

    times = []
    prices = []
    try:
        for candle in chart_data:
            ts = datetime.fromtimestamp(candle['datetime'] / 1000)
            # include one hour before alert to plotting end
            if ts >= alert_time - timedelta(hours=1):
                times.append(ts)
                prices.append(candle['close'])
    except Exception as e:
        return render_template("chart_error.html", error=f"Chart parsing error: {e}")

    if not times or not prices:
        return render_template("chart_error.html", error="No data in time range.")

    fig, ax = plt.subplots()
    ax.plot(times, prices, label=symbol)
    ax.axvline(x=alert_time, color='red', linestyle='--', label='Alert Time')
    ax.set_title(f"{symbol} - Intraday Chart")
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")
    ax.legend()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    plt.close(fig)

    return render_template("chart_view.html", symbol=symbol, chart=image_base64)

@app.route('/clear/<timestamp>')
def clear_alert(timestamp):
    conn = sqlite3.connect('alerts_clean.db')
    c = conn.cursor()
    c.execute("DELETE FROM alerts WHERE timestamp = ?", (timestamp,))
    conn.commit()
    conn.close()
    return ('', 204)

@app.route('/clear_all')
def clear_all():
    conn = sqlite3.connect('alerts_clean.db')
    c = conn.cursor()
    c.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return ('', 204)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
