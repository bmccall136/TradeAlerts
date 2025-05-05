from flask import Flask, render_template, request
import yfinance as yf
import plotly.graph_objs as go
from datetime import datetime
from pytz import timezone
import sqlite3

app = Flask(__name__)

@app.route("/chart/<symbol>")
def chart(symbol):
    conn = sqlite3.connect("alerts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp FROM alerts WHERE symbol = ? ORDER BY timestamp ASC LIMIT 1", (symbol,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return f"No alert timestamp found for {symbol}"

    alert_time_str = row[0]
    alert_time = datetime.strptime(alert_time_str, "%Y-%m-%d %H:%M:%S")
    alert_time = timezone("US/Eastern").localize(alert_time)

    df = yf.download(symbol, period="1d", interval="5m")
    df.index = df.index.tz_convert("US/Eastern")

    trace = go.Scatter(x=df.index, y=df["Close"], mode="lines", name=symbol)
    alert_line = go.Scatter(
        x=[alert_time, alert_time],
        y=[df["Close"].min(), df["Close"].max()],
        mode="lines",
        name="Alert Time",
        line=dict(color="red", dash="dash")
    )

    layout = go.Layout(
        title=f"{symbol} - Intraday Chart",
        xaxis=dict(title="Time"),
        yaxis=dict(title="Price"),
        template="plotly_dark"
    )

    fig = go.Figure(data=[trace, alert_line], layout=layout)
    chart_html = fig.to_html(full_html=False)

    return render_template("chart_view.html", chart_html=chart_html)