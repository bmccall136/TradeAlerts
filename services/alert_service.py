import sqlite3
import matplotlib
# Use the Agg backend so matplotlib never tries to open a GUI
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

ALERTS_DB = 'alerts.db'


def generate_sparkline(prices):
    """
    Given a list of prices, produce a tiny black-background sparkline (yellow line)
    and return it as an SVG string.
    """
    fig, ax = plt.subplots(figsize=(2.0, 0.4), dpi=100)
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    ax.plot(prices, color='yellow', linewidth=1.25)
    ax.axis('off')

    buf = io.BytesIO()
    fig.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0, transparent=True)
    plt.close(fig)

    svg_data = buf.getvalue().decode()
    # Strip everything before the first <svg> tag
    svg_data = svg_data.split('<svg', 1)[1]
    svg_data = f'<svg{svg_data}'
    return svg_data


def get_active_alerts():
    """
    Return a list of dictionaries for all alerts where cleared=0,
    deduplicated so only the newest entry per symbol remains.
    """
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute(
        "SELECT id, symbol, name, price, vwap, vwap_diff, triggers, sparkline, timestamp "
        "FROM alerts "
        "WHERE cleared=0 "
        "ORDER BY timestamp DESC"
    )
    rows = c.fetchall()
    columns = [desc[0] for desc in c.description]
    conn.close()

    seen = set()
    deduped_rows = []
    for row in rows:
        symbol = row[1]
        if symbol not in seen:
            seen.add(symbol)
            deduped_rows.append(row)

    alerts = [dict(zip(columns, row)) for row in deduped_rows]
    return alerts


def insert_alert(symbol, price, timestamp, name, vwap, vwap_diff, triggers, sparkline):
    """
    Delete any existing alert for this symbol, then insert the new one with cleared=0.
    """
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("DELETE FROM alerts WHERE symbol=?", (symbol,))
    c.execute(
        "INSERT INTO alerts "
        "(symbol, price, timestamp, name, vwap, vwap_diff, triggers, sparkline, cleared) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (symbol, price, timestamp, name, vwap, vwap_diff, triggers, sparkline)
    )
    conn.commit()
    conn.close()


def mark_alert_cleared(alert_id):
    """
    Mark a single alert row (by its id) as cleared=1.
    """
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("UPDATE alerts SET cleared=1 WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()


def clear_all_alerts():
    """
    Mark every alert in the DB as cleared=1.
    """
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("UPDATE alerts SET cleared=1")
    conn.commit()
    conn.close()


def clear_alerts_by_filter(filter_type, value):
    """
    Clear alerts either by symbol or by trigger substring:
      - If filter_type == 'symbol', set cleared=1 where symbol = value.
      - If filter_type == 'trigger', set cleared=1 where triggers LIKE '%value%'.
    """
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    if filter_type == 'symbol':
        c.execute("UPDATE alerts SET cleared=1 WHERE symbol=?", (value,))
    elif filter_type == 'trigger':
        c.execute(
            "UPDATE alerts SET cleared=1 WHERE triggers LIKE ?",
            (f"%{value}%",)
        )
    conn.commit()
    conn.close()

def clear_alert_by_id(alert_id):
    conn = sqlite3.connect(ALERTS_DB)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

# Expose get_alerts under this name so api.py can import it
get_alerts = get_active_alerts
